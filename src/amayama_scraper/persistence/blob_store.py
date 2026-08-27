"""Armazenamento de conteúdo endereçado por sha256 (research.md §8, data-model.md §4a).

Sharding de 2 níveis (`ab/cd/abcd...`) para evitar diretórios com milhares
de arquivos. Idempotente por construção: o mesmo `content_hash` sempre
resolve para o mesmo caminho — escrever o mesmo conteúdo duas vezes nunca
duplica o arquivo físico.
"""

from __future__ import annotations

from pathlib import Path


def blob_path(root: Path, content_hash: str) -> Path:
    return root / content_hash[0:2] / content_hash[2:4] / content_hash


def write_blob(root: Path, content_hash: str, raw_content: bytes) -> Path:
    path = blob_path(root, content_hash)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_bytes(raw_content)
    tmp_path.replace(path)  # atomic on POSIX — never a partially-written blob visible
    return path


def read_blob(root: Path, content_hash: str) -> bytes:
    path = blob_path(root, content_hash)
    if not path.exists():
        raise FileNotFoundError(f"blob {content_hash!r} not found under {root}")
    return path.read_bytes()
