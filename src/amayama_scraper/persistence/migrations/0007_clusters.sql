-- data-model.md §9 (ClusterAssignment). Um spec_identity_ref tem no máximo
-- uma assignment vigente — assign() faz upsert, invalidando (sobrescrevendo)
-- qualquer assignment anterior sob outra versão (T193).

CREATE TABLE cluster_assignment (
    spec_identity_ref TEXT PRIMARY KEY REFERENCES spec_registry (stable_key),
    cluster_key TEXT NOT NULL,
    normalizer_version TEXT NOT NULL,
    fingerprint_version TEXT NOT NULL
);

CREATE INDEX idx_cluster_assignment_cluster_key ON cluster_assignment (cluster_key);
