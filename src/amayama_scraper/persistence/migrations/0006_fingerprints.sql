-- data-model.md §7 (FingerprintSet) — colunas associadas ao snapshot (US3)

ALTER TABLE spec_snapshot ADD COLUMN fingerprint_version TEXT;
ALTER TABLE spec_snapshot ADD COLUMN structure_hash TEXT;
ALTER TABLE spec_snapshot ADD COLUMN spec_parts_hash TEXT;
ALTER TABLE spec_snapshot ADD COLUMN schema_semantic_hash TEXT;
ALTER TABLE spec_snapshot ADD COLUMN image_hash TEXT;

CREATE INDEX idx_spec_snapshot_spec_parts_hash ON spec_snapshot (spec_parts_hash);
