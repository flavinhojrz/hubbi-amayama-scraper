-- data-model.md §1 (SpecIdentity), §14 (DiscoveredSpecEntry), §12 (CurrentSpecState)

CREATE TABLE spec_registry (
    stable_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    vehicle_model TEXT NOT NULL,
    market TEXT NOT NULL,
    model_code TEXT NOT NULL,
    amayama_catalog_id TEXT NOT NULL,
    production_period_raw TEXT NOT NULL,
    source_url TEXT NOT NULL,
    production_start TEXT,
    production_end TEXT,
    grade TEXT,
    configuration TEXT
);

CREATE TABLE discovered_spec_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stable_key TEXT NOT NULL REFERENCES spec_registry (stable_key),
    market TEXT NOT NULL,
    model_code TEXT NOT NULL,
    amayama_catalog_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_capture_id TEXT NOT NULL,
    production_period_raw TEXT,
    production_start TEXT,
    production_end TEXT,
    grade TEXT,
    configuration TEXT,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_discovered_spec_entry_stable_key ON discovered_spec_entry (stable_key);

CREATE TABLE current_spec_state (
    spec_identity_ref TEXT PRIMARY KEY REFERENCES spec_registry (stable_key),
    latest_snapshot_id TEXT NOT NULL,
    cluster_key TEXT
);
