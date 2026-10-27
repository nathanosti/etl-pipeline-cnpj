# Plano: pipeline ETL CNPJ no GCP (Receita → GCS → BigQuery → dbt → Looker Studio)

## Contexto
Precisamos de uma base de CNPJ para prospectar clientes do agro: CNAEs 4683-4/00, 4623-1/08 e 4692-3/00, casando pelo CNAE principal **ou** secundário. Os CNAEs vão mudar com o tempo, então a **base inteira** é ingerida e o recorte acontece só na camada gold. A prioridade agora é o **Bronze**. As camadas silver e gold e o Looker Studio já ficam desenhados e entram logo em seguida.

Fatos levantados:
- A API `api.opencnpj.org/{cnpj}` consulta um CNPJ por vez e não filtra por CNAE, então não serve para varredura. Ela fica como enriquecimento futuro e opcional.
- A fonte oficial é o WebDAV público da Receita: `https://arquivos.receitafederal.gov.br/public.php/webdav/`, com usuário = token `YggdBLfdninEJX9`, senha vazia e `PROPFIND`. Há pastas mensais `YYYY-MM/`, e a mais recente é `2026-09`.
- Um mês tem ~7,8 GB zipados em 37 arquivos: Empresas0-9, Estabelecimentos0-9 (o maior tem 2,2 GB zipado), Socios0-9, Simples, e Cnaes, Municipios, Naturezas, Motivos, Paises e Qualificacoes. São CSVs sem cabeçalho, com `;`, aspas `"` e latin-1.

## Arquitetura
```
Cloud Scheduler (diário) ─► Cloud Workflows
   1. Cloud Run Job "ingest"   : discover mês → download zips → GCS landing → Parquet → GCS bronze
   2. BigQuery load jobs       : Parquet → bronze.* (partição ref_month)
   3. Cloud Run Job "dbt"      : dbt build (silver/gold + testes)
   4. registra execução em ops.ingestion_runs; falha → alerta por e-mail (Cloud Monitoring)
Looker Studio ─► gold.*
```
- **Região:** `southamerica-east1` para GCS, BigQuery, Cloud Run e Workflows.
- **GCS:**
  - `<proj>-cnpj-landing`: zips originais em `receita/ref_month=YYYY-MM/`. Lifecycle move para Archive depois de 30 dias, porque são imutáveis e servem de auditoria.
  - `<proj>-cnpj-bronze`: Parquet em `receita/<entidade>/ref_month=YYYY-MM/part-*.parquet`.
- **BigQuery:** datasets `bronze`, `silver`, `gold` e `ops`.
  - `bronze.receita_<entidade>` é uma tabela nativa particionada por `ref_month` (DATE, partição mensal), com **todas as colunas como STRING** e os metadados `_source_file`, `_ref_month`, `_ingested_at`.
  - Load jobs de GCS para BigQuery são gratuitos.
  - Expiração de partição configurável (padrão: manter 24 meses).
- **Por que conversão em streaming:** o disco do Cloud Run fica em memória, e o Estabelecimentos0 descompactado tem ~8 GB. O job lê o zip em stream (`zipfile` sobre GCS via `gcsfs`) e converte com `pyarrow.csv.open_csv` (streaming, latin-1, all string). Ele grava os row groups Parquet direto no GCS, de forma incremental, sem nunca ter o arquivo inteiro em memória. Recursos: 4 vCPU, 8–16 GB, timeout de 6 h.
- **Paralelismo:** Cloud Run Job com `--tasks N`. Cada task pega um subconjunto dos 37 arquivos a partir de `CLOUD_RUN_TASK_INDEX`.
- **Idempotência:** a tabela `ops.ingestion_files` guarda mês, arquivo, tamanho, last-modified, md5, linhas e status. Arquivos já carregados com a mesma assinatura são pulados. O load no BigQuery usa `WRITE_TRUNCATE` na partição `ref_month`, então reprocessar não duplica.
- **Detecção de mês novo:** o discover escolhe o mês mais recente com os 37 arquivos presentes e que ainda não esteja com status `loaded` em `ops`. Se não houver nada novo, o workflow termina sem custo.

## Estrutura do repositório
```
etl-pipeline-cnpj/
  README.md  Makefile  .gitignore  pyproject.toml (uv, Python 3.12)
  config/settings.yaml               # webdav url/token, buckets, região, retenção
  ingest/
    Dockerfile
    src/cnpj_ingest/
      config.py                      # pydantic-settings (env > yaml)
      cli.py                         # typer: discover | download | convert | load-bq | run
      webdav.py                      # PROPFIND + parser XML, lista meses e arquivos
      download.py                    # stream httpx → GCS resumable upload, retry (tenacity)
      convert.py                     # zip stream → pyarrow CSV reader → Parquet no GCS
      schemas.py                     # colunas por entidade (layout oficial da RFB)
      bq.py                          # load jobs particionados + escrita em ops.*
      storage.py                     # abstração GCS/local (dev local com ./data)
    tests/                           # parser PROPFIND, schemas, conversão de CSV latin-1 fixture
  dbt/
    dbt_project.yml  profiles.yml (oauth local / SA no Cloud Run)  Dockerfile
    models/sources.yml               # bronze.receita_*
    models/silver/                   # stg_* tipados + dimensões de domínio
    models/gold/                     # leads_agro, agg_leads_uf_municipio
    seeds/cnaes_alvo.csv             # 4683400, 4623108, 4692300 (editar = mudar o recorte)
  infra/terraform/
    main.tf apis.tf storage.tf bigquery.tf iam.tf artifact_registry.tf
    cloud_run_jobs.tf workflows.tf scheduler.tf monitoring.tf
    workflows/pipeline.yaml          # definição do Cloud Workflows
```

## Layout do Bronze (`schemas.py`)
- `estabelecimentos` (30): cnpj_basico, cnpj_ordem, cnpj_dv, identificador_matriz_filial, nome_fantasia, situacao_cadastral, data_situacao_cadastral, motivo_situacao_cadastral, nome_cidade_exterior, pais, data_inicio_atividade, cnae_fiscal_principal, cnae_fiscal_secundaria, tipo_logradouro, logradouro, numero, complemento, bairro, cep, uf, municipio, ddd_1, telefone_1, ddd_2, telefone_2, ddd_fax, fax, correio_eletronico, situacao_especial, data_situacao_especial
- `empresas` (7): cnpj_basico, razao_social, natureza_juridica, qualificacao_responsavel, capital_social, porte_empresa, ente_federativo_responsavel
- `socios` (11): cnpj_basico, identificador_socio, nome_socio_razao_social, cpf_cnpj_socio, qualificacao_socio, data_entrada_sociedade, pais, representante_legal, nome_do_representante, qualificacao_representante_legal, faixa_etaria
- `simples` (7): cnpj_basico, opcao_pelo_simples, data_opcao_simples, data_exclusao_simples, opcao_mei, data_opcao_mei, data_exclusao_mei
- Domínios `cnaes`, `municipios`, `naturezas`, `motivos`, `paises`, `qualificacoes` (2): codigo, descricao

## Silver / Gold (dbt, fase seguinte)
- **Silver** (incremental por `ref_month`, lendo só a partição nova):
  - `stg_estabelecimentos` tipado: CNPJ de 14 caracteres, datas `YYYYMMDD` com `00000000` virando NULL, `cnaes_secundarios` como `ARRAY<STRING>`, telefone formatado.
  - `stg_empresas` com capital como NUMERIC.
  - `stg_simples`, `stg_socios` e as dimensões de domínio.
- **Gold:**
  - `gold.leads_agro`: mês mais recente, join de estabelecimento + empresa + simples + domínios, filtrado pelo seed `cnaes_alvo` (principal OU secundário), com as colunas `match_tipo` (principal/secundário) e `cnae_match`. Clusterizado por `uf`, `municipio` e `situacao_cadastral`.
  - `gold.agg_leads_uf_municipio` para os mapas e KPIs do Looker Studio.
- **Testes dbt:** `unique` e `not_null` no cnpj, `accepted_values` na situação, e contagem de linhas bronze vs. silver.

## Custos estimados (on-demand)
- GCS: ~8 GB de zip + ~6 GB de Parquet por mês, menos de US$0,50/mês.
- BigQuery storage: ~25–35 GB lógicos por mês de bronze, ~US$0,60/mês por snapshot (cai pela metade depois de 90 dias).
- Queries: o dbt incremental lê ~30 GB/mês, dentro de 1 TB grátis. O Looker Studio lê o gold, que é pequeno.
- Cloud Run e Workflows: alguns centavos por execução. O custo é dominado pelo storage: **~US$2–5/mês** no total.

## Pré-requisitos (ação do usuário)
1. Criar um projeto GCP com billing ativo e instalar o `gcloud` e o `terraform` (`brew install --cask google-cloud-sdk && brew install terraform uv`).
2. Rodar `gcloud auth login` e `gcloud auth application-default login`.

## Ordem de implementação
1. Código do ingest e testes, rodando **localmente** com destino `local` e depois com destino GCS.
2. Terraform: APIs, buckets, datasets, service accounts (menor privilégio: o ingest com `storage.objectAdmin` nos buckets e `bigquery.dataEditor` em bronze/ops; o dbt com `dataEditor` em silver/gold e `dataViewer` em bronze), Artifact Registry, Cloud Run Jobs, Workflows, Scheduler e alerta.
3. Build e push das imagens (`gcloud builds submit`), seguidos da primeira carga manual de `2026-09`.
4. dbt silver/gold com o seed dos CNAEs.
5. Dashboard no Looker Studio conectado ao `gold` (esse passo é manual, feito na UI).

## Verificação
- `make test`: testes unitários do parser PROPFIND (XML fixture), do mapeamento de colunas e da conversão de um CSV latin-1 (acentos e `;` entre aspas).
- Smoke local: `cnpj-ingest run --month 2026-09 --only Cnaes,Municipios --target local`. Depois, no Parquet, conferir que os códigos 4683400, 4623108 e 4692300 aparecem com a descrição correta.
- Na nuvem: `gcloud run jobs execute ingest --args=run,--month=2026-09`.
  - Conferir as contagens em `ops.ingestion_files` contra `SELECT _source_file, COUNT(*) FROM bronze.receita_estabelecimentos GROUP BY 1`.
  - Rodar de novo e confirmar que tudo é pulado (idempotência).
- Workflow ponta a ponta: `gcloud workflows run cnpj-pipeline`, depois `dbt build` verde, e `SELECT uf, COUNT(*) FROM gold.leads_agro GROUP BY uf` com números plausíveis.
