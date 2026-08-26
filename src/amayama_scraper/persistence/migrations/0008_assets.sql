-- data-model.md §10 (ResolvedImage)

CREATE TABLE asset_resolution (
    spec_identity_ref TEXT PRIMARY KEY REFERENCES spec_registry (stable_key),
    origin_spec_ref TEXT NOT NULL,
    image_url_or_ref TEXT NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    resolved_within_cluster_key TEXT
);
