-- data-model.md §15 (SpecGroupManifest)

CREATE TABLE spec_group_manifest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_key TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_capture_id TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    manifest_complete INTEGER NOT NULL,
    validation_evidence_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_spec_group_manifest_spec_run ON spec_group_manifest (spec_key, run_id);
