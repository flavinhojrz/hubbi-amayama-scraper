-- data-model.md §6 (SpecSnapshot), §13b (idempotência de snapshot)
-- Fingerprint columns (structure_hash/spec_parts_hash/schema_semantic_hash/
-- image_hash/fingerprint_version) são adicionadas por 0006_fingerprints.sql —
-- ownership de US3, não desta migration (US6).

CREATE TABLE spec_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    spec_identity_ref TEXT NOT NULL REFERENCES spec_registry (stable_key),
    idempotency_key TEXT NOT NULL UNIQUE,
    collected_at TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    normalizer_version TEXT NOT NULL,
    collection_complete INTEGER NOT NULL,
    state TEXT NOT NULL,
    counts_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_spec_snapshot_spec_identity_ref ON spec_snapshot (spec_identity_ref);
