-- Repair do bug de manifest truncado: descoberta autoritativa categoria-a-
-- categoria (uma página base nunca decide completude sozinha). Puramente
-- aditiva — zero ALTER TABLE sobre schema existente (0001-0009).
--
-- spec_category_visit — espelha o formato/semântica de checkpoint_entry
-- (data-model.md §11/§13a), mas em tabela PRÓPRIA: uma visita de categoria
-- NUNCA pode aparecer em checkpoint_repo.list_accepted() (usado por
-- plan_finalization() para montar a árvore de GROUP_DETAIL aceitos) — uma
-- linha de visita de categoria misturada ali corromperia a finalização
-- (parse_group_detail() seria chamado sobre uma página de categoria, que
-- não tem a estrutura de um GROUP_DETAIL).
CREATE TABLE spec_category_visit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES collection_run (run_id),
    spec_key TEXT NOT NULL,
    category_slug TEXT NOT NULL,
    status TEXT NOT NULL,
    raw_capture_id TEXT REFERENCES raw_capture (capture_id),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    completed_at TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (run_id, spec_key, category_slug)
);
