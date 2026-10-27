{#
  Estabelecimentos cujo CNAE principal OU algum secundário está no seed cnaes_alvo.
  Mantém todas as situações cadastrais (filtrar ATIVA no dashboard); o recorte
  muda editando seeds/cnaes_alvo.csv + `dbt build`.

  Ordem importa para caber na memória: primeiro filtra os ~74 mi de estabelecimentos
  numa passada só (sem unnest/join na base inteira), depois enriquece apenas os leads.
#}
with alvo as (
    select list(cast(cnae as varchar)) as cnaes from {{ ref('cnaes_alvo') }}
),

leads as (
    select
        e.*,
        list_contains(alvo.cnaes, e.cnae_principal) as match_principal,
        list_sort(list_intersect(list_append(e.cnaes_secundarios, e.cnae_principal), alvo.cnaes)) as cnaes_alvo
    from {{ ref('stg_estabelecimentos') }} e, alvo
    where list_contains(alvo.cnaes, e.cnae_principal)
       or list_has_any(e.cnaes_secundarios, alvo.cnaes)
),

empresas as (
    select * from {{ ref('stg_empresas') }}
    where cnpj_basico in (select cnpj_basico from leads)
),

simples as (
    select * from {{ ref('stg_simples') }}
    where cnpj_basico in (select cnpj_basico from leads)
)

select
    e.cnpj,
    e.cnpj_basico,
    emp.razao_social,
    e.nome_fantasia,
    e.matriz_filial,
    e.situacao_cadastral,
    e.situacao_cadastral = 'ATIVA' as is_ativa,
    e.data_situacao_cadastral,
    mot.descricao as motivo_situacao,
    e.data_inicio_atividade,
    case when e.match_principal then 'principal' else 'secundario' end as match_tipo,
    e.cnaes_alvo,
    e.cnae_principal,
    cn.descricao as cnae_principal_descricao,
    e.cnaes_secundarios,
    emp.porte,
    emp.capital_social,
    nat.descricao as natureza_juridica,
    coalesce(sim.opcao_simples, false) as opcao_simples,
    coalesce(sim.opcao_mei, false) as opcao_mei,
    e.logradouro,
    e.numero,
    e.complemento,
    e.bairro,
    e.cep,
    e.uf,
    e.municipio_codigo,
    mun.descricao as municipio,
    e.telefone_1,
    e.telefone_2,
    e.email,
    e.ref_month
from leads e
left join empresas emp on emp.cnpj_basico = e.cnpj_basico
left join simples sim on sim.cnpj_basico = e.cnpj_basico
left join {{ ref('stg_cnaes') }} cn on cn.codigo = e.cnae_principal
left join {{ ref('stg_municipios') }} mun on mun.codigo = e.municipio_codigo
left join {{ ref('stg_naturezas') }} nat on nat.codigo = emp.natureza_juridica_codigo
left join {{ ref('stg_motivos') }} mot on mot.codigo = e.motivo_situacao_codigo
