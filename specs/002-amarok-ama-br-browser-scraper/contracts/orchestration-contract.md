# Contrato: Seleção de Run, Classificação de Retry, Dry-Run e CLI

**Feature**: `002-amarok-ama-br-browser-scraper` — ver [../research.md](../research.md) §8–§10, §12, §17 para as decisões e justificativas completas.

## 1. Seleção de `run_id` (DEC-005) — `orchestration/run_selection.py`

```python
@dataclass(frozen=True, slots=True)
class RunSelectionResult:
    run: CollectionRun
    created_new: bool


class IncompatibleResumeRunError(ValueError): ...
class AmbiguousResumeError(ValueError):
    candidates: list[CollectionRun]


def select_run(
    *,
    resume_run_id: str | None,
    new_run: bool,
    scope: str,
    now: datetime,
    run_id_factory: Callable[[], str],
    get_collection_run: Callable[[str], CollectionRun | None],
    list_incomplete_runs: Callable[[str], list[CollectionRun]],
    save_collection_run: Callable[[CollectionRun], None],
) -> RunSelectionResult:
    """DEC-005 — algoritmo determinístico, nenhuma escolha heurística.

    1. resume_run_id informado:
       - busca via get_collection_run(resume_run_id)
       - None, ou scope != scope, ou completed_at preenchido -> IncompatibleResumeRunError
       - senão -> RunSelectionResult(run=<encontrado>, created_new=False)  [não grava nada]

    2. new_run == True:
       - cria CollectionRun(run_id=run_id_factory(), scope=scope, started_at=now)
       - save_collection_run(novo run)
       - RunSelectionResult(created_new=True)

    3. nenhum dos dois:
       - candidates = list_incomplete_runs(scope)
       - len(candidates) == 0 -> cria novo run (idêntico ao caso 2)
       - len(candidates) == 1 -> RunSelectionResult(run=candidates[0], created_new=False)
         [NÃO grava nada — run já existe; orquestração externa decide se atualiza
          `resumed_at` via save_collection_run(...) antes ou depois de select_run(),
          mantendo esta função pura sobre a DECISÃO, não sobre side-effects de auditoria]
       - len(candidates) >= 2 -> AmbiguousResumeError(candidates)  [NUNCA escolhe uma]
    """
```

**Propriedades garantidas**:
- Função pura sobre callables injetadas — nenhum `sqlite3`/`selenium` importado por este módulo (testável 100% com fakes em memória).
- `--resume` inválido e `--new-run` nunca competem: `new_run=True` é verificado **depois** de `resume_run_id` só faz sentido se `resume_run_id is None` — a CLI (contract §4) garante que as duas flags são mutuamente exclusivas antes mesmo de chamar `select_run()` (erro de uso, não uma ambiguidade de domínio).
- Nenhuma heurística (mais recente, mais antigo, etc.) decide entre 2+ candidatos — sempre erro.

## 2. Classificação de retry (DEC-006) — `orchestration/retry_classification.py`

```python
class PendingUnitClassification(StrEnum):
    NOT_YET_ATTEMPTED = "NOT_YET_ATTEMPTED"
    TRANSPORT_RETRY = "TRANSPORT_RETRY"
    CHALLENGE_PAUSED = "CHALLENGE_PAUSED"
    REQUIRES_EXPLICIT_RETRY = "REQUIRES_EXPLICIT_RETRY"


_VALIDATION_REJECTION_OUTCOMES = frozenset({"INVALID", "INCOMPLETE", "TRANSLATION_CONTAMINATED"})


def classify_pending_unit(entry: CheckpointEntry | None) -> PendingUnitClassification:
    if entry is None or entry.status is CheckpointStatus.PENDING:
        return PendingUnitClassification.NOT_YET_ATTEMPTED
    if entry.status is CheckpointStatus.IN_PROGRESS:
        return PendingUnitClassification.TRANSPORT_RETRY
    # status == REJECTED
    if entry.evidence.get("outcome") == "CHALLENGE":
        return PendingUnitClassification.CHALLENGE_PAUSED
    return PendingUnitClassification.REQUIRES_EXPLICIT_RETRY
    # cobre: evidence.outcome in {INVALID, INCOMPLETE, TRANSLATION_CONTAMINATED}
    #        e também "critical_error" in evidence (parsing pós-aceitação)
```

**Propriedades garantidas**:
- Função pura, síncrona, sem I/O — testável com `CheckpointEntry` construído diretamente em memória, sem SQLite (research.md §9).
- `ACCEPTED` nunca chega a este classificador — `get_pending_groups()` já o exclui do universo pendente antes de qualquer chamada aqui.
- Nenhum novo `CheckpointStatus` é criado — a classificação deriva inteiramente de `status`/`evidence` já persistidos por `001`.

**Consumo pelo driver** (`contracts/browser-transport-contract.md` §3): por padrão, o driver tenta unidades classificadas como `NOT_YET_ATTEMPTED`, `TRANSPORT_RETRY` e `CHALLENGE_PAUSED`. `REQUIRES_EXPLICIT_RETRY` só entra na passada corrente quando o operador passa `--retry-rejected` (ou um filtro mais granular — TASKS decide a granularidade exata da flag, ex.: por spec específica) — nesse caso o driver simplesmente inclui essas unidades também, emitindo `START_ATTEMPT` normalmente (transição já permitida por `checkpoint/checkpoint_entry.py::transition()`, nenhuma operação nova de "reset" é necessária).

## 3. Planejamento somente-leitura (DEC-009) — `orchestration/dry_run.py`

```python
@dataclass(frozen=True, slots=True)
class ReadOnlyRepos:
    """Bundle estruturalmente incapaz de escrever — nenhum atributo aqui é uma
    função de save/upsert/insert. plan_operation() só recebe ISSO, nunca os
    ports de escrita usados pelo driver real — a garantia de "dry-run nunca
    muta nada" vem da assinatura de tipo, não apenas de uma convenção."""

    get_collection_run: Callable[[str], CollectionRun | None]
    list_incomplete_runs: Callable[[str], list[CollectionRun]]
    list_all_spec_identities: Callable[[], list[SpecIdentity]]
    get_current_state: Callable[[str], CurrentSpecState | None]
    get_authoritative_manifest: Callable[[str, str], SpecGroupManifest | None]
    get_pending_groups: Callable[[str, str], list[tuple[str, str]]]


def plan_operation(
    repos: ReadOnlyRepos,
    *,
    resume_run_id: str | None,
    new_run: bool,
    scope: str,
    limit_specs: int | None,
    limit_groups: int | None,
    spec_filter: list[str] | None,
    force: list[str] | None,
) -> OperationalPlan:
    """Reproduz a MESMA decisão de select_run() (§1) e os MESMOS filtros do
    driver real (contracts/browser-transport-contract.md §3), mas:
      - nunca chama save_collection_run / process_capture / upsert_checkpoint
        / transport.navigate — nenhuma dessas funções está sequer disponível
        em ReadOnlyRepos;
      - quando a seleção de run seria AmbiguousResumeError/IncompatibleResumeRunError,
        reporta isso em OperationalPlan.run_decision como texto, em vez de levantar
        (um dry-run nunca "falha" por uma condição que ele existe justamente para
        revelar ao operador antes de uma execução real)."""
```

**Propriedade estrutural** (não apenas comportamental): como `ReadOnlyRepos` não inclui nenhuma função de escrita, é **impossível** para `plan_operation()` mutar qualquer estado — não há função a chamar. Isso é verificável por um teste unitário que constrói `ReadOnlyRepos` com todas as leituras stubadas e nenhuma outra dependência, e por `mypy --strict` (uma tentativa de chamar `repos.save_collection_run(...)` dentro de `plan_operation()` simplesmente não compila — `AttributeError` estático).

## 4. CLI — superfície de opções (`cli/main.py`, `cli/options.py`)

```
amayama-scraper run
  --resume RUN_ID          # mutuamente exclusivo com --new-run
  --new-run                # mutuamente exclusivo com --resume
  --dry-run                # somente-leitura (DEC-009) — ignora --retry-rejected/--force
                            # apenas para fins de navegação real (não afeta a leitura do plano)
  --limit-specs N
  --limit-groups N
  --spec STABLE_KEY         # repetível — filtra por identidade já descoberta (FR-025)
  --retry-rejected          # inclui REQUIRES_EXPLICIT_RETRY na passada atual (DEC-006)
  --force STABLE_KEY        # repetível — bypassa o skip de "já VALID" para essas specs (DEC-008)
  --cdp-host HOST           # default 127.0.0.1 (env AMAYAMA_CDP_HOST)
  --cdp-port PORT           # default 9222 (env AMAYAMA_CDP_PORT)
  --min-interval SECONDS    # intervalo mínimo entre navegações (FR-029), default técnico documentado em research.md §17
  --transport-max-retries N
  --transport-backoff-seconds F
  --challenge-poll-interval SECONDS
  --challenge-timeout SECONDS   # opcional; ausente = espera indefinida (research.md §11)
  --db-path PATH             # default sob controle de configuração do projeto (TASKS decide o caminho padrão)
  --raw-root PATH
```

**Regras de validação da CLI** (antes de chamar `select_run()`/`plan_operation()`):
- `--resume` e `--new-run` juntos → erro de uso imediato (nunca chega à camada de orquestração).
- `--dry-run` com `--retry-rejected`/`--force` → aceito; o plano exibido reflete o que essas flags fariam em uma execução real, mas nada é escrito (DEC-009 — "incluindo qual decisão de resume seria tomada").
- Nenhuma flag aceita uma lista de códigos de catálogo hardcoded como valor especial/atalho — `--spec` sempre referencia uma identidade já persistida (`stable_key`), nunca um literal de domínio embutido na CLI (FR-009).

**Rastreabilidade**: FR-018 a FR-027, DEC-005, DEC-006, DEC-008, DEC-009.
