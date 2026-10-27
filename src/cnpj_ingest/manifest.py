"""Manifesto de ingestão (ops): o que foi baixado/convertido, com assinatura do arquivo remoto.

Equivalente local da tabela ops.ingestion_files do plano GCP. Garante idempotência:
arquivo com mesmo etag/tamanho já convertido é pulado.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}

    def get(self, month: str, filename: str) -> dict:
        return self.data.get(month, {}).get(filename, {})

    def update(self, month: str, filename: str, **fields) -> None:
        with self._lock:
            entry = self.data.setdefault(month, {}).setdefault(filename, {})
            entry.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False, default=str))
            tmp.replace(self.path)

    def is_converted(self, month: str, filename: str, etag: str | None, size: int | None) -> bool:
        e = self.get(month, filename)
        return e.get("status") == "converted" and e.get("etag") == etag and e.get("size") == size
