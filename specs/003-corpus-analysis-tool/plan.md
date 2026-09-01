# Implementation Plan: Ferramenta de Análise do Corpus Coletado

**Feature**: `003-corpus-analysis-tool` | **Input**: `spec.md` (mesma branch, aprovação registrada em DEC-001)

## Resumo da abordagem

Nenhuma migration. Nenhuma dependência nova. Reaproveita integralmente `equivalence/`, `fingerprints/`, os tipos de domínio existentes e o padrão de repositório já estabelecido (`persistence/repositories/*.py`, função pura por arquivo, `conn: sqlite3.Connection` como primeiro argumento). Um pacote novo (`analysis/`) concentra a lógica pura (sem `sqlite3`/I/O), e um entrypoint novo e independente (`cli/analyze.py`) faz a composição (abre conexão somente-leitura, chama repositórios, chama `analysis/`, formata saída).

## Por que um entrypoint CLI separado, e não estender `cli/main.py`/`cli/options.py`

`src/amayama_scraper/cli/` é um pacote inteiramente não commitado, pertencente à feature `002-amarok-ama-br-browser-scraper`, ainda em implementação nesta mesma branch (tasks em andamento, sem revisão do Codex, sem validação do PO). Editar `cli/main.py`/`cli/options.py` misturaria o diff de duas features não relacionadas e comprometeria a rastreabilidade de `002`. `cli/analyze.py` é um arquivo novo, autocontido, com seu próprio `build_arg_parser()`/`main(argv)` — mesmo padrão estrutural de `cli/main.py`, mas zero linha compartilhada.

## Extensões aos repositórios existentes (todas aditivas — nenhuma função existente é alterada)

- `persistence/repositories/spec_registry_repo.py`: `list_by_scope(conn, *, manufacturer, vehicle_model, market) -> list[SpecIdentity]` — filtro case-insensitive sobre `spec_registry`.
- `persistence/repositories/snapshot_repo.py`: `list_latest_snapshot_per_spec(conn, spec_identity_refs) -> dict[str, SpecSnapshot]` — o snapshot mais recente por `collected_at` (qualquer `state`, não só VALID/STALE — a auditoria de qualidade precisa ver INVALID/INCOMPLETE também). Desempate determinístico por `snapshot_id`.
- `persistence/repositories/manifest_repo.py`: `list_for_spec(conn, spec_key) -> list[SpecGroupManifest]` — todos os manifests de uma spec, mais recente primeiro; a lógica de "qual é o manifest vigente" (mais recente com `manifest_complete=True`) fica em `analysis/`, não no repositório.
- `persistence/repositories/checkpoint_repo.py`: `list_accepted_group_keys_for_spec(conn, spec_key) -> frozenset[tuple[str, str]]` — união de `(category_slug, group_id)` `ACCEPTED` através de todos os runs dessa spec.
- `persistence/db.py`: `connect_read_only(db_path) -> sqlite3.Connection` — mesma técnica já usada por `cli/main.py::_connect_read_only` (URI `mode=ro`, com/sem `immutable=1` conforme WAL pendente), reimplementada aqui como função pública e reutilizável em vez de duplicar a lógica dentro de `cli/analyze.py`; não modifica `connect()`/`transaction()` existentes.

## Pacote novo `src/amayama_scraper/analysis/`

Sem imports de `sqlite3`/`selenium`/etc. (mesma disciplina do `DOMAIN_LAYER_PACKAGES`, embora este pacote não precise ser adicionado à lista de enforcement do teste de fronteiras — é uma extensão, não uma mudança de contrato existente).

- `types.py` — `ScopeIdentifier`, `DistributionStats`, `Severity` (`StrEnum`: `INFO`/`WARNING`/`ERROR`), `Finding`, `ScopeSummary`, `QualityReport`, `RedundancyCluster`, `RedundancyReport`, `GroupSetDiff`, `SpecComparison`.
- `summary.py::build_scope_summary(scope, specs, latest_snapshot_by_spec) -> ScopeSummary` — pura (US1).
- `quality.py::assess_quality(scope, specs, latest_snapshot_by_spec, manifests_by_spec, accepted_keys_by_spec) -> QualityReport` — pura (US2); cada `Finding` carrega `code`, `severity`, `spec_stable_key`, `message` (explica o motivo) e `details`.
- `redundancy.py::build_redundancy_report(scope, specs, latest_snapshot_by_spec) -> RedundancyReport` — pura (US3); usa `equivalence.cluster.cluster_key()` para agrupar (nunca reimplementa comparação de hash); filtra por elegibilidade `collection_complete and state in {VALID, STALE}` (mesmo critério de `equivalence.validity.is_comparison_valid`, aplicado a um único snapshot em vez de par).
- `comparison.py::compare_specs(scope, identity_a, identity_b, snapshot_a, snapshot_b, manifest_a, manifest_b) -> SpecComparison` — pura (US4); delega hash/relação a `equivalence.evaluate.evaluate_equivalence()`.
- `render.py::render_text(...) -> str` — apresentação texto, uma função por tipo de relatório.
- `json_view.py::to_json_dict(...) -> dict` — apresentação JSON, determinística (chaves ordenadas, coleções convertidas para listas ordenadas).

## `src/amayama_scraper/cli/analyze.py`

Subcomandos: `summary`, `quality`, `redundancy`, `compare`, todos com `--manufacturer/--vehicle-model/--market` obrigatórios (exceto `compare`, que usa `--spec-a/--spec-b STABLE_KEY`) e `--json` opcional (default: texto). `--db-path` opcional (default `amayama.db`, mesmo default de `cli/main.py`). Sem escopo default implícito — exigir os três flags evita qualquer suposição de escopo não pedida explicitamente. Abre `connect_read_only`; se o arquivo não existir, erro claro (exit code 2) em vez de criar o banco.

## Testes

- `tests/unit/test_analysis_summary.py`, `test_analysis_quality.py`, `test_analysis_redundancy.py`, `test_analysis_comparison.py`, `test_analysis_json_view.py` — puros, fixtures de dataclasses em memória (sem SQLite).
- `tests/integration/test_analysis_repo_reads.py` — as 4 funções de repositório novas, sobre SQLite `:memory:` + `run_migrations()`, mesmo padrão de `tests/integration/test_checkpoint_repo.py`.
- `tests/integration/test_cli_analyze_end_to_end.py` — `cli/analyze.py::main()` ponta a ponta sobre fixture SQLite em arquivo temporário, cobrindo corpus saudável, manifest divergente, snapshot incompleto, spec com zero peças legítima, banco vazio/escopo inexistente, e saída `--json` vs texto.

## Fora do plan (confirmado durante a pesquisa, não uma lacuna a resolver aqui)

- Nenhuma migration: todos os campos necessários já existem.
- Nenhuma dependência nova: `statistics` (stdlib) cobre mín/máx/média/mediana sem pandas.
- Diff de OEMs/peças: fora de escopo (spec.md, "Fora de escopo").
