import logging

import httpx
from tenacity import wait_none

from cnpj_ingest.download import download_file

PAYLOAD = b"0123456789" * 100


def test_download_resumes_after_stall_and_logs_reason(tmp_path, caplog):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("range"))
        if len(calls) == 1:
            raise httpx.ReadTimeout("The read operation timed out", request=request)
        start = int(request.headers["range"].removeprefix("bytes=").rstrip("-")) if "range" in request.headers else 0
        return httpx.Response(206 if start else 200, content=PAYLOAD[start:])

    dest = tmp_path / "Cnaes.zip"
    # simula um .part de uma tentativa anterior
    dest.with_name("Cnaes.zip.part").write_bytes(PAYLOAD[:300])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with caplog.at_level(logging.WARNING):
        fresh = download_file.retry_with(wait=wait_none())(client, "https://x/Cnaes.zip", ("t", ""), dest, len(PAYLOAD))

    assert fresh is True
    assert dest.read_bytes() == PAYLOAD
    assert calls == ["bytes=300-", "bytes=300-"]  # retomou do ponto parado, nas duas tentativas
    assert "servidor parou de enviar dados por 60s" in caplog.text
    assert "30% baixado" in caplog.text


def test_download_skips_existing_file(tmp_path):
    dest = tmp_path / "Cnaes.zip"
    dest.write_bytes(PAYLOAD)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert download_file(client, "https://x/Cnaes.zip", ("t", ""), dest, len(PAYLOAD)) is False
