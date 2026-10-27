import os
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "settings.yaml"


@dataclass(frozen=True)
class Settings:
    webdav_url: str
    webdav_token: str
    data_dir: Path
    download_workers: int = 4
    convert_workers: int = 4
    delete_zips_after_convert: bool = False
    bq_project: str | None = None
    bq_dataset: str = "gold"
    bq_location: str = "southamerica-east1"
    bq_account: str | None = None

    @property
    def landing_dir(self) -> Path:
        return self.data_dir / "landing" / "receita"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze" / "receita"

    @property
    def ops_dir(self) -> Path:
        return self.data_dir / "ops"


def load_settings(path: Path = DEFAULT_CONFIG) -> Settings:
    """yaml < variáveis de ambiente CNPJ_<CHAVE>."""
    raw = yaml.safe_load(path.read_text()) if path.exists() else {}
    values = {}
    for f in fields(Settings):
        value = os.environ.get(f"CNPJ_{f.name.upper()}", raw.get(f.name))
        if value is None:
            continue
        if f.type in (int, "int"):
            value = int(value)
        elif f.type in (bool, "bool") and isinstance(value, str):
            value = value.lower() in ("1", "true", "yes", "sim")
        values[f.name] = value

    data_dir = Path(values.get("data_dir", "./data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    values["data_dir"] = data_dir.resolve()
    values["webdav_url"] = values["webdav_url"].rstrip("/")
    return Settings(**values)
