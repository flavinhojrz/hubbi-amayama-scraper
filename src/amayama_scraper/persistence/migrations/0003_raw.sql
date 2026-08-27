-- data-model.md §4a (RawBlob, física, deduplicada) / §4b (RawCapture, Observation, nunca colapsada)

CREATE TABLE raw_blob (
    content_hash TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE raw_capture (
    capture_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    content_hash TEXT NOT NULL REFERENCES raw_blob (content_hash),
    source_url TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    capture_kind TEXT NOT NULL,
    acquisition_mode TEXT NOT NULL,
    expected_identity_context_json TEXT,
    collection_metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_raw_capture_content_hash ON raw_capture (content_hash);
CREATE INDEX idx_raw_capture_run_id ON raw_capture (run_id);
