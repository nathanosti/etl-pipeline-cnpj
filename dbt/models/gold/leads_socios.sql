{# Quadro societário das empresas que estão em leads_agro (para achar o decisor). #}
select
    s.cnpj_basico,
    s.tipo_socio,
    s.nome_socio,
    q.descricao as qualificacao,
    s.data_entrada_sociedade,
    case s.faixa_etaria_codigo
        when '1' then '0-12' when '2' then '13-20' when '3' then '21-30'
        when '4' then '31-40' when '5' then '41-50' when '6' then '51-60'
        when '7' then '61-70' when '8' then '71-80' when '9' then '80+'
    end as faixa_etaria,
    s.ref_month
from {{ ref('stg_socios') }} s
left join {{ ref('stg_qualificacoes') }} q on q.codigo = s.qualificacao_socio_codigo
where s.cnpj_basico in (select cnpj_basico from {{ ref('leads_agro') }})
