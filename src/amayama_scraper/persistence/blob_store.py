"""Armazenamento de conteúdo endereçado por sha256 (research.md §8, data-model.md §4a).

Sharding de 2 níveis (`ab/cd/abcd...`) para evitar diretórios com milhares
de arquivos. Idempotente por construção: o mesmo `content_hash` sempre
resolve para o mesmo caminho — escrever o mesmo conteúdo duas vezes nunca
duplica o arquivo físico.

005 hardening (post-review, HIGH — `FilesystemRawBlobStore` concorrente):
`write_blob()` usa um arquivo temporário EXCLUSIVO por chamada (PID +
UUID), nunca um `.tmp` de nome fixo compartilhado — dois workers
(processos distintos) escrevendo o MESMO `content_hash` ao mesmo tempo
nunca disputam o mesmo arquivo intermediário nem se pisam com
`FileNotFoundError`/erro de compartilhamento (Windows). A publicação final
(`Path.replace()`) é atômica em todas as plataformas suportadas — mesmo
que dois workers publiquem em sequência, o conteúdo é idêntico por
definição (mesmo `content_hash`), então um "sobrescrever" pelo segundo
nunca corrompe nada nem perde bytes de um blob válido já publicado com
conteúdo diferente.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def blob_path(root: Path, content_hash: str) -> Path:
    return root / content_hash[0:2] / content_hash[2:4] / content_hash


def write_blob(root: Path, content_hash: str, raw_content: bytes) -> Path:
    path = blob_path(root, content_hash)
    if path.exists():
        return path  # já publicado por alguém (este processo ou outro) — nada a fazer
    path.parent.mkdir(parents=True, exist_ok=True)
    # Nome exclusivo por chamada — nunca compartilhado entre workers/processos
    # concorrentes escrevendo o mesmo content_hash (005 hardening, HIGH 6).
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(raw_content)
        tmp_path.replace(path)  # atômico em todas as plataformas (inclusive Windows) —
        # se `path` já existir (outro worker publicou primeiro), sobrescreve
        # atomicamente com o MESMO conteúdo (mesmo content_hash), nunca corrompe.
    finally:
        tmp_path.unlink(missing_ok=True)  # no-op se replace() já moveu o arquivo
    return path


def read_blob(root: Path, content_hash: str) -> bytes:
    path = blob_path(root, content_hash)
    if not path.exists():
        raise FileNotFoundError(f"blob {content_hash!r} not found under {root}")
    return path.read_bytes()
