# Data Model: Performance Worker Pool

**Feature**: `005-performance-worker-pool` | **Spec**: [spec.md](./spec.md)

Quatro entidades novas, todas persistidas em SQLite (Constitution: SQLite/WAL
continua sendo a única fonte de verdade — FR-030). Nenhuma entidade existente
(001–004) é alterada; migration puramente aditiva.

## 1. `spec_lease` — claim/lease atômico (US2)

```sql
-- persistence/migrations/0009_worker_pool.sql
CREATE TABLE spec_lease (
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    spec_key TEXT NOT NULL,
    owner TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    renewed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (run_id, spec_key)
);
```

- `owner`: identificador opaco do worker (ex.: `f"{run_id}:{worker_index}:{pid}"`)
  — nunca reutilizado por dois processos vivos simultâneos.
- Chave primária `(run_id, spec_key)` — no máximo uma linha por spec por run,
  reforçando FR-012 (uma spec, um dono, por vez) estruturalmente no schema
  (não apenas por convenção do código chamador).
- Nenhum `DELETE` no caminho normal — liberação é uma sobrescrita
  (reclaim por outro worker) ou simplesmente o fim natural do run; linhas de
  lease de runs completos não são limpas por esta feature (auditabilidade —
  Constitution §4; limpeza é responsabilidade operacional futura, fora de
  escopo).

### Operação de claim (atômica, `BEGIN IMMEDIATE ... COMMIT`)

```sql
INSERT INTO spec_lease (run_id, spec_key, owner, acquired_at, renewed_at, expires_at)
VALUES (:run_id, :spec_key, :owner, :now, :now, :expires_at)
ON CONFLICT (run_id, spec_key) DO UPDATE SET
    owner = excluded.owner,
    acquired_at = excluded.acquired_at,
    renewed_at = excluded.renewed_at,
    expires_at = excluded.expires_at
WHERE spec_lease.owner = excluded.owner        -- renovação pelo mesmo dono
   OR spec_lease.expires_at <= :now             -- recovery de lease expirado
```

Seguido de uma leitura de confirmação (`SELECT owner FROM spec_lease WHERE
run_id=? AND spec_key=?`) dentro da mesma transação: se `owner == :owner`, o
claim foi bem-sucedido (inserção nova, renovação, ou recovery); caso
contrário, outro worker já detém um lease válido — o claim falha e o worker
tenta a próxima spec candidata. A cláusula `WHERE` do `DO UPDATE` é o ponto
de atomicidade: quando falsa, o SQLite mantém a linha existente intacta (o
conflito "vence" sem sobrescrever), nunca uma escrita parcial.

`BEGIN IMMEDIATE` (já usado por `persistence/db.py::transaction()`) garante
que, entre processos, o SQLite serializa essa transação inteira via seu
único-escritor + `busy_timeout=5000` já configurado — nenhuma race window
entre o `INSERT ... ON CONFLICT` e a leitura de confirmação.

## 2. `rate_limiter_state` — concorrência efetiva adaptativa (US3)

```sql
CREATE TABLE rate_limiter_state (
    run_id TEXT PRIMARY KEY REFERENCES collection_run (run_id),
    effective_concurrency INTEGER NOT NULL,
    stable_since TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

- Uma linha por `run_id`, inicializada com `effective_concurrency =
  --workers` e `stable_since = started_at do run` na primeira leitura
  (lazy-init, sem migration de dados).
- `stable_since`: timestamp desde o qual nenhum `ChallengeEvent` foi
  observado — usado para decidir a recuperação gradual (FR-064).

### Função pura subjacente (`orchestration/rate_limiter.py`)

```python
@dataclass(frozen=True, slots=True)
class RateLimiterConfig:
    max_concurrency: int              # == --workers
    challenge_window_seconds: float
    challenge_threshold: int
    stability_seconds: float

@dataclass(frozen=True, slots=True)
class RateLimiterState:
    effective_concurrency: int
    stable_since: datetime

def on_challenge_observed(
    state: RateLimiterState, now: datetime, config: RateLimiterConfig,
    recent_challenge_count_in_window: int,
) -> RateLimiterState:
    """FR-063: decrementa em 1 (piso 1) quando o limiar é atingido dentro da
    janela; sempre reinicia stable_since ao decrementar."""

def on_stability_tick(
    state: RateLimiterState, now: datetime, config: RateLimiterConfig,
) -> RateLimiterState:
    """FR-064: incrementa em 1 (teto max_concurrency) quando
    (now - stable_since) >= stability_seconds; reinicia stable_since."""
```

Ambas as funções são puras (sem I/O) — testáveis com `now`/estado
fabricados, sem SQLite (SC-004). A camada de persistência
(`persistence/repositories/rate_limiter_repo.py`) apenas lê o estado atual,
aplica a função pura, e grava o resultado — nunca decide a política.

## 3. `challenge_event` — log de challenges (US3, US4)

```sql
CREATE TABLE challenge_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    worker_id TEXT NOT NULL,
    spec_key TEXT,
    capture_kind TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX idx_challenge_event_run_observed ON challenge_event (run_id, observed_at);
```

- Uma linha por entrada no laço `await_challenge_resolution()` (inserida no
  primeiro `CHALLENGE_WAITING`, atualizada com `resolved_at` no
  `CHALLENGE_RESOLVED`/`CHALLENGE_TIMEOUT`).
- Fonte única tanto do contador do rate limiter (`recent_challenge_count_in_window`,
  FR-063) quanto das métricas "challenges"/"challenges/hora"/"tempo total
  esperando challenge" (US4) — uma única tabela evita dois lugares que
  poderiam divergir sobre "o que conta como challenge".
- `spec_key` é `NULL` para o challenge do nível MARKET_INDEX (mesma
  convenção de `expected_identity_context` opcional já usada em
  `collection_driver.py`).

## 4. `worker_heartbeat` — apenas para a métrica "workers ativos" (US4)

```sql
CREATE TABLE worker_heartbeat (
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    worker_id TEXT NOT NULL,
    pid INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT NOT NULL,
    PRIMARY KEY (run_id, worker_id)
);
```

- Atualizado pelo próprio worker a cada renovação de lease (reuso do mesmo
  ponto de heartbeat de US2 — nenhum timer adicional).
- "Workers ativos" (métrica) = contagem de linhas com
  `last_heartbeat_at >= now - heartbeat_staleness_seconds` (janela curta,
  ex. `2 * lease_seconds`) — nunca usada para decisão de claim/lease
  (responsabilidade exclusiva de `spec_lease`, US2) — apenas observabilidade
  (US4), explicitamente fora do caminho crítico de correção.

## Relação com entidades existentes (001–004, inalteradas)

| Entidade 005        | Referencia (FK lógica) | Nunca duplica          |
|----------------------|------------------------|-------------------------|
| `spec_lease`         | `collection_run.run_id`| `checkpoint_entry`, `spec_group_manifest`, `spec_snapshot` |
| `rate_limiter_state`| `collection_run.run_id`| —                        |
| `challenge_event`    | `collection_run.run_id`| —                        |
| `worker_heartbeat`   | `collection_run.run_id`| —                        |

Nenhuma coluna nova em `checkpoint_entry`, `collection_run`,
`spec_group_manifest`, `spec_snapshot`, `current_spec_state`,
`discovered_spec_entry`, `spec_registry`, `raw_capture`, `raw_blob` — 005 é
puramente aditiva (nova migration `0009_worker_pool.sql`, quatro `CREATE
TABLE` novos, zero `ALTER TABLE`).
