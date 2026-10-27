"""Layout oficial dos arquivos de dados abertos do CNPJ (CSV sem cabeçalho, ';', latin-1).

No bronze tudo é STRING: a tipagem acontece na camada silver (dbt).
"""

import re

DOMAIN_COLUMNS = ["codigo", "descricao"]

COLUMNS: dict[str, list[str]] = {
    "empresas": [
        "cnpj_basico",
        "razao_social",
        "natureza_juridica",
        "qualificacao_responsavel",
        "capital_social",
        "porte_empresa",
        "ente_federativo_responsavel",
    ],
    "estabelecimentos": [
        "cnpj_basico",
        "cnpj_ordem",
        "cnpj_dv",
        "identificador_matriz_filial",
        "nome_fantasia",
        "situacao_cadastral",
        "data_situacao_cadastral",
        "motivo_situacao_cadastral",
        "nome_cidade_exterior",
        "pais",
        "data_inicio_atividade",
        "cnae_fiscal_principal",
        "cnae_fiscal_secundaria",
        "tipo_logradouro",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "cep",
        "uf",
        "municipio",
        "ddd_1",
        "telefone_1",
        "ddd_2",
        "telefone_2",
        "ddd_fax",
        "fax",
        "correio_eletronico",
        "situacao_especial",
        "data_situacao_especial",
    ],
    "socios": [
        "cnpj_basico",
        "identificador_socio",
        "nome_socio_razao_social",
        "cpf_cnpj_socio",
        "qualificacao_socio",
        "data_entrada_sociedade",
        "pais",
        "representante_legal",
        "nome_do_representante",
        "qualificacao_representante_legal",
        "faixa_etaria",
    ],
    "simples": [
        "cnpj_basico",
        "opcao_pelo_simples",
        "data_opcao_simples",
        "data_exclusao_simples",
        "opcao_mei",
        "data_opcao_mei",
        "data_exclusao_mei",
    ],
    "cnaes": DOMAIN_COLUMNS,
    "municipios": DOMAIN_COLUMNS,
    "naturezas": DOMAIN_COLUMNS,
    "motivos": DOMAIN_COLUMNS,
    "paises": DOMAIN_COLUMNS,
    "qualificacoes": DOMAIN_COLUMNS,
}

# Arquivos particionados em 10 partes (Empresas0..9 etc.)
PARTITIONED = ("Empresas", "Estabelecimentos", "Socios")
SINGLE = ("Simples", "Cnaes", "Municipios", "Naturezas", "Motivos", "Paises", "Qualificacoes")

EXPECTED_FILES: frozenset[str] = frozenset(
    [f"{p}{i}.zip" for p in PARTITIONED for i in range(10)] + [f"{s}.zip" for s in SINGLE]
)

_NAME_RE = re.compile(r"^([A-Za-z]+?)(\d*)\.zip$")


def entity_for(filename: str) -> str:
    """'Estabelecimentos3.zip' -> 'estabelecimentos'."""
    m = _NAME_RE.match(filename)
    if not m or m.group(1).lower() not in COLUMNS:
        raise ValueError(f"Arquivo desconhecido: {filename}")
    return m.group(1).lower()
