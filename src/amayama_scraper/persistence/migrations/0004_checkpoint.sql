-- data-model.md §11 (CollectionRun/CheckpointEntry), §13a (idempotência de checkpoint)

CREATE TABLE collection_run (
    run_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    started_at TEXT,
    resumed_at TEXT,
    completed_at TEXT
);

CREATE TABLE checkpoint_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    spec_key TEXT NOT NULL,
    category_slug TEXT NOT NULL,
    group_id TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_capture_id TEXT REFERENCES raw_capture (capture_id),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    completed_at TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (run_id, spec_key, category_slug, group_id)
);
