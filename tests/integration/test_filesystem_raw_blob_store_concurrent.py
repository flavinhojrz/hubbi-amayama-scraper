"""005 hardening (post-review) — HIGH 6: `FilesystemRawBlobStore.get_or_create()`
sob concorrência REAL entre PROCESSOS (não threads) — dois workers tentando
publicar o MESMO `content_hash` ao mesmo tempo nunca corrompem o arquivo
nem derrubam o processo (`IntegrityError`/`FileNotFoundError`/erro de
compartilhamento do Windows), e o content-addressed storage permanece
consistente (uma linha em `raw_blob`, um arquivo físico, conteúdo íntegro,
nenhum `.tmp` remanescente).

`multiprocessing` real (contexto `spawn`) aqui — ao contrário dos testes de
worker pool (que evitam spawn real por causa de Chrome/selenium), esta
operação é puramente filesystem + SQLite, leve e segura de rodar como
processo real em CI."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from amayama_scraper.ingestion.hashing import content_hash
from amayama_scraper.persistence.adapters.filesystem_raw_blob_store import FilesystemRawBlobStore
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations

_RAW_CONTENT = b"<html>same content published by two concurrent processes</html>" * 200


def _worker_write_blob(db_path: str, raw_root: str, iterations: int) -> None:
    """Entrypoint de processo real (picklable — módulo-nível, contracts/
    worker-pool-contract.md §0, mesmo padrão de `cli/main.py::_worker_process_entrypoint`)."""
    conn = connect(db_path)
    blob_store = FilesystemRawBlobStore(Path(raw_root), conn)
    digest = content_hash(_RAW_CONTENT)
    for _ in range(iterations):
        blob_store.get_or_create(digest, _RAW_CONTENT)
    conn.close()


def test_two_processes_publishing_the_same_blob_concurrently_never_corrupt_or_crash(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "pool.db")
    raw_root = tmp_path / "blobs"
    setup_conn = connect(db_path)
    run_migrations(setup_conn)
    setup_conn.close()

    digest = content_hash(_RAW_CONTENT)

    ctx = multiprocessing.get_context("spawn")
    processes = [
        ctx.Process(target=_worker_write_blob, args=(db_path, str(raw_root), 5)) for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=60)

    for process in processes:
        assert process.exitcode == 0, f"worker process exited with {process.exitcode!r}"

    conn = connect(db_path)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM raw_blob WHERE content_hash = ?", (digest,)
    ).fetchone()
    assert row["n"] == 1  # nenhuma duplicação de linha por colisão de PK

    blob_store = FilesystemRawBlobStore(raw_root, conn)
    assert blob_store.read(digest) == _RAW_CONTENT  # conteúdo íntegro, nunca corrompido/truncado

    tmp_leftovers = list(raw_root.rglob("*.tmp"))
    assert tmp_leftovers == []  # nenhum arquivo temporário órfão
