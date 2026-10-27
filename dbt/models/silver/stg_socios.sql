select
    cnpj_basico,
    case identificador_socio
        when '1' then 'PESSOA JURIDICA'
        when '2' then 'PESSOA FISICA'
        when '3' then 'ESTRANGEIRO'
    end as tipo_socio,
    trim(nome_socio_razao_social) as nome_socio,
    {{ clean('cpf_cnpj_socio') }} as cpf_cnpj_socio,
    {{ clean('qualificacao_socio') }} as qualificacao_socio_codigo,
    {{ parse_date('data_entrada_sociedade') }} as data_entrada_sociedade,
    {{ clean('pais') }} as pais_codigo,
    {{ clean('nome_do_representante') }} as nome_representante,
    {{ clean('faixa_etaria') }} as faixa_etaria_codigo,
    _ref_month as ref_month
from {{ source('bronze', 'socios') }}
where {{ ref_month_filter(source('bronze', 'socios')) }}
