# Implementation Plan: Scraper Real Amarok AMA-BR — Navegador Assistido, Human-in-the-Loop e Resume

**Branch**: `002-amarok-ama-br-browser-scraper` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/002-amarok-ama-br-browser-scraper/spec.md` (aprovada e clarificada pelo PO — DEC-001 a DEC-009). GitHub Issue #10 — "FEATURE — scraper real Amarok AMA-BR com navegador assistido e resume". PO autorizou explicitamente o avanço para PLAN nesta conversa.

**Governança aplicada**: `.specify/memory/constitution.md`, `docs/sdd/EXECUTION_POLICY.md`, `AGENTS.md`, `CLAUDE.md`. Este PLAN aplica a precedência normativa do projeto sobre qualquer default genérico do Spec Kit — nenhuma "informed guess" foi feita para decisões semânticas; decisões técnicas (HOW) foram tomadas e justificadas em [research.md](./research.md), sempre precedidas de inspeção do código real de `001-amarok-ama-br-ingestion` (research.md §1 traz o inventário de prova).

## Summary

Esta feature adiciona **transporte** (Chrome real via CDP) e **orquestração operacional** (driver de coleta dinâmico, seleção de run, classificação de retry, planejamento dry-run, CLI, observabilidade) sobre o núcleo de ingestão já mergeado de `001-amarok-ama-br-ingestion` — sem criar um segundo core. Toda regra de domínio (identidade, validação, parsing, normalização, fingerprints, equivalência, imagens, snapshots, checkpoint) é reutilizada exatamente como está; nenhuma função existente de `process_capture()`, `classify_capture()`, `route_if_challenge()`, `get_pending_groups()`, `try_finalize_spec_entry()` tem sua assinatura ou comportamento alterado.

Abordagem: um novo pacote de folha `transport/` (único ponto de contato com Selenium, attach via Chrome DevTools Protocol a um Chrome já aberto pelo operador — DEC-007), um punhado de novos módulos dentro do já-existente `orchestration/` (o driver dinâmico de descoberta-e-ação, seleção de run — DEC-005, classificação de retry — DEC-006, planejador read-only de dry-run — DEC-009, reportador de progresso), duas novas *queries* de leitura aditivas sobre tabelas já existentes (nenhuma migration), um novo valor de enum já antecipado pelo próprio código de `001` (`AcquisitionMode.AUTOMATED_BROWSER_CDP`), e um novo pacote `cli/` fino (argparse) que compõe tudo isso. Nenhum artefato de código é criado por este PLAN — apenas os documentos de planejamento.

## Technical Context

**Language/Version**: Python ≥ 3.11 (dev/CI em 3.12) — inalterado de `001`.

**Primary Dependencies**: `beautifulsoup4`/`lxml` (já existentes, inalterados — nenhum parser novo). **Nova**: `selenium>=4.15,<5` (research.md §14), isolada em `transport/chrome_cdp_adapter.py`. Dev: `pytest`/`pytest-cov`/`ruff`/`mypy` (inalterados).

**Storage**: mesmo SQLite (metadados/estado) + filesystem content-addressed (raw) de `001` — DEC-002 reafirmado, nenhum banco novo. Duas novas *queries* de leitura aditivas (`list_incomplete_runs`, `list_all_spec_identities` — data-model.md §7); um ajuste de configuração de conexão (`PRAGMA busy_timeout`, data-model.md §8); nenhuma migration nova.

**Testing**: `pytest`, majoritariamente offline via `BrowserTransport` fake em memória (estendendo `tests/unit/fakes.py`); um pequeno subconjunto de testes do adapter concreto usa `selenium` real apenas para validar construção/wiring com `webdriver.Chrome`/`Options` stubados (nunca abrindo um Chrome de verdade) — ver research.md §14, quickstart.md.

**Target Platform**: estação de desenvolvimento/CI Linux/macOS/WSL — inalterado. Execução real do CLI depende adicionalmente de um Chrome real local acessível via CDP, controlado pelo operador (fora do processo de CI).

**Project Type**: pacote Python interno com um novo ponto de entrada de CLI (`amayama-scraper run`) — a saída funcional continua sendo o modelo de domínio interno já definido por `001` (nenhum contrato de export é criado ou alterado).

**Performance Goals**: nenhum definido (mesma decisão de `001` — determinismo/corretude sobre throughput; navegação é deliberadamente conservadora — FR-028/FR-029).

**Constraints**: núcleo de domínio (`validation/` em diante) continua sem chamadas de rede — o transporte não introduz rede em nenhum módulo além de `transport/`. Nenhum bypass de CAPTCHA/Cloudflare sob nenhuma circunstância (Constitution §5).

**Scale/Scope**: um modelo (Amarok) × um mercado (`AMA-BR`) — `CollectionRun.scope` é uma constante fixa (`FIXED_SCOPE`) já validada pelo próprio domínio (`checkpoint/collection_run.py`), reafirmando o escopo desta feature sem necessidade de novo código de validação.

## Constitution Check

*GATE: Deve passar antes da Fase 0/1. Re-checado após o desenho completo (Fase 1).*

| Princípio (Constitution) | Status | Como este PLAN atende |
|---|---|---|
| §1 Missão | ✅ PASS | Escopo restrito a Amarok/AMA-BR (mesmo `FIXED_SCOPE` de `001`); identidade/proveniência preservadas — nenhuma entidade de `001` é redefinida. |
| §2 Fonte e escopo | ✅ PASS | Fonte continua Amayama; hierarquia modelo→mercado→spec→categoria→grupo→schema→OEM inalterada; `model_code` isolado continua nunca sendo identificador (SpecIdentity intocado). |
| §3 Preservação de identidade | ✅ PASS | `SpecIdentity`/`stable_key()` reutilizados sem alteração; nenhuma nova regra de identidade é criada (spec.md exige explicitamente isso). |
| §4 Raw imutável e auditável | ✅ PASS | `accept_capture()` (inalterado) continua sendo o único caminho de escrita de `RawBlob`/`RawCapture`, sempre antes de qualquer validação — o transporte só entrega `page_source`/`effective_url`/`captured_at`, nunca escreve raw por conta própria (contracts/browser-transport-contract.md §1). Falha de transporte pura (antes de existir conteúdo) nunca produz um raw fabricado (data-model.md §3). |
| §5 Coleta e segurança | ✅ PASS | Attach via CDP a um Chrome já aberto pelo operador (DEC-007) — nunca bypass/evasão/stealth/proxy rotation/manipulação de token (explicitamente proibidos e testáveis — contracts/browser-transport-contract.md §2, research.md §13); `classify_capture()`/`detect_challenge()` continuam a única autoridade; challenge sempre roteado a human-in-the-loop (contracts/browser-transport-contract.md §4), nunca contornado. |
| §6 Separação de responsabilidades | ✅ PASS | `transport/` é uma folha isolada (nenhum módulo de domínio a importa); `orchestration/pipeline.py` permanece sem nenhuma importação de `transport`/`selenium` (research.md §5, §7, §13); novos módulos de orquestração (`run_selection.py`, `retry_classification.py`, `dry_run.py`) são funções puras sem I/O próprio. |
| §7 Normalização conservadora | ✅ PASS | Nenhuma mudança em `normalization/` — não tocado por esta feature. |
| §8 Fingerprints e equivalência | ✅ PASS | Nenhuma mudança em `fingerprints/`/`equivalence/` — não tocados; `finalize_spec_entry()` (que já os invoca) é chamado sem alteração pelo novo driver, exatamente como `run_collection()` já fazia. |
| §9 Classes de equivalência e representante | ✅ PASS | Nenhuma mudança — FR-033 exige explicitamente que esta feature nunca use equivalência para decidir o que coletar. |
| §10 Imagens e fallback | ✅ PASS | Nenhuma mudança em `assets/`. |
| §11 Snapshots e revalidação | ✅ PASS | Nenhuma mudança na máquina de estados de `SpecSnapshot`; DEC-008 (freshness) mantém o MVP sem TTL automático, consistente com a política de freshness já deliberadamente deixada configurável/não fixada por `001`. |
| §12 Qualidade e testes | ✅ PASS | Estratégia 100% offline via `BrowserTransport` fake (contracts/browser-transport-contract.md, quickstart.md); suíte/coverage/ruff/mypy strict mantidos (FR-037). |
| §13 Versionamento | ✅ PASS | Nenhum parser/normalizer/fingerprint version é alterado; `AcquisitionMode` ganha um valor novo sem quebrar compatibilidade (research.md §6). |
| §14 SDD e gates | ✅ PASS | Este PLAN não avança para `/speckit-tasks`; aguarda gate explícito do PO. |

**Nenhuma violação identificada.** Complexity Tracking (abaixo) está intencionalmente vazio.

## Project Structure

### Documentation (this feature)

```text
specs/002-amarok-ama-br-browser-scraper/
├── plan.md                                # este arquivo
├── research.md                            # Phase 0 — decisões técnicas + prova de inspeção do código real
├── data-model.md                          # Phase 1 — entidades novas/estendidas
├── quickstart.md                          # Phase 1 — cenários de validação (offline + Fases A–E reais)
├── contracts/
│   ├── browser-transport-contract.md      # BrowserTransport port + driver de coleta + laço de challenge
│   └── orchestration-contract.md          # DEC-005/DEC-006/DEC-009 algoritmos + superfície CLI
└── tasks.md                               # Phase 2 — NÃO criado por este PLAN
```

### Source Code (repository root) — estrutura ALVO, não criada nesta fase

```text
src/amayama_scraper/
├── ingestion/
│   └── capture_kind.py            # MODIFICADO — + AcquisitionMode.AUTOMATED_BROWSER_CDP (research.md §6)
├── persistence/
│   └── repositories/
│       ├── checkpoint_repo.py     # MODIFICADO — + list_incomplete_runs() (data-model.md §7)
│       └── spec_registry_repo.py  # MODIFICADO — + list_all_spec_identities() (data-model.md §7)
│   └── db.py                      # MODIFICADO — + PRAGMA busy_timeout (data-model.md §8)
├── transport/                     # NOVO pacote — único lugar que importa selenium/CDP
│   ├── __init__.py
│   ├── port.py                    # BrowserTransport (Protocol) + BrowserCapture
│   ├── errors.py                  # TransportError e subclasses (nunca confundidas com ValidationOutcome)
│   └── chrome_cdp_adapter.py      # ChromeCdpTransport — attach via debuggerAddress (Selenium)
├── orchestration/
│   ├── pipeline.py                # INALTERADO — process_capture/run_collection/try_finalize_spec_entry
│   ├── logging.py                 # INALTERADO — reutilizado por progress_reporter.py
│   ├── run_selection.py           # NOVO — DEC-005 (contracts/orchestration-contract.md §1)
│   ├── retry_classification.py    # NOVO — DEC-006 (contracts/orchestration-contract.md §2)
│   ├── collection_driver.py       # NOVO — laço de descoberta-e-ação (contracts/browser-transport-contract.md §3-4)
│   ├── dry_run.py                 # NOVO — DEC-009 (contracts/orchestration-contract.md §3)
│   └── progress_reporter.py       # NOVO — FR-027, construído sobre logging.py::log_event()
└── cli/                           # NOVO pacote — entrypoint fino, sem lógica de domínio
    ├── __init__.py
    ├── main.py                    # parsing de argumentos + composição (único lugar que instancia ChromeCdpTransport)
    └── options.py                 # definição argparse (contracts/orchestration-contract.md §4)

tests/
├── unit/
│   ├── fakes.py                    # ESTENDIDO — + FakeBrowserTransport (implementa BrowserTransport)
│   ├── test_run_selection.py                       # NOVO
│   ├── test_retry_classification.py                # NOVO
│   ├── test_dry_run_zero_mutation.py                # NOVO
│   ├── test_browser_transport_to_process_capture.py # NOVO
│   ├── test_chrome_cdp_adapter.py                   # NOVO — selenium stubado, nunca Chrome real
│   ├── test_no_browser_automation_dependency.py      # ESTENDIDO — allowlist de transport/chrome_cdp_adapter.py (research.md §13)
│   └── test_architecture_boundaries.py                # ESTENDIDO ou irmão — transport/ fora do domain layer
├── integration/
│   ├── test_no_auto_retry_on_validation_rejection.py  # NOVO
│   ├── test_challenge_pause_and_resume.py             # NOVO
│   ├── test_challenge_wrong_page_after_resolution.py  # NOVO
│   ├── test_resume_skips_accepted_and_valid.py        # NOVO
│   └── test_collection_driver_end_to_end_fake.py      # NOVO — MARKET_INDEX→SPEC_NAVIGATION→GROUP_DETAIL→VALID, tudo via fake
├── regression/
│   └── test_market_index_discovery_no_hardcode.py     # NOVO (reaproveita fixtures reais já existentes de 001)
└── fixtures/                        # reaproveitadas de 001 — nenhuma fixture nova de domínio é necessária
                                      # (o transporte não introduz novo HTML a parsear; usa as mesmas
                                      # fixtures MARKET_INDEX/SPEC_NAVIGATION/GROUP_DETAIL já existentes)
```

**Structure Decision**: extensão mínima da estrutura já existente (Constitution §6) — dois pacotes novos (`transport/`, `cli/`), cinco arquivos novos dentro do já-existente `orchestration/`, duas funções aditivas em repositórios já existentes, um ajuste de configuração em `persistence/db.py`, um novo valor de enum em `ingestion/capture_kind.py`. **Nenhum diretório/arquivo listado acima é criado por este PLAN** — esta seção é a especificação da estrutura-alvo para TASKS/implementação, seguindo a mesma convenção que `001-amarok-ama-br-ingestion/plan.md` já estabeleceu.

## Complexity Tracking

> Preencher SOMENTE se o Constitution Check tiver violações a justificar.

Nenhuma violação identificada — tabela intencionalmente vazia.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| _(nenhuma)_ | — | — |

## Integração com o core existente — resumo executivo

| Fluxo alvo (Issue #10) | Componente responsável | Novo ou existente? |
|---|---|---|
| Chrome real via CDP | `transport/chrome_cdp_adapter.py::ChromeCdpTransport` | **Novo** |
| → BrowserTransport | `transport/port.py::BrowserTransport` | **Novo** (port) |
| → captura HTML + provenance | `orchestration/collection_driver.py` (converte `BrowserCapture` → `RawCaptureInput`) | **Novo** (conversão) sobre **existente** (`RawCaptureInput`) |
| → persistência raw | `ingestion/accept.py::accept_capture()` | **Existente**, inalterado |
| → `process_capture()` | `orchestration/pipeline.py::process_capture()` | **Existente**, inalterado |
| → checkpoint/resume | `checkpoint/*`, `orchestration/run_selection.py` (novo, decide QUAL run), `orchestration/retry_classification.py` (novo, decide O QUE tentar) | Máquina de estados **existente**; decisão de orquestração **nova** |
| → manifest/spec navigation | `parsing/spec_group_manifest.py` via `process_capture()` | **Existente**, inalterado |
| → group details | `parsing/group_detail.py` via `process_capture()` | **Existente**, inalterado |
| → `try_finalize_spec_entry()` | `orchestration/pipeline.py::try_finalize_spec_entry()` | **Existente**, inalterado |
| → snapshots/fingerprints/equivalence/output interno | `snapshots/`, `fingerprints/`, `equivalence/`, `export/` | **Existentes**, intocados; equivalência/clustering entre specs continua uma capacidade disponível não invocada automaticamente pelo driver desta feature (nem por `finalize_spec_entry()` hoje) — consistente com FR-033/"Fora de Escopo" (nenhuma otimização de coleta por equivalência histórica); acionar um passo de equivalência em lote após uma execução, se desejado, é uma decisão operacional separada, não um requisito desta feature. |

## Adapter CDP/Selenium — escolha e justificativa (resumo)

Selenium ≥ 4.15 em modo *attach* (`debuggerAddress`) a um Chrome já aberto pelo operador — nunca lançado/gerenciado pelo scraper. Justificativa completa, alternativas consideradas (CDP puro, Playwright, bibliotecas CDP de terceiros) e prova de precedente já validado no próprio repositório (`amayama_browser_fixture_collector.py`, script exploratório não promovido a produção) em **research.md §2**. Endereço configurável (CLI > env > default `127.0.0.1:9222`, nunca hardcoded de forma não-sobrescrevível) em **research.md §3**. Falha de conexão é fail-fast, sem retry/lançamento automático de Chrome, em **research.md §4**.

## Modelo de run/resume (DEC-005) — resumo

`orchestration/run_selection.py::select_run()`, função pura, algoritmo determinístico de 3 ramos (`--resume` explícito / `--new-run` explícito / nenhum dos dois → 0, 1 ou 2+ candidatos incompletos do mesmo `scope`) — nunca escolhe heuristicamente entre múltiplos candidatos. Duas novas *queries* de leitura aditivas (`list_incomplete_runs`, data-model.md §7) sobre a tabela `collection_run` já existente, usando os campos `scope`/`completed_at` já existentes — nenhuma migration. Algoritmo completo em **contracts/orchestration-contract.md §1**; prova de que a estrutura existente (`get_collection_run`/`save_collection_run`) não atende, em **research.md §8**.

## Modelo de retry (DEC-006) — resumo

Duas categorias, nunca misturadas: **falha de transporte** (nunca alcançou `classify_capture()`) — retry local dentro de `ChromeCdpTransport`, configurável, sem persistência de estado adicional além do `attempt_count` já existente; **rejeição de validação** (`INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED`/`critical_error`) — nunca retentada automaticamente, permanece `REJECTED`, só reentra na passada do driver com `--retry-rejected` explícito. `CHALLENGE` mantém seu próprio fluxo (não é "retry" no sentido de DEC-006 — é o laço de pausa/retomada, sempre automático). Prova de que nenhuma nova transição de estado é necessária (REJECTED→IN_PROGRESS já existe em `checkpoint/checkpoint_entry.py::transition()`) em **research.md §9**. Algoritmo de classificação em **contracts/orchestration-contract.md §2**.

## Fluxo de challenge (human-in-the-loop) — resumo

Laço bloqueante de poll (`orchestration/collection_driver.py::await_challenge_resolution()`), intervalo configurável (default técnico 5s), sem timeout por padrão (`--challenge-timeout` opcional), sempre reprocessando via `process_capture()`/`classify_capture()` reais — nunca uma verificação paralela decidindo "resolvido". Proteção contra página errada é **inteiramente reuso** de `detect_invalid_structure()` já existente (nenhum código novo de verificação de URL é autoritativo — apenas um sinal de diagnóstico não-autoritativo adicional). Se o Chrome for fechado durante a espera, `ChromeNotReachableError` interrompe a execução com a unidade preservada em estado retomável. Algoritmo completo em **contracts/browser-transport-contract.md §4**; justificativa em **research.md §11**.

## CLI planejada — resumo

Um subcomando (`run`), ~13 flags (listadas em **contracts/orchestration-contract.md §4**), `argparse` da stdlib (nenhuma dependência de CLI nova). Exemplos executáveis (quando implementado) em **quickstart.md**, incluindo as 5 Fases de validação real (A–E). CLI não implementada por este PLAN.

## Persistência / migrations — confirmação

**Nenhuma migration é necessária.** Duas *queries* de leitura aditivas sobre tabelas já existentes (`collection_run`, `spec_registry` — data-model.md §7), um novo valor de enum sobre uma coluna `TEXT` sem `CHECK` (data-model.md §0), e uma linha de configuração de conexão (`PRAGMA busy_timeout`, data-model.md §8, justificada por concorrência entre processos — research.md §16). A afirmação de `spec.md` FR-032 ("nenhuma nova entidade persistida é estritamente necessária") é confirmada por inspeção direta do schema (`migrations/0001` a `0008` lidos integralmente para as tabelas relevantes — research.md §1, §8, §12).

## Estratégia de testes offline — resumo

`BrowserTransport` fake em memória (`tests/unit/fakes.py`, estendido) é o único ponto de substituição necessário para testar 100% do driver/orquestração sem rede/Chrome real — mesma disciplina já usada por `InMemoryRawBlobStore`/`InMemoryRawCaptureRepository` em `001`. Cobertura exigida detalhada em **quickstart.md** (cenários 0–9) e **spec.md FR-034/FR-035**: seleção de run (4 ramos), classificação de retry (4 categorias), pausa/retomada de challenge, página errada pós-challenge, não-recoleta de `ACCEPTED`/skip de `VALID`, `--force`, dry-run zero-mutação, descoberta sem hardcode, integração transporte→`process_capture()`, comportamento após falhas de transporte simuladas. Um pequeno conjunto adicional (`test_chrome_cdp_adapter.py`) testa o adapter concreto com Selenium stubado, nunca abrindo um Chrome real (research.md §14).

## Plano de validação real — resumo

Fases A–E (attach+descoberta → uma spec com limite → spec completa `VALID` → interrupção+resume → challenge real quando ocorrer) — descritas com comandos concretos em **quickstart.md**. Challenge real não é provocado deliberadamente; os cenários 4–5 offline (fakes) já provam esse comportamento antes de qualquer exposição ao site real.

## Dependências novas — confirmação

Apenas `selenium>=4.15,<5`, adicionada a `[project] dependencies` (não um extra opcional — o CLI real precisa dela). Nenhuma outra dependência (sem `webdriver-manager`, sem `playwright`, sem bibliotecas de progress bar/logging). Justificativa completa em **research.md §14**.

## Segurança arquitetural — confirmação explícita

Esta feature **não** implementa, em nenhum lugar do desenho: solver de CAPTCHA, bypass de Cloudflare, stealth/anti-detecção, rotação de proxy para evasão, manipulação de tokens de challenge, concorrência agressiva, troca da fonte Amayama, ou otimização de coleta por equivalência histórica. Cada uma dessas proibições está refletida em pelo menos um destes lugares verificáveis: `spec.md` "Out of Scope"/DEC-006/DEC-007, `contracts/browser-transport-contract.md` §2 ("Proibições explícitas"), `research.md` §2/§13 (testes de fronteira que impedem dependências de stealth/automação de serem sequer declaradas em `pyproject.toml`), e o Constitution Check acima (§5, §9).

## Questões/blockers restantes

**Nenhum blocker de produto identificado.** Todas as decisões necessárias para este PLAN — incluindo as cinco áreas que o CLARIFY já fechou (DEC-005 a DEC-009) — tinham base suficiente em `spec.md`, na Constitution, na Execution Policy e no código real de `001` para decisões técnicas (HOW) serem tomadas sem *informed guess* de produto. As poucas decisões secundárias tomadas aqui com justificativa própria (nome exato de módulos/pacotes, biblioteca CDP concreta, tipos de exceção, valores técnicos de backoff/polling, granularidade exata da flag `--retry-rejected`, caminho padrão de `--db-path`/`--raw-root`) são exatamente do tipo que a Execution Policy classifica como mecânicas/técnicas, não semânticas — documentadas com Decision/Rationale/Alternatives em `research.md`, revisáveis em TASKS sem retornar a um gate de produto.

Um único ponto é sinalizado — não como blocker, mas como **decisão técnica explicitamente aberta para TASKS** (não uma ambiguidade de produto): a granularidade exata da flag de retry manual (`--retry-rejected` global vs. um seletor por `spec`/`group` específico) — `spec.md` FR-020 exige apenas que a ação seja "explícita", sem especificar granularidade, e `contracts/orchestration-contract.md` §2 já registra isso como uma escolha de TASKS. Isso não bloqueia PLAN nem TASKS — é uma decisão de forma de flag, não de comportamento de retry (o comportamento — nunca automático — já está fechado por DEC-006).

Este PLAN não avança para `/speckit-tasks`. Aguarda gate explícito do Product Owner.
