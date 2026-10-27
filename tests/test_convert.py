import zipfile

import pyarrow.parquet as pq

from cnpj_ingest.convert import convert_zip


def _make_zip(tmp_path, content: str):
    zip_path = tmp_path / "Cnaes.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("F.K03200$Z.D61011.CNAECSV", content.encode("latin-1"))
    return zip_path


def test_convert_latin1_quoted_semicolons(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        '"4683400";"Comércio atacadista de defensivos agrícolas, adubos, fertilizantes e corretivos do solo"\n'
        '"0000001";"Descrição com ; dentro das aspas"\n',
    )
    out = tmp_path / "out" / "Cnaes.parquet"
    result = convert_zip(zip_path, "cnaes", out, "2026-10")

    assert result.rows == 2 and result.invalid_rows == 0
    table = pq.read_table(out)
    assert table.column_names[:2] == ["codigo", "descricao"]
    rows = table.to_pylist()
    assert rows[0]["codigo"] == "4683400"  # continua string, sem perder zeros
    assert rows[0]["descricao"].startswith("Comércio atacadista")
    assert rows[1]["descricao"] == "Descrição com ; dentro das aspas"
    assert rows[0]["_source_file"] == "Cnaes.zip"
    assert rows[0]["_ref_month"] == "2026-10"
    assert not (tmp_path / "out" / "Cnaes.parquet.tmp").exists()


def test_convert_skips_invalid_rows(tmp_path):
    zip_path = _make_zip(tmp_path, '"01";"ok"\n"02";"a mais";"coluna"\n"03";"ok"\n')
    result = convert_zip(zip_path, "cnaes", tmp_path / "x.parquet", "2026-10")
    assert result.rows == 2
    assert result.invalid_rows == 1
    assert "coluna" in result.invalid_sample[0]
