from datetime import datetime, timezone

from cnpj_ingest.schemas import EXPECTED_FILES, entity_for
from cnpj_ingest.webdav import parse_propfind

PROPFIND_XML = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
 <d:response><d:href>/public.php/webdav/2026-10/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
 <d:response><d:href>/public.php/webdav/2026-10/Cnaes.zip</d:href>
  <d:propstat><d:prop>
   <d:getlastmodified>Tue, 13 Oct 2026 22:00:16 GMT</d:getlastmodified>
   <d:getcontentlength>22078</d:getcontentlength><d:resourcetype/>
   <d:getetag>&quot;17e2f9b2f51164f0e35a0e6011551c63&quot;</d:getetag>
  </d:prop></d:propstat></d:response>
 <d:response><d:href>/public.php/webdav/2026-11/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
</d:multistatus>"""


def test_parse_propfind_skips_self_and_reads_props():
    entries = parse_propfind(PROPFIND_XML)
    assert [e.name for e in entries] == ["Cnaes.zip", "2026-11"]
    cnaes, folder = entries
    assert not cnaes.is_dir and folder.is_dir
    assert cnaes.size == 22078
    assert cnaes.etag == "17e2f9b2f51164f0e35a0e6011551c63"
    assert cnaes.last_modified == datetime(2026, 10, 13, 22, 0, 16, tzinfo=timezone.utc)


def test_expected_files_and_entities():
    assert len(EXPECTED_FILES) == 37
    assert entity_for("Estabelecimentos3.zip") == "estabelecimentos"
    assert entity_for("Simples.zip") == "simples"
    assert entity_for("Qualificacoes.zip") == "qualificacoes"
