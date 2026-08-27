# Raw schema — RawBlob / RawCapture / SpecGroupManifest / storage

**Feature**: `001-amarok-ama-br-ingestion` — Constitution §4 ("preservar o bruto antes de qualquer transformação").

## `RawBlob` (física, deduplicada) — data-model.md §4a

Conteúdo físico endereçado por `content_hash` (SHA-256 hex do `raw_content`). Dois `RawCapture` com o mesmo `content_hash` compartilham um único `RawBlob` — nunca duplicado no disco.

| Campo | Tipo | Notas |
|---|---|---|
| `content_hash` | `str` (64 hex) | PK |
| `size_bytes` | `int` | |
| `storage_path` | `str` | caminho sharded (ver abaixo) |
| `first_seen_at` | `datetime` | primeira vez que este conteúdo foi visto |

Tabela: `raw_blob` (`0003_raw.sql`). Implementação: `src/amayama_scraper/persistence/blob_store.py` + adapter `FilesystemRawBlobStore` (satisfaz o port `RawBlobStore`, `ingestion/ports.py`).

**Layout do storage content-addressed**: sharding de 2 níveis por prefixo do `content_hash` — `<root>/<hash[0:2]>/<hash[2:4]>/<hash>`. Evita diretórios com dezenas de milhares de arquivos. Escrita atômica via arquivo temporário + `rename()` (`write_blob()`), nunca um blob parcialmente escrito visível.

## `RawCapture` (Observation, nunca colapsada) — data-model.md §4b

Cada submissão manual (browser-in-the-loop, DEC-001) gera uma nova `RawCapture`, mesmo que o `content_hash` já exista — `capture_id` é sempre novo.

| Campo | Tipo | Notas |
|---|---|---|
| `capture_id` | `str` | PK, UUID |
| `run_id` | `str` | FK lógica para `CollectionRun` |
| `content_hash` | `str` | FK para `raw_blob` |
| `source_url` | `str` | URL absoluta capturada |
| `collected_at` | `datetime` | |
| `capture_kind` | `MARKET_INDEX \| SPEC_NAVIGATION \| GROUP_DETAIL` | roteia o parser |
| `acquisition_mode` | `MANUAL_BROWSER` | único valor válido nesta feature (DEC-001) |
| `expected_identity_context` | `dict \| null` | contexto presumido pela navegação (auditoria, nunca fonte de verdade) |
| `collection_metadata` | `dict` | |

Tabela: `raw_capture` (`0003_raw.sql`). Implementação: adapter `SqliteRawCaptureRepository` (satisfaz o port `RawCaptureRepository`).

**Replay/reconstrução determinística** (contracts/ports-contract.md): `capture_repo.get(capture_id) → RawCapture.content_hash → blob_store.read(content_hash) → bytes` — suficiente para reconstruir o HTML bruto original de qualquer captura já persistida, mesmo após um restart de processo, sem depender de nenhum objeto parseado sobrevivendo em memória (`ingestion/ports.py:reconstruct_raw_content()`, usado por `snapshots/finalize.py`).

## `SpecGroupManifest` (Nível B, autoritativo) — data-model.md §15

Fonte autoritativa do universo esperado de `(category_slug, group_id)` para uma spec entry, dentro de uma `CollectionRun`.

| Campo | Tipo | Notas |
|---|---|---|
| `spec_key` | `str` | `stable_key` da spec entry |
| `run_id` | `str` | associado à run que descobriu este manifesto (coluna denormalizada para consulta — `get_authoritative(spec_key, run_id)`) |
| `source_capture_id` | `str` | `RawCapture.capture_id` de origem |
| `discovered_at` | `datetime` | |
| `categories` | JSON | lista de `{category_slug, groups: [{group_id, source_url}]}` |
| `manifest_complete` | `bool` | ver limitação de observabilidade em research.md §21 |
| `validation_evidence` | JSON | contagens de auditoria |

Tabela: `spec_group_manifest` (`0002_manifest.sql`). Implementação: `persistence/repositories/manifest_repo.py`. Condição 1 de autoridade (captura ACCEPTED) é estruturalmente garantida pelo pipeline (nunca reverificada no repositório) — ver docstring de `manifest_repo.get_authoritative()`.

## Demais tabelas de persistência (visão geral)

| Tabela | Migration | Entidade |
|---|---|---|
| `spec_registry` / `discovered_spec_entry` / `current_spec_state` | `0001` | `SpecIdentity`/`DiscoveredSpecEntry`/`CurrentSpecState` |
| `collection_run` / `checkpoint_entry` | `0004` | `CollectionRun`/`CheckpointEntry` |
| `spec_snapshot` (+ colunas de fingerprint em `0006`) | `0005`/`0006` | `SpecSnapshot`/`FingerprintSet` |
| `cluster_assignment` | `0007` | `ClusterAssignment` |
| `asset_resolution` | `0008` | `ResolvedImage` |

`persistence/` é o único pacote autorizado a importar `sqlite3` (`tests/unit/test_persistence_isolation.py`); PostgreSQL não é projetado nesta feature — apenas a fronteira de repositórios permitiria uma substituição futura (DEC-002, `persistence/db.py`).
