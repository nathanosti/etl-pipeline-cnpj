with src as (
    select *
    from {{ source('bronze', 'estabelecimentos') }}
    where {{ ref_month_filter(source('bronze', 'estabelecimentos')) }}
)

select
    cnpj_basico || cnpj_ordem || cnpj_dv as cnpj,
    cnpj_basico,
    case identificador_matriz_filial when '1' then 'MATRIZ' when '2' then 'FILIAL' end as matriz_filial,
    {{ clean('nome_fantasia') }} as nome_fantasia,
    lpad(situacao_cadastral, 2, '0') as situacao_cadastral_codigo,
    case lpad(situacao_cadastral, 2, '0')
        when '01' then 'NULA'
        when '02' then 'ATIVA'
        when '03' then 'SUSPENSA'
        when '04' then 'INAPTA'
        when '08' then 'BAIXADA'
    end as situacao_cadastral,
    {{ parse_date('data_situacao_cadastral') }} as data_situacao_cadastral,
    {{ clean('motivo_situacao_cadastral') }} as motivo_situacao_codigo,
    {{ parse_date('data_inicio_atividade') }} as data_inicio_atividade,
    {{ clean('cnae_fiscal_principal') }} as cnae_principal,
    case
        when {{ clean('cnae_fiscal_secundaria') }} is null then []::varchar[]
        else string_split(cnae_fiscal_secundaria, ',')
    end as cnaes_secundarios,
    concat_ws(' ', {{ clean('tipo_logradouro') }}, {{ clean('logradouro') }}) as logradouro,
    {{ clean('numero') }} as numero,
    {{ clean('complemento') }} as complemento,
    {{ clean('bairro') }} as bairro,
    {{ clean('cep') }} as cep,
    {{ clean('uf') }} as uf,
    {{ clean('municipio') }} as municipio_codigo,
    {{ clean('pais') }} as pais_codigo,
    {{ clean('nome_cidade_exterior') }} as cidade_exterior,
    case when {{ clean('telefone_1') }} is not null then concat_ws('', trim(ddd_1), trim(telefone_1)) end as telefone_1,
    case when {{ clean('telefone_2') }} is not null then concat_ws('', trim(ddd_2), trim(telefone_2)) end as telefone_2,
    lower({{ clean('correio_eletronico') }}) as email,
    {{ clean('situacao_especial') }} as situacao_especial,
    {{ parse_date('data_situacao_especial') }} as data_situacao_especial,
    _ref_month as ref_month
from src
