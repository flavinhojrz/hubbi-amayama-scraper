"""FingerprintSet — 4 hashes independentes + versão (data-model.md §7)."""

from __future__ import annotations

from dataclasses import dataclass

#: Sentinel para um hash de fingerprint indisponível (ex.: coluna NULL em
#: estado persistido — spec_snapshot.<hash>_hash é NULLable desde
#: 0006_fingerprints.sql, para snapshots anteriores ao cálculo de
#: fingerprints). Deliberadamente incompatível com um SHA-256 real
#: (comprimento/charset), então nunca colide com um hash genuíno.
#:
#: Vive em fingerprints/ (camada de domínio pura, sem I/O) — não em
#: persistence/ — para que qualquer camada (persistence/ na conversão
#: row->domain, analysis/ na leitura) possa depender desta representação
#: neutra sem que analysis/ precise importar persistence/
#: (003-corpus-analysis-tool, achado arquitetural do Codex).
UNAVAILABLE_HASH = "UNAVAILABLE-NULL-FINGERPRINT"


@dataclass(frozen=True, slots=True)
class FingerprintSet:
    structure_hash: str
    spec_parts_hash: str
    schema_semantic_hash: str
    image_hash: str
    fingerprint_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "structure_hash",
            "spec_parts_hash",
            "schema_semantic_hash",
            "image_hash",
            "fingerprint_version",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"FingerprintSet.{field_name} must not be empty")
