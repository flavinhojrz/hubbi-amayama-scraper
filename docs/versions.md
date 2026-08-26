# Versões — parser/normalizer/fingerprint

**Feature**: `001-amarok-ama-br-ingestion` — Constitution §13 ("qualquer alteração de regra exige uma nova versão explícita, nunca reinterpretação silenciosa do mesmo valor").

## `parser_version`

| Valor | Nível | Módulo | Constante |
|---|---|---|---|
| `amayama-market-index-parser-v1` | A (Market Index) | `src/amayama_scraper/parsing/market_index.py` | `PARSER_VERSION` |
| `amayama-spec-group-manifest-parser-v1` | B (Spec Group Manifest) | `src/amayama_scraper/parsing/spec_group_manifest.py` | `PARSER_VERSION` |
| `amayama-parser-v1` | C (Group Detail) | `src/amayama_scraper/parsing/group_detail.py` | `PARSER_VERSION` |

Cada nível tem sua própria versão — os três avançam de forma independente. Um `SpecSnapshot.parser_version` reflete o parser de Nível C (`amayama-parser-v1`) usado para reconstruir a árvore de detalhe na finalização (`snapshots/finalize.py`), já que é o único nível cujo conteúdo participa diretamente do `spec_parts_hash`/fingerprints.

## `normalizer_version`

| Valor | Módulo | Constante |
|---|---|---|
| `amayama-normalizer-v1` | `src/amayama_scraper/normalization/version.py` | `NORMALIZER_VERSION` |

Regras: NFKC, colapso de whitespace técnico/NBSP, `strip()`, `upper()` seletivo (OEM/PNC), remoção de whitespace interno técnico do OEM, ordenação lexicográfica de `pr_codes` — contracts/normalization-fingerprint-contracts.md.

## `fingerprint_version`

| Valor | Módulo | Constante |
|---|---|---|
| `amayama-fingerprint-v1` | `src/amayama_scraper/fingerprints/version.py` | `FINGERPRINT_VERSION` |

Campos canônicos de `part_fingerprint` (`schema_id, pnc, oem, description, details, period, required`) — `pr_codes` explicitamente excluído (decisão fechada pelo PO, contracts/normalization-fingerprint-contracts.md). Quatro hashes independentes compõem `FingerprintSet`: `structure_hash`, `spec_parts_hash`, `schema_semantic_hash`, `image_hash`.

## Regra de versionamento

Qualquer alteração em uma regra de normalização ou no conjunto de campos canônicos de um fingerprint exige uma nova constante de versão (`-v2`, etc.) e revalidação dos dados dependentes (clusters, `SpecSnapshot`) — nunca uma reinterpretação silenciosa do mesmo valor de versão. `contracts/equivalence-contracts.md` já trata mismatch de versão como `comparison_valid = False` / `parts_relation = UNKNOWN`, nunca `DIFFERENT`.
