# Phase 1 Data Model: Scraper Real Amarok AMA-BR — Navegador Assistido, Human-in-the-Loop e Resume

**Feature**: `002-amarok-ama-br-browser-scraper` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

Este documento descreve apenas o que é **novo ou explicitamente estendido** por esta feature. Toda entidade já definida em `specs/001-amarok-ama-br-ingestion/data-model.md` (`SpecIdentity`, `RawBlob`/`RawCapture`, `CaptureValidationResult`, `SpecSnapshot`, `FingerprintSet`, `EquivalenceResult`/`EquivalenceClass`, `ResolvedImage`, `CollectionRun`/`CheckpointEntry`, `CurrentSpecState`, `DiscoveredSpecEntry`, `SpecGroupManifest`) permanece **inalterada** — não é repetida aqui.

## 0. Extensão de enum existente

### `AcquisitionMode` (`ingestion/capture_kind.py`)

| Valor | Origem |
|---|---|
| `MANUAL_BROWSER` | já existente (`001`) |
| `AUTOMATED_BROWSER_CDP` | **novo** — usado por toda `RawCaptureInput` produzida pelo transporte desta feature |

Nenhuma mudança de schema (coluna `TEXT` já existente, sem `CHECK`). Ver research.md §6.

---

## 1. `BrowserCapture` (novo — `transport/port.py`)

Saída do transporte real, entregue à camada de orquestração para ser convertida em `RawCaptureInput` (contrato já existente de `001`, inalterado).

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `page_source` | `str` | sim | HTML bruto tal como o navegador o expõe no momento da captura (`outerHTML` do documento) — nunca pós-processado/filtrado pelo transporte. |
| `effective_url` | `str` | sim | URL efetiva após qualquer redirecionamento — pode diferir da URL navegada. |
| `captured_at` | `datetime` (UTC) | sim | Momento da leitura, não da navegação (relevante quando `current_capture()` relê sem nova navegação — research.md §11). |

**Invariante**: `BrowserCapture` nunca é produzida com `page_source` vazio — uma falha de navegação/leitura é sempre uma exceção de `transport/errors.py`, nunca uma `BrowserCapture` "vazia" silenciosa (mesma disciplina de `RawCaptureInput.raw_content` em `001`, que rejeita bytes vazios como pré-condição, não como `INCOMPLETE`).

**Conversão para `RawCaptureInput`** (feita pelo driver, `orchestration/collection_driver.py`, nunca pelo transporte):
```
RawCaptureInput(
    capture_kind=<conhecido pelo driver — qual unidade está sendo capturada>,
    source_url=capture.effective_url,
    collected_at=capture.captured_at,
    raw_content=capture.page_source.encode("utf-8"),
    run_id=<run ativo>,
    acquisition_mode=AcquisitionMode.AUTOMATED_BROWSER_CDP,
    expected_identity_context=<quando aplicável>,
)
```

---

## 2. `BrowserTransport` (Protocol — `transport/port.py`)

Ver `contracts/browser-transport-contract.md` §1 para a definição completa e regras. Resumo:

```
BrowserTransport (Protocol):
  navigate(url: str) -> BrowserCapture
  current_capture() -> BrowserCapture
```

Nenhum método de "resolver challenge", "esperar N segundos" ou "verificar se é challenge" existe nesta interface — essas responsabilidades pertencem, respectivamente, a: nunca (proibido), ao driver (`orchestration/collection_driver.py`, laço de poll), e a `classify_capture()` (núcleo já existente). O port é deliberadamente mínimo.

---

## 3. Erros de transporte (`transport/errors.py`)

| Exceção | Quando |
|---|---|
| `TransportError` | Base — nunca instanciada diretamente. |
| `ChromeNotReachableError` | O endpoint CDP configurado não responde (research.md §4). |
| `NavigationTimeoutError` | A navegação não completou dentro do timeout interno do adapter. |
| `NavigationFailedError` | Falha de navegação não coberta pelas duas acima (ex.: erro de rede reportado pelo próprio Chrome). |

**Invariante central (DEC-006)**: nenhuma dessas exceções é, ou é convertida em, um `ValidationOutcome` (`CHALLENGE`/`INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED`/`ACCEPTED`) — elas nunca alcançam `classify_capture()`, porque nenhuma `RawCaptureInput` chega a ser construída quando uma delas é levantada. O driver as trata exclusivamente pela via de "falha de transporte" (research.md §10), nunca pela via de "rejeição de validação".

---

## 4. `RunSelectionResult` (novo — `orchestration/run_selection.py`)

| Campo | Tipo | Notas |
|---|---|---|
| `run` | `CollectionRun` | O run efetivamente selecionado/criado. |
| `created_new` | `bool` | `True` quando um novo `CollectionRun` foi criado por esta seleção. |

Erros (não um campo de resultado — levantados, nunca retornados como valor "de erro" silencioso):

| Exceção | Quando |
|---|---|
| `IncompatibleResumeRunError` | `--resume <run_id>` aponta para um run de `scope` diferente ou já `completed_at` preenchido. |
| `AmbiguousResumeError` | Sem `--resume`/`--new-run`, e 2+ `CollectionRun` incompletas compatíveis existem — carrega a lista de candidatos para a mensagem de erro. |

Ver `contracts/orchestration-contract.md` §1 para o algoritmo completo (DEC-005).

---

## 5. `PendingUnitClassification` (novo — `orchestration/retry_classification.py`)

```
enum PendingUnitClassification:
  NOT_YET_ATTEMPTED       # CheckpointEntry ausente ou status PENDING
  TRANSPORT_RETRY          # status IN_PROGRESS (órfã de execução anterior)
  CHALLENGE_PAUSED         # status REJECTED, evidence.outcome == "CHALLENGE"
  REQUIRES_EXPLICIT_RETRY  # status REJECTED, evidence.outcome em {INVALID, INCOMPLETE,
                           # TRANSLATION_CONTAMINATED} OU "critical_error" em evidence
```

Classificação de **consumo** (spec.md, Key Entities "Retry Classification") — não é um novo status persistido; deriva inteiramente de `CheckpointEntry.status`/`CheckpointEntry.evidence`, ambos já existentes. Ver research.md §9 e `contracts/orchestration-contract.md` §2.

---

## 6. `OperationalPlan` (novo — `orchestration/dry_run.py`)

Saída somente-leitura de `plan_operation()` (DEC-009) — nunca produzida por um caminho que também possa escrever.

| Campo | Tipo | Notas |
|---|---|---|
| `run_decision` | `str` (descrição legível) | Resultado que `select_run()` produziria — sem executá-lo (mesma lógica pura de leitura, nunca chama `save_collection_run`). |
| `discovered_spec_count` | `int` | Quantidade de `SpecIdentity` já em `spec_registry` no momento da leitura. |
| `specs_to_process` | `list[str]` (`stable_key`) | Após aplicar filtros (`--spec`, `--limit-specs`) e exclusão de já-`VALID` (a menos que `--force`). |
| `already_valid_specs` | `list[str]` (`stable_key`) | Specs que seriam puladas por já estarem `VALID`/`STALE`. |
| `pending_groups_by_spec` | `dict[str, list[tuple[str, str]]]` | Para specs com manifesto autoritativo já persistido — `(category_slug, group_id)` pendentes, já truncado por `--limit-groups` quando aplicável. |
| `specs_without_manifest_yet` | `list[str]` (`stable_key`) | Specs selecionadas cujo manifesto ainda não existe — seriam capturadas via `SPEC_NAVIGATION` antes de qualquer `GROUP_DETAIL`. |

Ver `contracts/orchestration-contract.md` §3 para a garantia estrutural de que `plan_operation()` nunca recebe nenhuma função de escrita como dependência (não apenas "promete não chamar" — é estruturalmente incapaz).

---

## 7. Novas funções de leitura em repositórios existentes (nenhuma nova tabela)

### `persistence/repositories/checkpoint_repo.py`

```python
def list_incomplete_runs(conn: sqlite3.Connection, scope: str) -> list[CollectionRun]:
    """CollectionRun com scope == scope e completed_at IS NULL (data-model.md §11 de 001).

    Query aditiva sobre a tabela collection_run já existente — nenhuma migration.
    Usada exclusivamente por orchestration/run_selection.py (DEC-005).
    """
```

### `persistence/repositories/spec_registry_repo.py`

```python
def list_all_spec_identities(conn: sqlite3.Connection) -> list[SpecIdentity]:
    """Todas as SpecIdentity já persistidas em spec_registry, nesta ou em execuções
    anteriores (independente de run_id — spec_registry não é escopado por run).

    Query aditiva sobre a tabela spec_registry já existente — nenhuma migration.
    Usada por orchestration/collection_driver.py para saber quais specs navegar
    após uma captura MARKET_INDEX, e por orchestration/dry_run.py.
    """
```

Nenhuma função existente é modificada; ambas são adições puras. Ver research.md §8/§12 para a prova de que nenhuma delas pode ser obtida de outra forma sem alterar uma assinatura já aprovada de `001`.

---

## 8. Ajuste de robustez em `persistence/db.py` (não é uma nova entidade)

```python
def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")   # NOVO — research.md §16
    return conn
```

Configuração padrão de SQLite para tolerar contenção de escrita entre processos (5 segundos de espera antes de `database is locked`, em vez de falha imediata). Não é uma nova entidade de domínio nem uma migration — é uma linha de configuração de conexão. Comportamento single-process é idêntico ao atual (nunca há contenção a esperar).

---

## Resumo de rastreabilidade (entidade/mudança → decisão)

| Item | Decisão/FR relacionados |
|---|---|
| `AcquisitionMode.AUTOMATED_BROWSER_CDP` | FR-005, research.md §6 |
| `BrowserCapture` / `BrowserTransport` | FR-001, FR-003, FR-003a, FR-005 |
| `transport/errors.py` | FR-020 (distinção falha de transporte), DEC-006 |
| `RunSelectionResult` / `select_run()` | FR-019, FR-026, DEC-005 |
| `PendingUnitClassification` / `classify_pending_unit()` | FR-020, FR-021, DEC-006 |
| `OperationalPlan` / `plan_operation()` | FR-022, DEC-009 |
| `list_incomplete_runs()` | FR-019, FR-032, DEC-005 |
| `list_all_spec_identities()` | FR-006, FR-007, FR-032 |
| `PRAGMA busy_timeout` | concorrência entre processos (research.md §16) |
