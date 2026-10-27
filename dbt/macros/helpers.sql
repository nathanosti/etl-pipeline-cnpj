{# Usa o nome do schema configurado (silver, gold, ref) sem prefixar o schema do target. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}

{# Filtro do snapshot: var ref_month ou o mês mais recente da própria fonte. #}
{% macro ref_month_filter(relation) -%}
    {%- if var('ref_month') -%}
        _ref_month = '{{ var("ref_month") }}'
    {%- else -%}
        _ref_month = (select max(_ref_month) from {{ relation }})
    {%- endif -%}
{%- endmacro %}

{# Datas da Receita vêm como YYYYMMDD; '0', '00000000' e vazio viram NULL. #}
{% macro parse_date(col) -%}
    try_strptime(nullif(nullif(trim({{ col }}), ''), '00000000'), '%Y%m%d')::date
{%- endmacro %}

{% macro clean(col) -%}
    nullif(trim({{ col }}), '')
{%- endmacro %}

{# Tabelas de domínio (código, descrição) têm todas o mesmo formato. #}
{% macro stg_domain(source_name) -%}
select
    trim(codigo) as codigo,
    trim(descricao) as descricao,
    _ref_month as ref_month
from {{ source('bronze', source_name) }}
where {{ ref_month_filter(source('bronze', source_name)) }}
{%- endmacro %}
