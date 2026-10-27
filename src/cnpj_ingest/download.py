"""Download dos zips com retomada (HTTP Range) e retry."""

import logging
from pathlib import Path

import httpx
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class IncompleteDownload(Exception):
    pass


# O servidor da Receita costuma congelar ou derrubar conexões no meio do arquivo
_REASONS = {
    httpx.ReadTimeout: "servidor parou de enviar dados por 60s",
    httpx.RemoteProtocolError: "servidor fechou a conexão no meio do arquivo",
    httpx.ConnectError: "não conectou ao servidor",
    httpx.ConnectTimeout: "não conectou ao servidor",
    IncompleteDownload: "download terminou incompleto",
}


def _log_retry(state: RetryCallState) -> None:
    params = dict(zip(("client", "url", "auth", "dest", "expected_size"), state.args)) | state.kwargs
    dest, expected = params["dest"], params["expected_size"]
    part = dest.with_name(dest.name + ".part")
    got = part.stat().st_size if part.exists() else 0
    exc = state.outcome.exception()
    reason = _REASONS.get(type(exc), type(exc).__name__)
    log.warning(
        "%s: tentativa %d falhou (%s) com %.0f%% baixado (%.2f/%.2f GB); retomando em %.0fs",
        dest.name, state.attempt_number, reason, 100 * got / expected if expected else 0,
        got / 1e9, expected / 1e9, state.next_action.sleep,
    )
    log.debug("%s: detalhe do erro: %r", dest.name, exc)


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, IncompleteDownload)),
    stop=stop_after_attempt(8),
    wait=wait_exponential(multiplier=5, max=120),
    before_sleep=_log_retry,
    reraise=True,
)
def download_file(client: httpx.Client, url: str, auth: tuple[str, str], dest: Path, expected_size: int) -> bool:
    """Baixa `url` em `dest`. Retorna False se o arquivo já existia com o tamanho esperado."""
    if dest.exists() and dest.stat().st_size == expected_size:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    pos = part.stat().st_size if part.exists() else 0
    if pos > expected_size:
        part.unlink()
        pos = 0
    headers = {"Range": f"bytes={pos}-"} if pos else {}

    with client.stream("GET", url, auth=auth, headers=headers) as r:
        if pos and r.status_code != 206:  # servidor ignorou o Range: recomeça do zero
            pos = 0
        r.raise_for_status()
        with open(part, "ab" if pos else "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)

    got = part.stat().st_size
    if got != expected_size:
        raise IncompleteDownload(f"{dest.name}: {got} de {expected_size} bytes")
    part.rename(dest)
    return True
