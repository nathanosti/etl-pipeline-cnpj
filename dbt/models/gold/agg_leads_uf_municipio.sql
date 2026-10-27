select
    uf,
    municipio_codigo,
    municipio,
    situacao_cadastral,
    match_tipo,
    porte,
    count(*) as estabelecimentos,
    count(*) filter (where email is not null) as com_email,
    count(*) filter (where telefone_1 is not null or telefone_2 is not null) as com_telefone,
    any_value(ref_month) as ref_month
from {{ ref('leads_agro') }}
group by all
