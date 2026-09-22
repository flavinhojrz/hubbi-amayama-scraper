---
description: "Task list — feature 004 (multi-model isolation)"
---

# Tasks: Multi-Model Volkswagen Scraper — Isolamento Operacional

**Input**: spec.md, plan.md (ambos neste diretório)

**Tests**: obrigatórios (Constitution §12, Execution Policy "Política de testes")
— toda task de regra estrutural inclui teste correspondente.

**Autorização**: PO autorizou explicitamente, nesta conversa, a execução
direta de `CLAUDE IMPLEMENTA` para as tasks abaixo, dispensando o gate
assíncrono formal de aprovação separada (ver CLAUDE.md — instrução do PO
tratada como aprovação direta, mesmo padrão já registrado na entrega da
feature 002).

## Fase 1: Fundação — CollectionContext (bloqueante para todas as demais)

- [x] T401 [P] Criar `src/amayama_scraper/domain/collection_context.py`:
      `normalize_scope_component()`, `CollectionContext` (frozen, validado),
      `build_scope()`, `parse_scope()`, `ContextScopeMismatchError`,
      `InvalidScopeComponentError`, `InvalidScopeError`.
- [x] T402 [P] `tests/unit/test_collection_context.py`: normalização
      (trim/upper/rejeição de vazio/delimitador/caracteres inseguros),
      round-trip `parse_scope(build_scope(ctx)) == ctx`, preservação exata do
      scope histórico da Amarok.

**Checkpoint**: FR-001, FR-010–FR-015, FR-020–FR-024 cobertos e testáveis
isoladamente, sem tocar orchestration/CLI ainda.

---

## Fase 2: `CollectionRun` e `checkpoint/collection_run.py`

- [x] T403 `CollectionRun.__post_init__` valida `scope` via `parse_scope()`
      (substituindo a checagem de não-vazio simples); adicionar
      `CollectionRun.context()` (retorna `CollectionContext`). Remover o
      `build_scope()` local (agora vive em `domain/collection_context.py`).
      `FIXED_SCOPE` permanece, docstring reforça "legado apenas".
- [x] T404 [P] Atualizar `tests/unit/test_collection_run.py`,
      `tests/unit/test_collection_run_scope.py` para a nova validação/API.

**Checkpoint**: FR-064 (FIXED_SCOPE como legado) e FR-013/014 (parse via
CollectionRun) cobertos.

---

## Fase 3: URL segura

- [x] T405 `domain/discovery.py::build_market_index_url()` passa a receber
      `CollectionContext` (não mais 3 strings soltas); remove a
      normalização própria (`_slug`) — usa diretamente os componentes já
      canônicos do contexto.
- [x] T406 [P] Atualizar `tests/unit/test_build_market_index_url.py` para a
      nova assinatura; adicionar teste de preservação exata da URL histórica
      da Amarok (FR-032).

**Checkpoint**: FR-030–FR-032 cobertos.

---

## Fase 4: Contexto único em `process_capture`/`run_collection` (US1, US4)

- [x] T407 `orchestration/pipeline.py::process_capture()` exige `context:
      CollectionContext` (keyword-only, sem default); valida contra
      `get_collection_run(conn, run_id).scope` **antes** de `accept_capture()`;
      levanta `ContextScopeMismatchError` em divergência. Remove
      `manufacturer`/`vehicle_model` soltos e `_IDENTITY_CONSTANTS`/defaults
      remanescentes de 002.
- [x] T408 `process_capture()` branch MARKET_INDEX: após parse, comparar
      `market` de cada `DiscoveredSpecEntry` com `context.market`; em
      divergência, não persistir nada e retornar `critical_error=True`
      (FR-040, FR-041).
- [x] T409 `run_collection()` (mesmo módulo) propaga `context` obrigatório
      para `process_capture()`.
- [x] T410 [P] `tests/unit/test_process_capture_context_validation.py`
      (NOVO): contexto divergente do `CollectionRun.scope` levanta erro antes
      de qualquer persistência (raw capture incluído); MARKET_INDEX com
      market divergente não persiste specs e retorna `critical_error=True`.

**Checkpoint**: FR-002, FR-005, FR-040–FR-042 cobertos no nível de
`process_capture`.

---

## Fase 5: Contexto único em `run_collection_driver` (US1, Cenário E/F)

- [x] T411 `orchestration/collection_driver.py::run_collection_driver()` e
      `await_challenge_resolution()` exigem `context: CollectionContext`
      (sem default); `run_collection_driver()` valida
      `get_collection_run(conn, run_id).scope == context.scope()` **antes**
      de qualquer `navigate()`. Substitui os parâmetros soltos
      `manufacturer/vehicle_model/market` introduzidos em 002. Descoberta via
      `list_by_scope()` passa a usar `context.manufacturer/vehicle_model/market`.
- [x] T412 `run_collection_driver()`: após processar o MARKET_INDEX inicial
      (e seu eventual challenge-wait), checar `result.critical_error`; se
      verdadeiro, emitir `on_event("RUN_ABORTED", reason=...)` e retornar
      sem prosseguir para descoberta de specs (FR-041, Cenário F).
- [x] T413 `_maybe_mark_run_completed()` recebe `context` (não mais 3
      strings soltas) e usa `list_by_scope()` com seus campos (FR-050,
      FR-051).
- [x] T414 [P] `cli/main.py`: constrói `CollectionContext` a partir dos args
      (defaults históricos preservados — FR-003, FR-063) e o repassa para
      `run_collection_driver()`; valida (`ContextScopeMismatchError` ->
      mensagem de erro amigável + exit code) se aplicável.

**Checkpoint**: Cenário E (FR-034-A) e F (FR-035-A) cobertos ponta a ponta
via CLI/driver.

---

## Fase 6: Migração mecânica dos call sites existentes (sem mudança de
comportamento esperado)

- [x] T415 [P] Atualizar todos os call sites de `process_capture()`/
      `run_collection()`/`run_collection_driver()`/`await_challenge_resolution()`
      em `tests/` para passar `context=` explícito (usar
      `tests/support.py::AMAROK_CONTEXT` — task T420). Nenhuma asserção de
      comportamento muda; apenas a assinatura da chamada.
- [x] T416 [P] Atualizar `tests/integration/test_multi_model_collection.py`
      (002) e `tests/integration/test_cli_multi_model_run.py` (002) para a
      nova API `CollectionContext`/`build_scope`/`build_market_index_url`.

**Checkpoint**: suíte volta a compilar/coletar sob a nova assinatura, antes
de rodar a suíte completa.

---

## Fase 7: Isolamento entre modelos — Cenários A–D (US3)

- [x] T417 [P] Criar `tests/support.py`: `AMAROK_CONTEXT`, `GOL_CONTEXT`
      (constantes `CollectionContext` compartilhadas pelos testes).
- [x] T418 `tests/integration/test_multi_model_isolation.py` (NOVO) —
      **Cenário A**: Amarok totalmente populada (specs + manifest +
      checkpoints ACCEPTED + snapshot VALID + current_state) via inserts
      diretos nos repositórios; iniciar coleta de GOL (MARKET_INDEX apenas);
      assert zero specs/manifests/checkpoints/snapshots/current_state
      herdados por GOL; `CollectionRun` de GOL permanece incompleto
      (FR-030-A, FR-050, FR-051).
- [x] T419 [P] No mesmo arquivo — **Cenário B**: duas `SpecIdentity` com
      `model_code`/`amayama_catalog_id`/`market` idênticos e `vehicle_model`
      diferente têm `stable_key()` diferentes; nenhuma colisão de
      `current_state`/checkpoint (FR-031-A).
- [x] T420 [P] No mesmo arquivo — **Cenário C**: mesmo `vehicle_model`,
      `market` diferente — mesma prova de isolamento de B aplicada a
      `market` (FR-032-A).
- [x] T421 [P] No mesmo arquivo — **Cenário D**: `--resume`/`select_run()`
      entre um `CollectionRun` Amarok antigo e um novo contexto GOL é
      rejeitado (`IncompatibleResumeRunError`) (FR-033-A).

**Checkpoint**: SC-001 (100% dos cenários A–D) coberto.

---

## Fase 8: Isolamento entre modelos — Cenários E–F (US1, US4)

- [x] T422 [P] No mesmo arquivo — **Cenário E**: `run_collection_driver()`
      chamado com `run_id` de um `CollectionRun` Amarok e `context` GOL
      levanta `ContextScopeMismatchError` antes de qualquer
      `navigate()`/persistência (reusa T411; teste de integração ponta a
      ponta com `FakeBrowserTransport` que falha o teste se `navigate()` for
      chamado).
- [x] T423 [P] No mesmo arquivo — **Cenário F**: MARKET_INDEX cujo `market`
      extraído diverge de `context.market` — nenhuma spec persistida, run
      abortado (reusa T408/T412).

**Checkpoint**: SC-001 completo (cenários A–F).

---

## Fase 8b: Hardening — identidade ausente falha fechada (achado final do Codex)

- [x] T431 `_require_matching_spec_context()` (`orchestration/pipeline.py`)
      não pula mais a validação quando `spec_key` não tem `SpecIdentity`
      registrada — levanta `UnregisteredSpecIdentityError` (novo, em
      `domain/collection_context.py`), aplicado em `process_capture()` e
      `try_finalize_spec_entry()`. Testes legados que exercitavam SPEC_
      NAVIGATION/GROUP_DETAIL com `spec_key` sintético não registrado foram
      ajustados para registrar a identidade (`tests/support.py::register_spec`),
      nunca contornados. Novos testes: spec_key inexistente em
      `process_capture()` (SPEC_NAVIGATION e GROUP_DETAIL) e em
      `try_finalize_spec_entry()` falham fechado antes de qualquer
      manifest/checkpoint/snapshot/current_state; spec registrada e
      pertencente ao context continua funcionando normalmente.

**Checkpoint**: nenhum caminho operacional que processe `spec_key` mais
aceita identidade ausente como "nada a validar".

---

## Fase 8c: Hardening — provenance `capture_input.run_id` (achado final do Codex)

- [x] T432 `process_capture()` valida `capture_input.run_id == run_id`
      antes de qualquer validação secundária/persistência — `accept_capture()`
      persiste usando `capture_input.run_id`, então os dois precisam ser
      idênticos ou a garantia "o que foi validado é o que é persistido"
      quebra. Novo `CaptureRunMismatchError` (`domain/collection_context.py`,
      ao lado de `ContextScopeMismatchError`). Testes: cenário adversarial
      (run_id/context de GOL, `capture_input.run_id` de um run da Amarok,
      spec GOL registrada) rejeitado antes de raw_capture/manifest/
      checkpoint/snapshot/current_state; caso positivo (run_id igual)
      inalterado.

**Checkpoint**: `process_capture()` nunca mais persiste sob um
`capture_input.run_id` diferente do `run_id` validado.

---

## Fase 9: Validação final

- [x] T424 Rodar testes focados da feature 004
      (`test_collection_context.py`, `test_build_market_index_url.py`,
      `test_process_capture_context_validation.py`,
      `test_multi_model_isolation.py`, `test_collection_run*.py`).
- [x] T425 Rodar testes de `orchestration/` e `persistence/` (regressão).
- [x] T426 Rodar testes de CLI (regressão 002).
- [x] T427 Rodar suíte completa (`pytest -q`).
- [x] T428 `ruff check` nos arquivos alterados.
- [x] T429 `mypy src`.
- [x] T430 Reportar ao PO: artefatos SDD, arquitetura final, normalização,
      prova de isolamento, testes adicionados, resultado da suíte,
      limitações restantes.

---

## Dependencies & Execution Order

Fase 1 bloqueia todas as demais (todo o resto depende de `CollectionContext`).
Fases 2–3 podem rodar em paralelo entre si após Fase 1. Fase 4 depende de
Fases 1–3. Fase 5 depende de Fase 4. Fase 6 depende de Fases 4–5 (assinaturas
já estáveis). Fases 7–8 dependem de Fase 6 (suíte precisa compilar antes de
adicionar novos testes de isolamento). Fase 9 é sempre a última.

## Notes

- Nenhuma task desta lista faz coleta real ou commit (instrução explícita do
  PO, reforçada em cada task de execução).
- `parsing/market_index.py`, `equivalence/*`, `fingerprints/*`,
  `snapshots/*`, `analysis/*` (003), e o comportamento de CAPTCHA
  (`validation/detectors/challenge.py`) não têm nenhuma task nesta lista —
  permanecem intocados por design (spec.md "Assumptions", FR-060–FR-064).
