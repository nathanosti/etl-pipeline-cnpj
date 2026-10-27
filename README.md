# ETL CNPJ — prospecção agro

Pipeline dos dados abertos de CNPJ da Receita Federal para prospectar clientes por CNAE
(hoje: 4683-4/00, 4623-1/08, 4692-3/00 — principal **ou** secundário).

A base **inteira** é ingerida; o recorte por CNAE só acontece na gold, a partir de
`dbt/seeds/cnaes_alvo.csv`. Mudar o público = editar o seed e rodar `make dbt`.

## Fase 1 (atual): local, sem nuvem paga

```
Receita (WebDAV, zips mensais ~7,8 GB)
  └─ cnpj-ingest ─► data/landing/receita/ref_month=YYYY-MM/*.zip      (originais)
                 └► data/bronze/receita/<entidade>/ref_month=YYYY-MM/*.parquet  (tudo STRING)
  └─ dbt + DuckDB ─► data/warehouse.duckdb
                      silver.stg_*            (views tipadas, snapshot do mês)
                      gold.leads_agro         (recorte pelos CNAEs alvo)
                      gold.agg_leads_uf_municipio
                      gold.leads_socios       (quadro societário dos leads)
  └─ Streamlit ─► dashboard/app.py  (painel local, lê a gold)
```

A gold também é publicada no BigQuery Sandbox (gratuito, projeto `echo-lead`, dataset `gold`,
`southamerica-east1`) para Looker Studio / Power BI: `make publish`.
O desenho completo para quando houver GCP com billing está em [docs/PLANO_ETL_GCP.md](docs/PLANO_ETL_GCP.md).

## Uso

Requer [uv](https://docs.astral.sh/uv/) (`brew install uv`). Espaço: ~15 GB por mês (zips + Parquet);
use `--delete-zips` ou `delete_zips_after_convert: true` para ficar em ~7 GB.

```bash
make setup          # instala dependências (Python 3.12 via uv)
make test           # testes unitários
make ingest-smoke   # só tabelas de domínio, segundos
make ingest         # mês completo mais recente (ou MONTH=2026-10)
make dbt            # silver + gold + testes
make status         # arquivos do mês e status no manifesto
make dash           # painel local em http://localhost:8501
make publish        # envia a gold para o BigQuery (config/settings.yaml)
```

A ingestão é idempotente: o manifesto `data/ops/ingestion_files.json` guarda etag/tamanho
de cada arquivo, então rodar de novo só processa o que mudou. Downloads interrompidos são
retomados (HTTP Range).

Consultar direto:

```bash
uv run python -c "import duckdb; print(duckdb.connect('data/warehouse.duckdb', read_only=True).sql(
  'select uf, count(*) n from gold.leads_agro where is_ativa group by 1 order by 2 desc'))"
```

(ou abra `data/warehouse.duckdb` no DBeaver / CLI do DuckDB, `brew install duckdb`).

## Painel (`make dash`)

- **Filtros:** situação (padrão ATIVA), CNAE alvo como principal/secundário, CNAE, UF, município,
  porte, matriz/filial, Simples, exigir e-mail/telefone, ano de abertura.
- **KPIs:** estabelecimentos, empresas (CNPJ raiz), % com e-mail, % com telefone, abertas em 12 meses.
- **Mercado:** leads por UF (principal × secundário), top 15 municípios, por CNAE, por porte, aberturas por ano.
- **Lista de leads:** busca, export CSV (abre no Excel), e ficha ao clicar numa linha com
  dados cadastrais, contato, quadro societário e outros estabelecimentos da mesma empresa.

O painel abre o DuckDB em modo leitura só durante cada consulta, então dá para rodar
`make dbt` com ele aberto (depois, recarregue o cache com a tecla `C` no painel).

## BigQuery (`make publish`)

Exporta `gold.leads_agro`, `gold.agg_leads_uf_municipio`, `gold.leads_socios` e `ref.cnaes_alvo`
do DuckDB para Parquet e carrega no BigQuery com load jobs (gratuitos, `WRITE_TRUNCATE`).

- Autentica com a **conta ativa do `gcloud`** (`gcloud auth login`), não com as Application
  Default Credentials, que podem estar em outra conta. Para fixar a conta: `bq_account` no settings.
- No Sandbox as tabelas expiram em **60 dias**; cada `make publish` recria e renova o prazo.
- Também cria as views `vw_leads` (sem ARRAY, com `uf_iso` para mapa) e `vw_leads_cnae`
  (uma linha por lead × CNAE alvo), pensadas para Looker Studio / Power BI.

## Compartilhar o painel

**Looker Studio** (sem código): lookerstudio.google.com → Criar → Fonte de dados → BigQuery →
`echo-lead` → `gold` → `vw_leads`. Deixe a credencial como "Proprietário" para quem recebe o
link não precisar de acesso ao BigQuery. Compartilhe o relatório por e-mail.

**Streamlit Community Cloud** (o mesmo painel deste repo, 1 app privado grátis):

1. `bash scripts/setup_streamlit_sa.sh` — cria a conta de serviço só-leitura no dataset `gold`
   e gera `data/secrets/streamlit_secrets.toml` (fora do Git).
2. share.streamlit.io → entrar com o GitHub → Create app → repo `etl-pipeline-cnpj`, branch
   `main`, arquivo `dashboard/app.py`; em Advanced settings: Python 3.12 e cole o conteúdo do
   `streamlit_secrets.toml` em Secrets.
3. No app: Share → convide os e-mails do time (o app herda o privado do repositório).

Com os secrets presentes o painel lê do BigQuery; sem eles, do DuckDB local.

## Observações sobre os dados

- `municipio_codigo` é o código da Receita (TOM), **não** o código IBGE.
- Situação cadastral: 01 NULA, 02 ATIVA, 03 SUSPENSA, 04 INAPTA, 08 BAIXADA.
- Linhas malformadas são puladas e contadas no manifesto (`invalid_rows`, com amostra).
