"""CLI da ingestão: Receita (WebDAV) -> landing (zips) -> bronze (Parquet)."""

import logging
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path

import typer

from .config import load_settings
from .convert import convert_zip
from .download import download_file
from .manifest import Manifest
from .schemas import EXPECTED_FILES, entity_for
from .webdav import ReceitaWebDAV, RemoteEntry

app = typer.Typer(help="Ingestão dos dados abertos de CNPJ da Receita Federal", no_args_is_help=True)
log = logging.getLogger("cnpj_ingest")


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _gb(n: int) -> str:
    return f"{n / 1e9:.2f} GB"


def _select(files: list[RemoteEntry], only: str | None) -> list[RemoteEntry]:
    """Filtra pelos prefixos de --only (ex.: 'Cnaes,Municipios,Estabelecimentos0')."""
    files = [f for f in files if f.name in EXPECTED_FILES]
    if not only:
        return files
    prefixes = [p.strip().lower() for p in only.split(",") if p.strip()]
    return [f for f in files if any(f.name.lower().startswith(p) for p in prefixes)]


def _resolve_month(dav: ReceitaWebDAV, month: str | None) -> tuple[str, list[RemoteEntry]]:
    if month:
        return month, dav.list_files(month)
    return dav.latest_complete_month()


@app.command()
def months() -> None:
    """Lista os meses publicados pela Receita."""
    s = load_settings()
    for m in ReceitaWebDAV(s.webdav_url, s.webdav_token).list_months():
        typer.echo(m)


@app.command()
def files(month: str = typer.Option(None, help="YYYY-MM (padrão: mês completo mais recente)")) -> None:
    """Lista os arquivos de um mês e o status local de cada um."""
    s = load_settings()
    dav = ReceitaWebDAV(s.webdav_url, s.webdav_token)
    month, remote = _resolve_month(dav, month)
    manifest = Manifest(s.ops_dir / "ingestion_files.json")
    typer.echo(f"Mês {month}")
    for f in remote:
        status = manifest.get(month, f.name).get("status", "-")
        typer.echo(f"  {f.name:<24} {_gb(f.size or 0):>10}  {status}")
    typer.echo(f"Total: {_gb(sum(f.size or 0 for f in remote))}")


def _convert_job(zip_path: str, entity: str, out_path: str, month: str):
    # roda em outro processo: devolve só tipos simples
    r = convert_zip(Path(zip_path), entity, Path(out_path), month)
    return r.rows, r.invalid_rows, r.invalid_sample


@app.command()
def run(
    month: str = typer.Option(None, help="YYYY-MM (padrão: mês completo mais recente)"),
    only: str = typer.Option(None, help="Prefixos separados por vírgula, ex.: Cnaes,Municipios"),
    force: bool = typer.Option(False, help="Reconverte mesmo se já estiver no manifesto"),
    delete_zips: bool = typer.Option(None, help="Apaga o zip após converter (padrão: settings.yaml)"),
) -> None:
    """Baixa os zips do mês e converte para Parquet na camada bronze."""
    s = load_settings()
    delete_zips = s.delete_zips_after_convert if delete_zips is None else delete_zips
    dav = ReceitaWebDAV(s.webdav_url, s.webdav_token)
    month, remote = _resolve_month(dav, month)
    selected = _select(remote, only)
    if not selected:
        raise typer.BadParameter(f"Nenhum arquivo selecionado em {month} (only={only!r})")

    manifest = Manifest(s.ops_dir / "ingestion_files.json")
    pending = [f for f in selected if force or not manifest.is_converted(month, f.name, f.etag, f.size)]
    log.info("Mês %s: %d arquivos selecionados, %d pendentes", month, len(selected), len(pending))
    if not pending:
        log.info("Nada a fazer: tudo já convertido.")
        return

    landing = s.landing_dir / f"ref_month={month}"
    need = sum(f.size or 0 for f in pending if not (landing / f.name).exists())
    free = shutil.disk_usage(s.data_dir if s.data_dir.exists() else s.data_dir.parent).free
    log.info("Download necessário: %s | disco livre: %s", _gb(need), _gb(free))
    if need * 2 > free:  # zip + parquet
        raise typer.Exit(log.error("Espaço em disco insuficiente (precisa ~2x o download)") or 1)

    # Download (threads) e conversão (processos: o parse do CSV é CPU-bound) em esteira:
    # cada arquivo é convertido assim que termina de baixar, sem esperar os demais.
    def on_converted(f: RemoteEntry, fut) -> None:
        try:
            rows, invalid, sample = fut.result()
        except Exception as e:
            manifest.update(month, f.name, status="convert_failed", error=str(e))
            log.error("Falha ao converter %s: %s", f.name, e)
            return
        manifest.update(month, f.name, status="converted", rows=rows, invalid_rows=invalid,
                        invalid_sample=sample, error=None)
        log.info("convertido %s: %d linhas%s", f.name, rows, f" ({invalid} inválidas)" if invalid else "")
        if delete_zips:
            (landing / f.name).unlink(missing_ok=True)

    t0 = time.monotonic()
    with ThreadPoolExecutor(s.download_workers) as dl_pool, ProcessPoolExecutor(s.convert_workers) as cv_pool:
        # maiores primeiro: o arquivo mais lento começa cedo
        downloads = {
            dl_pool.submit(download_file, dav.client, dav.url(month, f.name), dav.auth, landing / f.name, f.size): f
            for f in sorted(pending, key=lambda f: -(f.size or 0))
        }
        for fut in as_completed(downloads):
            f = downloads[fut]
            try:
                fresh = fut.result()
            except Exception as e:
                manifest.update(month, f.name, status="download_failed", error=str(e))
                log.error("Falha no download de %s: %s", f.name, e)
                continue
            manifest.update(month, f.name, status="downloaded", size=f.size, etag=f.etag,
                            last_modified=f.last_modified)
            log.info("%s %s (%s)", "baixado" if fresh else "já existia", f.name, _gb(f.size or 0))
            entity = entity_for(f.name)
            out = s.bronze_dir / entity / f"ref_month={month}" / f.name.replace(".zip", ".parquet")
            cv_pool.submit(_convert_job, str(landing / f.name), entity, str(out), month).add_done_callback(
                partial(on_converted, f)
            )
        log.info("Downloads concluídos em %.0fs; aguardando conversões", time.monotonic() - t0)
    log.info("Ingestão concluída em %.0fs", time.monotonic() - t0)

    failed = [f.name for f in pending if manifest.get(month, f.name).get("status") != "converted"]
    if failed:
        log.error("Arquivos com falha: %s", ", ".join(failed))
        raise typer.Exit(1)
