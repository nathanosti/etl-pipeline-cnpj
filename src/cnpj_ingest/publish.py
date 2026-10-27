"""Publica a gold (DuckDB local) no BigQuery para Looker Studio / Power BI.

Funciona no BigQuery Sandbox (sem billing): só usa load jobs, que são gratuitos.
No Sandbox as tabelas expiram em 60 dias; cada publicação recria e renova o prazo.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)

# tabela no DuckDB -> nome no BigQuery
TABLES = {
    "gold.leads_agro": "leads_agro",
    "gold.agg_leads_uf_municipio": "agg_leads_uf_municipio",
    "gold.leads_socios": "leads_socios",
    "ref.cnaes_alvo": "cnaes_alvo",
}


@dataclass(frozen=True)
class Published:
    table_id: str
    rows: int


def gcloud_credentials(account: str | None = None):
    """Credenciais da conta ativa do `gcloud` (não das Application Default Credentials).

    Evita depender do ADC da máquina, que pode estar em outra conta Google.
    O token vale ~1h, mais que suficiente para uma publicação.
    """
    from google.oauth2.credentials import Credentials

    gcloud = shutil.which("gcloud")
    if not gcloud:
        raise RuntimeError("gcloud não encontrado: instale com `brew install --cask google-cloud-sdk`")
    cmd = [gcloud, "auth", "print-access-token"] + ([f"--account={account}"] if account else [])
    token = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
    return Credentials(token)


def export_parquet(db_path: Path, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    with duckdb.connect(str(db_path), read_only=True) as con:
        for src, name in TABLES.items():
            path = out_dir / f"{name}.parquet"
            con.execute(f"copy {src} to '{path}' (format parquet, compression zstd)")
            files[name] = path
    return files


def publish(db_path: Path, work_dir: Path, project: str, dataset: str, location: str,
            account: str | None = None) -> list[Published]:
    from google.cloud import bigquery

    client = bigquery.Client(project=project, credentials=gcloud_credentials(account), location=location)
    ds = bigquery.Dataset(f"{project}.{dataset}")
    ds.location = location
    ds.description = "Prospecção agro: gold publicada a partir do pipeline local (etl-pipeline-cnpj)"
    client.create_dataset(ds, exists_ok=True)

    parquet_opts = bigquery.ParquetOptions()
    parquet_opts.enable_list_inference = True  # listas do DuckDB viram ARRAY<STRING>, não STRUCT
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        parquet_options=parquet_opts,
    )

    results = []
    for name, path in export_parquet(db_path, work_dir).items():
        table_id = f"{project}.{dataset}.{name}"
        with open(path, "rb") as f:
            client.load_table_from_file(f, table_id, job_config=job_config).result()
        table = client.get_table(table_id)
        log.info("publicado %s: %d linhas%s", table_id, table.num_rows,
                 f" (expira em {table.expires:%d/%m/%Y})" if table.expires else "")
        results.append(Published(table_id, table.num_rows))
    shutil.rmtree(work_dir, ignore_errors=True)
    return results
