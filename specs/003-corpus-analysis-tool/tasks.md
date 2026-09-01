# Tasks: Ferramenta de Análise do Corpus Coletado

**Feature**: `003-corpus-analysis-tool` | **Input**: `spec.md`, `plan.md` (mesma branch; aprovação do PO registrada em DEC-001 — implementação autorizada diretamente, sem gate intermediário por artefato).

## Fase 1 — Extensões aditivas aos repositórios (sem migration, nenhuma função existente alterada)

- [x] T001 [P] Test: `spec_registry_repo.list_by_scope()` — filtra por `manufacturer`/`vehicle_model`/`market` (case-insensitive), ordenado por `stable_key`, em `tests/integration/test_analysis_repo_reads.py`.
- [x] T002 Implementar `list_by_scope()` em `persistence/repositories/spec_registry_repo.py` — depende de: T001.
- [x] T003 [P] Test: `snapshot_repo.list_latest_snapshot_per_spec()` — retorna o snapshot mais recente por `collected_at` por spec, qualquer `state`, desempate determinístico; lista vazia de refs → dict vazio, em `tests/integration/test_analysis_repo_reads.py`.
- [x] T004 Implementar `list_latest_snapshot_per_spec()` em `persistence/repositories/snapshot_repo.py` — depende de: T003.
- [x] T005 [P] Test: `manifest_repo.list_for_spec()` — todos os manifests de uma spec por qualquer run, mais recente primeiro, em `tests/integration/test_analysis_repo_reads.py`.
- [x] T006 Implementar `list_for_spec()` em `persistence/repositories/manifest_repo.py` — depende de: T005.
- [x] T007 [P] Test: `checkpoint_repo.list_accepted_group_keys_for_spec()` — união de `(category_slug, group_id)` `ACCEPTED` entre runs, em `tests/integration/test_analysis_repo_reads.py`.
- [x] T008 Implementar `list_accepted_group_keys_for_spec()` em `persistence/repositories/checkpoint_repo.py` — depende de: T007.
- [x] T009 [P] Test: `db.connect_read_only()` — abre sem criar arquivo/WAL quando o DB já existe; nunca escreve, em `tests/integration/test_analysis_repo_reads.py`.
- [x] T010 Implementar `connect_read_only()` em `persistence/db.py` — depende de: T009.

## Fase 2 — Pacote `analysis/` (puro, sem I/O)

- [x] T011 [P] Implementar `analysis/types.py` (`ScopeIdentifier`, `DistributionStats`, `Severity`, `Finding`, `ScopeSummary`, `QualityReport`, `RedundancyCluster`, `RedundancyReport`, `GroupSetDiff`, `SpecComparison`).
- [x] T012 [P] Test: `build_scope_summary()` — corpus saudável (totais/distribuição batem com `counts_json` somado manualmente), spec sem snapshot (conta em discovered/problemático, exclui da distribuição), escopo vazio (zeros, sem exceção), em `tests/unit/test_analysis_summary.py`.
- [x] T013 Implementar `analysis/summary.py::build_scope_summary()` — depende de: T011, T012.
- [x] T014 [P] Test: `assess_quality()` — corpus saudável (zero achados ERROR/WARNING), manifest divergente (achado com os dois números), snapshot incompleto/não-VALID, spec zero-peças (achado INFO, nunca ERROR/WARNING), spec sem snapshot, grupo esperado nunca ACCEPTED, em `tests/unit/test_analysis_quality.py`.
- [x] T015 Implementar `analysis/quality.py::assess_quality()` — depende de: T011, T014.
- [x] T016 [P] Test: `build_redundancy_report()` — cluster de tamanho 2 + spec isolada, distintos por hash, taxa de redução, exclusão de snapshot INCOMPLETE/INVALID, em `tests/unit/test_analysis_redundancy.py`.
- [x] T017 Implementar `analysis/redundancy.py::build_redundancy_report()` — reaproveita `equivalence.cluster.cluster_key()` — depende de: T011, T016.
- [x] T018 [P] Test: `compare_specs()` — par EXACT, diff de grupos via manifest, um lado sem snapshot (comparação indisponível, não exceção), em `tests/unit/test_analysis_comparison.py`.
- [x] T019 Implementar `analysis/comparison.py::compare_specs()` — reaproveita `equivalence.evaluate.evaluate_equivalence()` — depende de: T011, T018.
- [x] T020 [P] Test: `to_json_dict()` — determinismo (mesma entrada → mesmo JSON serializado byte a byte; coleções ordenadas), em `tests/unit/test_analysis_json_view.py`.
- [x] T021 Implementar `analysis/json_view.py::to_json_dict()` — depende de: T011, T020.
- [x] T022 Implementar `analysis/render.py::render_text()` (sem teste dedicado de snapshot de string — coberto indiretamente pelo teste end-to-end da CLI, T025) — depende de: T011.

## Fase 3 — CLI própria (não toca `cli/main.py`/`cli/options.py` — pertencem a `002` em andamento)

- [x] T023 [P] Test: `cli/analyze.py::build_arg_parser()` — 4 subcomandos, flags obrigatórios de escopo (exceto `compare`), `--json` opcional, em `tests/unit/test_cli_analyze_options.py`.
- [x] T024 Implementar `cli/analyze.py` (parser + `main(argv)`, composição read-only) — depende de: T002, T004, T006, T008, T010, T013, T015, T017, T019, T021, T022, T023.
- [x] T025 [P] Test de integração end-to-end: `main()` sobre fixture SQLite em arquivo temporário — corpus saudável, manifest divergente, snapshot incompleto, spec zero-peças legítima, banco inexistente/escopo inexistente, saída texto vs `--json`, em `tests/integration/test_cli_analyze_end_to_end.py` — depende de: T024.

## Checkpoint final

- [x] T026 Suíte completa (`pytest`), `ruff check`, `mypy` — verdes; testes pré-existentes inalterados/verdes; nenhuma migration nova; nenhuma dependência nova em `pyproject.toml`.
