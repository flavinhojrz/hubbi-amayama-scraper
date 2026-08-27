# Relatório de aceitação — quickstart.md

**Feature**: `001-amarok-ama-br-ingestion` | **Preenchido**: 2026-08-26, durante a implementação (Issue #7) | **Suíte completa**: 443 testes, `pytest --cov` 96.12% (limiar 90%), `mypy --strict` limpo (99 arquivos), `ruff check`/`ruff format --check` limpos.

Este relatório mapeia cada Cenário de `quickstart.md` ao(s) teste(s) real(is) que o exercitam nesta implementação — os caminhos de arquivo abaixo são os efetivamente criados (podem diferir dos nomes ilustrativos do `quickstart.md`, que é um guia de referência, não a decomposição normativa; `tasks.md` é a fonte normativa de nomes de arquivo).

| Cenário | Status | Teste(s) |
|---|---|---|
| 0 — Enumeração market index | ✅ PASS | `tests/integration/test_market_discovery_to_registry.py`, `tests/parser/test_market_index_parsing.py` |
| 1 — Identidade não depende só de `model_code` | ✅ PASS | `tests/unit/test_market_index_parsing.py::test_same_model_code_diff_catalog_id`, `tests/unit/test_spec_identity.py` |
| 2 — Raw preservado antes de validação | ✅ PASS | `tests/unit/test_accept_capture.py`, `tests/unit/test_raw_observation_distinctness.py` |
| 3 — Rejeição de challenge/tradução/inválido | ✅ PASS | `tests/unit/test_classify_capture_single_signal.py`, `test_classify_capture_precedence.py` |
| 4 — Determinismo de normalização/fingerprint | ✅ PASS | `tests/unit/test_fingerprint_set_determinism.py`, `test_image_change_does_not_affect_parts_hash.py` |
| **5 — Equivalência exata nos 3 pares de evidência real** | 🛑 **BLOQUEADO** | não implementado — ver "Blocker" abaixo |
| 6 — Representante determinístico | ✅ PASS | `tests/unit/test_representative_criterion_*.py` (5 arquivos, um por critério) |
| 7 — Fallback de imagem controlado | ✅ PASS | `tests/unit/test_image_fallback_requires_exact_cluster.py`, `test_image_fallback_rejected_without_equivalence.py` |
| 8 — Snapshots imutáveis e reprocessamento | ✅ PASS | `tests/integration/test_finalize_new_collection_supersedes.py`, `test_reprocessing_creates_new_snapshot.py` |
| 9 — Checkpoint/resume hierárquico (A–E) | ✅ PASS | `tests/integration/test_checkpoint_resume_skips_accepted.py`, `test_checkpoint_resume_full.py` (inclui Cenário E — restart real) |
| 10 — Pipeline integrado ponta-a-ponta | ✅ PASS | `tests/integration/test_pipeline_end_to_end.py` |
| 11 — Idempotência/atomicidade | ✅ PASS | `tests/integration/test_idempotency_and_atomicity_full.py`, `test_finalize_atomicity.py` |

## Blocker — Cenário 5

Os três pares de evidência real (`2HBC3X↔S1BC3X`, `S6BC74↔S7BC74`, `S7BC8A-62184↔AGDC8A-62169`) e o caso `S7BC8A-61189` (Cenário 1/T248) exigem, cada um, um `manifest.html` real + um `.html` real por grupo capturado de cada lado do par (tasks.md Phase 16, T245–T248). A evidência real disponível nesta sessão (fornecida pelo PO em 2026-08-26) cobre apenas a página de índice do mercado AMA-BR (Nível A) e a navegação de UMA spec (`S1BC3X-56087`, Nível B) — nenhum `manifest.html` para os outros códigos, e nenhuma página de `GROUP_DETAIL` real para nenhuma spec. T245–T249 permanecem não implementadas por essa razão (mesma disciplina de "não inventar fixture" já aplicada em T073–T078) — ver a nota de blocker em `tasks.md` Phase 16 e o relatório de entrega para a pergunta formal ao PO.

Toda a lógica que o Cenário 5 exercitaria (`evaluate_parts_relation`, `is_comparison_valid`, `build_equivalence_class`) já está implementada e coberta por testes com dados sintéticos/reais-derivados equivalentes em conteúdo (`tests/unit/test_parts_relation.py`, `tests/integration/test_pipeline_end_to_end.py`) — o que falta é especificamente a fixação como *regressão sobre os pares nomeados na spec*, que requer a evidência real ainda não disponível.

## Suíte completa (comandos executados)

```
pytest --cov=amayama_scraper --cov-report=term-missing   # 443 passed, 96.12% (limiar 90%)
mypy --strict src/                                          # Success: no issues found in 99 source files
ruff check src/ tests/                                       # All checks passed
ruff format --check src/ tests/                               # 242 files already formatted
```
