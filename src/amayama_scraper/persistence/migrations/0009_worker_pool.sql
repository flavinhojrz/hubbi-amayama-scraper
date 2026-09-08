-- data-model.md §1-§4 (005-performance-worker-pool) — puramente aditivo,
-- zero ALTER TABLE sobre schema existente (001-004).

CREATE TABLE spec_lease (
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    spec_key TEXT NOT NULL,
    owner TEXT NOT NULL,
    -- lease_token (005 hardening, BLOCKER 1 — fencing): incrementado a cada
    -- claim/renovação/takeover bem-sucedido. Toda escrita de estado da spec
    -- no caminho paralelo valida (owner, lease_token) atomicamente antes de
    -- persistir — nunca confia apenas em `owner` (um worker "antigo" que
    -- ainda tem `owner` correto mas um `lease_token` desatualizado, por
    -- exemplo após o próprio worker renovar, nunca deveria acontecer, mas a
    -- checagem cobre o par inteiro por definição).
    lease_token INTEGER NOT NULL DEFAULT 0,
    acquired_at TEXT NOT NULL,
    renewed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (run_id, spec_key)
);

CREATE TABLE rate_limiter_state (
    run_id TEXT PRIMARY KEY REFERENCES collection_run (run_id),
    effective_concurrency INTEGER NOT NULL,
    stable_since TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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

CREATE TABLE worker_heartbeat (
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    worker_id TEXT NOT NULL,
    pid INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT NOT NULL,
    PRIMARY KEY (run_id, worker_id)
);

-- spec_pool_disposition (005 hardening, BLOCKER 2 — 2ª rodada: terminalidade
-- real via disposição explícita, nunca backoff temporal). Uma linha por
-- (run_id, spec_key) reflete o resultado da ÚLTIMA passagem sem progresso;
-- limpa (DELETE) assim que a spec progride de novo — não é dado de auditoria
-- (checkpoint_entry/spec_snapshot continuam a fonte de verdade de progresso,
-- Constitution §4), apenas coordenação de elegibilidade de claim.
CREATE TABLE spec_pool_disposition (
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    spec_key TEXT NOT NULL,
    -- 'MANUAL_RETRY_REQUIRED' (nunca reelegível em execução normal, só
    -- --retry-rejected) | 'DEFERRED_THIS_SESSION' (inelegível apenas para
    -- pool_session_id; nova invocação de run_pool() pode tentar de novo).
    state TEXT NOT NULL,
    pool_session_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, spec_key)
);
