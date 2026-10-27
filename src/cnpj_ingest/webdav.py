"""Listagem do WebDAV público da Receita (Nextcloud) via PROPFIND."""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime
from urllib.parse import unquote

import httpx
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .schemas import EXPECTED_FILES

log = logging.getLogger(__name__)
NS = {"d": "DAV:"}
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    is_dir: bool
    size: int | None
    etag: str | None
    last_modified: datetime | None


def parse_propfind(xml_text: str) -> list[RemoteEntry]:
    """Converte a resposta multistatus em entradas, ignorando a própria pasta consultada."""
    root = ET.fromstring(xml_text)
    entries = []
    for i, resp in enumerate(root.findall("d:response", NS)):
        if i == 0:  # a primeira entrada é a própria coleção
            continue
        href = unquote(resp.findtext("d:href", default="", namespaces=NS))
        prop = resp.find("d:propstat/d:prop", NS)
        is_dir = prop is not None and prop.find("d:resourcetype/d:collection", NS) is not None
        size = prop.findtext("d:getcontentlength", namespaces=NS) if prop is not None else None
        etag = prop.findtext("d:getetag", namespaces=NS) if prop is not None else None
        modified = prop.findtext("d:getlastmodified", namespaces=NS) if prop is not None else None
        entries.append(
            RemoteEntry(
                name=href.rstrip("/").rsplit("/", 1)[-1],
                is_dir=is_dir,
                size=int(size) if size else None,
                etag=etag.strip('"') if etag else None,
                last_modified=parsedate_to_datetime(modified) if modified else None,
            )
        )
    return entries


class ReceitaWebDAV:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.auth = (token, "")
        self.client = client or httpx.Client(timeout=httpx.Timeout(60, connect=30), follow_redirects=True)

    def url(self, *parts: str) -> str:
        return "/".join([self.base_url, *parts])

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=3, max=60),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _propfind(self, path: str) -> list[RemoteEntry]:
        r = self.client.request("PROPFIND", self.url(path) + "/", headers={"Depth": "1"}, auth=self.auth)
        r.raise_for_status()
        return parse_propfind(r.text)

    def list_months(self) -> list[str]:
        return sorted(e.name for e in self._propfind("") if e.is_dir and MONTH_RE.match(e.name))

    def list_files(self, month: str) -> list[RemoteEntry]:
        return sorted((e for e in self._propfind(month) if not e.is_dir), key=lambda e: e.name)

    def latest_complete_month(self) -> tuple[str, list[RemoteEntry]]:
        """Mês mais recente que já tem os 37 arquivos publicados."""
        for month in reversed(self.list_months()):
            files = self.list_files(month)
            if EXPECTED_FILES <= {f.name for f in files}:
                return month, files
        raise RuntimeError("Nenhum mês completo encontrado no WebDAV da Receita")
