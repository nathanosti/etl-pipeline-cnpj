"""zip da Receita -> Parquet (bronze), em streaming: o CSV nunca é extraído para disco."""

import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .schemas import COLUMNS

BLOCK_SIZE = 32 << 20  # 32 MB por bloco de leitura


@dataclass(frozen=True)
class ConvertResult:
    rows: int
    invalid_rows: int
    invalid_sample: list[str]


def convert_zip(zip_path: Path, entity: str, out_path: Path, ref_month: str) -> ConvertResult:
    columns = COLUMNS[entity]
    invalid: list[str] = []

    def on_invalid(row: pacsv.InvalidRow) -> str:
        invalid.append(row.text)
        return "skip"

    read_opts = pacsv.ReadOptions(column_names=columns, encoding="latin1", block_size=BLOCK_SIZE)
    parse_opts = pacsv.ParseOptions(delimiter=";", quote_char='"', invalid_row_handler=on_invalid)
    convert_opts = pacsv.ConvertOptions(column_types={c: pa.string() for c in columns})

    schema = pa.schema(
        [(c, pa.string()) for c in columns]
        + [
            ("_source_file", pa.string()),
            ("_ref_month", pa.string()),
            ("_ingested_at", pa.timestamp("us", tz="UTC")),
        ]
    )
    ingested_at = datetime.now(timezone.utc)
    source_file = zip_path.name

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    rows = 0

    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name}: esperado 1 arquivo no zip, encontrado {len(members)}")
        with zf.open(members[0]) as raw, pq.ParquetWriter(tmp_path, schema, compression="zstd") as writer:
            reader = pacsv.open_csv(raw, read_options=read_opts, parse_options=parse_opts, convert_options=convert_opts)
            for batch in reader:
                n = batch.num_rows
                if n == 0:
                    continue
                extra = [
                    pa.array([source_file] * n, pa.string()),
                    pa.array([ref_month] * n, pa.string()),
                    pa.array([ingested_at] * n, pa.timestamp("us", tz="UTC")),
                ]
                writer.write_batch(pa.RecordBatch.from_arrays(batch.columns + extra, schema=schema))
                rows += n

    tmp_path.replace(out_path)
    return ConvertResult(rows=rows, invalid_rows=len(invalid), invalid_sample=invalid[:5])
