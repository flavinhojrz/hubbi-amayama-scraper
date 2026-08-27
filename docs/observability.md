# Observabilidade — identificadores de evidência/run

**Feature**: `001-amarok-ama-br-ingestion` — ponto 27 do PLAN.

Este documento registra, como contrato de observabilidade, os identificadores que correlacionam uma execução de coleta ao estado que ela produziu — a base para auditar "o que aconteceu" sem depender de nenhuma representação em memória de uma execução anterior (data-model.md §13c).

## `run_id`

Identifica uma `CollectionRun` (`checkpoint/collection_run.py`, tabela `collection_run`). Todo `RawCapture`, `CheckpointEntry`, `SpecGroupManifest` e evento de log (`orchestration/logging.py`) carrega o `run_id` da execução que o produziu — é a chave de correlação primária entre logs, checkpoints e persistência.

## `capture_id`

Identifica uma `RawCapture` (Observation, data-model.md §4b) — nunca colapsado mesmo quando duas capturas compartilham `content_hash` (dedup físico via `RawBlob`, separado). `CheckpointEntry.raw_capture_id` referencia este identificador — é o que permite reconstruir o `raw_content` original via `reconstruct_raw_content()` (`ingestion/ports.py`) mesmo após um restart de processo.

## Evidência de checkpoint

`CheckpointEntry.evidence` (dict) — preenchido em `upsert_checkpoint()` (`checkpoint/upsert.py`) quando o evento é `REJECT`: registra o `outcome` de validação (`CHALLENGE`/`TRANSLATION_CONTAMINATED`/`INVALID`/`INCOMPLETE`) ou o `critical_error` de parsing que motivou a rejeição — nunca um booleano solto sem contexto. Consultável por `(run_id, spec_key, category_slug, group_id)`.

## Evidência de manifesto

`SpecGroupManifest.validation_evidence` (dict) — contagens de auditoria da extração do Nível B (`category_count`, `group_count`), preenchidas por `parse_spec_group_manifest()`. Junto com `manifest_complete`, é o que permite auditar por que um manifesto foi ou não considerado autoritativo (`is_manifest_authoritative()`, data-model.md §15).

## Logging estruturado

`orchestration/logging.py:log_event(*, run_id, event, **fields)` — emite uma linha JSON por evento, sempre correlacionada por `run_id`. Campos nomeados `raw_content`/`raw_html`/`html`, ou qualquer valor `bytes`/`bytearray`, são recusados explicitamente (`RawContentInLogError`) — o log nunca despeja conteúdo bruto completo, apenas referências (`content_hash`, `capture_id`, `size_bytes`).

## Idempotência auditável

`SpecSnapshot.idempotency_key` (data-model.md §13b) é determinístico a partir de `(run_id, spec_key, accepted_checkpoint_fingerprint)` — o multiset de `(category_slug, group_id, raw_capture_id)` `ACCEPTED` (`snapshots/idempotency.py`). Dois snapshots com a mesma chave são, por construção, a mesma finalização — nunca uma coincidência a ser investigada manualmente.
