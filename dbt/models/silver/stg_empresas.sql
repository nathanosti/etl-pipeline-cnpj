select
    cnpj_basico,
    trim(razao_social) as razao_social,
    {{ clean('natureza_juridica') }} as natureza_juridica_codigo,
    {{ clean('qualificacao_responsavel') }} as qualificacao_responsavel_codigo,
    try_cast(replace(capital_social, ',', '.') as decimal(18, 2)) as capital_social,
    lpad(porte_empresa, 2, '0') as porte_codigo,
    case lpad(porte_empresa, 2, '0')
        when '00' then 'NAO INFORMADO'
        when '01' then 'MICRO EMPRESA'
        when '03' then 'EMPRESA DE PEQUENO PORTE'
        when '05' then 'DEMAIS'
    end as porte,
    {{ clean('ente_federativo_responsavel') }} as ente_federativo_responsavel,
    _ref_month as ref_month
from {{ source('bronze', 'empresas') }}
where {{ ref_month_filter(source('bronze', 'empresas')) }}
