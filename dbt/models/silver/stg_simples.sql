select
    cnpj_basico,
    opcao_pelo_simples = 'S' as opcao_simples,
    {{ parse_date('data_opcao_simples') }} as data_opcao_simples,
    {{ parse_date('data_exclusao_simples') }} as data_exclusao_simples,
    opcao_mei = 'S' as opcao_mei,
    {{ parse_date('data_opcao_mei') }} as data_opcao_mei,
    {{ parse_date('data_exclusao_mei') }} as data_exclusao_mei,
    _ref_month as ref_month
from {{ source('bronze', 'simples') }}
where {{ ref_month_filter(source('bronze', 'simples')) }}
