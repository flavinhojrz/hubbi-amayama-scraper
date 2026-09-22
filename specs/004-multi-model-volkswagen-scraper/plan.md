# Implementation Plan: Multi-Model Volkswagen Scraper — Isolamento Operacional

**Branch**: `004-multi-model-volkswagen-scraper` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-multi-model-volkswagen-scraper/spec.md`

## Summary

Substituir a passagem solta de `manufacturer/vehicle_model/market` (introduzida
em 002) por uma única estrutura tipada e validada (`CollectionContext`),
tornar `build_scope`/`build_market_index_url` canônicos e sem colisão, validar
o `CollectionContext` contra o `CollectionRun.scope` persistido em todo ponto
de execução interna (`process_capture`, `run_collection_driver`), validar o
`market` efetivamente retornado pelo MARKET_INDEX contra o contexto do run, e
provar isolamento total entre modelos no mesmo banco com 6 cenários de teste
(A–F). Nenhuma mudança de schema, nenhuma migração, nenhuma alteração de
parser EPC/fingerprints/snapshots/equivalência/análise 003/CAPTCHA.

## Technical Context

**Language/Version**: Python 3.11 (mypy strict)

**Primary Dependencies**: stdlib (`dataclasses`, `re`), sqlite3 — nenhuma
dependência nova.

**Storage**: SQLite (`amayama.db`) — schema inalterado, nenhuma migração.

**Testing**: pytest (`tests/unit`, `tests/integration`)

**Target Platform**: Windows/PowerShell (ambiente do PO) e Linux — sem uso de
API específica de OS.

**Project Type**: single project (CLI + biblioteca de domínio)

**Performance Goals**: N/A (mudança estrutural, não de performance) — custo
adicional aceito: 1 leitura extra de `CollectionRun` por `process_capture()`/
`run_collection_driver()` (SQLite local, indexado por PK, desprezível frente
ao custo de rede/parsing já existente por captura).

**Constraints**: nenhuma coleta real; nenhum commit; nenhuma migração
destrutiva; compatibilidade total com defaults históricos da CLI e com o
banco/dados já existentes da Amarok.

**Scale/Scope**: mesmo escopo de 002 (Volkswagen/Amayama), sem novo volume de
dados.

## Constitution Check

*GATE: relido antes desta fase (Constitution §5, §6, §12, §14; ver CLAUDE.md).*

- §5 (Coleta e segurança): sem bypass de CAPTCHA/challenge — inalterado.
- §6 (Separação de responsabilidades): `CollectionContext`/`build_scope`/
  `parse_scope` vivem em `domain/` (puro, sem I/O); a validação
  contexto-vs-run vive em `orchestration/` (camada de composição), nunca no
  parser (`parsing/market_index.py` permanece intocado — FR de spec.md
  "Assumptions").
- §12 (Qualidade e testes): toda regra estrutural nova (FR-001 a FR-064) tem
  teste automatizado correspondente na Fase de tasks abaixo.
- §13 (Versionamento): nenhuma versão de parser/normalizer/fingerprint muda —
  esta feature não altera nenhum algoritmo versionado, apenas a camada de
  contexto operacional acima deles.
- **Gate PASSA.** Nenhuma violação a justificar em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/004-multi-model-volkswagen-scraper/
├── spec.md               # este documento de especificação
├── plan.md                # este arquivo
└── tasks.md               # lista de tasks executável
```

Sem `research.md`/`data-model.md`/`contracts/` dedicados — o design already
está inteiramente especificado no pedido do PO (spec.md acima) e neste plan;
não há incerteza técnica residual que justifique uma fase de pesquisa
separada (mesmo racional de "Assumptions" em spec.md).

### Source Code (repository root)

```text
src/amayama_scraper/
├── domain/
│   ├── collection_context.py   # NOVO — CollectionContext, normalize_scope_component,
│   │                            #        build_scope, parse_scope, exceções
│   └── discovery.py             # build_market_index_url() passa a receber CollectionContext
├── checkpoint/
│   └── collection_run.py        # CollectionRun.__post_init__ valida via parse_scope();
│                                  # build_scope local antigo é removido (superset em domain/)
├── orchestration/
│   ├── pipeline.py               # process_capture()/run_collection() exigem `context`;
│   │                              # validação contexto-vs-run; validação de market MARKET_INDEX
│   └── collection_driver.py      # run_collection_driver()/await_challenge_resolution() exigem
│                                  # `context`; validação contexto-vs-run antes de navegar;
│                                  # aborta run em critical_error de MARKET_INDEX
└── cli/
    └── main.py                   # constrói CollectionContext a partir dos args (defaults
                                    # históricos preservados) e o repassa

tests/
├── unit/
│   ├── test_collection_context.py       # NOVO — normalização, validação, round-trip
│   └── test_build_market_index_url.py   # atualizado para CollectionContext
├── integration/
│   ├── test_multi_model_isolation.py    # NOVO — cenários A–F
│   └── (arquivos existentes atualizados para a nova assinatura de process_capture/
│        run_collection_driver — ver tasks.md Fase 6)
└── support.py                            # NOVO — AMAROK_CONTEXT/GOL_CONTEXT compartilhados
```

**Structure Decision**: projeto single (já estabelecido por 001/002/003).
`CollectionContext` entra em `domain/` por ser um tipo puro sem I/O, no mesmo
nível de `SpecIdentity`/`DiscoveredSpecEntry`. A validação contexto-vs-run
(que precisa ler `CollectionRun` do banco) fica em `orchestration/`, a única
camada autorizada a compor domínio + adapters concretos (Constitution §6,
já documentado em `orchestration/pipeline.py`).

## Complexity Tracking

Nenhuma violação de Constitution Check — tabela não aplicável.
