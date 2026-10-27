export CNPJ_DATA_DIR ?= $(CURDIR)/data
DBT_FLAGS = --project-dir dbt --profiles-dir dbt

.PHONY: setup test ingest ingest-smoke dbt pipeline dash status

setup:
	uv sync

test:
	uv run pytest -q

# Mês completo mais recente (ou MONTH=YYYY-MM)
ingest:
	uv run cnpj-ingest run $(if $(MONTH),--month $(MONTH))

# Só as tabelas de domínio (poucos KB) para validar o fluxo
ingest-smoke:
	uv run cnpj-ingest run --only Cnaes,Municipios,Naturezas,Motivos,Paises,Qualificacoes

dbt:
	uv run dbt build $(DBT_FLAGS) --full-refresh $(if $(MONTH),--vars '{ref_month: "$(MONTH)"}')

pipeline: ingest dbt

# Painel local em http://localhost:8501
dash:
	uv run --group dash streamlit run dashboard/app.py

status:
	uv run cnpj-ingest files $(if $(MONTH),--month $(MONTH))
