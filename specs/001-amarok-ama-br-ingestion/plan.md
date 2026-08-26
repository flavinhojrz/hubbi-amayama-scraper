# Implementation Plan: MVP de Ingestão Amayama — Volkswagen Amarok (Mercado AMA BR)

**Branch**: `001-amarok-ama-br-ingestion` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-amarok-ama-br-ingestion/spec.md` (aprovada pelo PO, commit `eb7dd83`). GitHub Issue #5 — "PLAN — MVP de ingestão Amayama Amarok AMA-BR".

**Correção aplicada (2026-08-25)**: este documento foi revisado após decisão explícita do PO — DEC-002 (persistência interna do MVP, materializada em `spec.md`) e três ajustes técnicos determinados pelo PO: checkpoint hierárquico com progresso por `Group`, `pr_codes` fechado como fora do `part_fingerprint` v1, e `stable_key` de `SpecIdentity` endurecido para cobrir todo o escopo de identidade sem ambiguidade. Ver `research.md` §8–§10 para o detalhamento técnico de cada correção.

**Correção técnica final aplicada (2026-08-26)**: fechada a garantia de idempotência de checkpoint/resume, que dependia insuficientemente do content-addressing do raw. Adicionados: chave única `(run_id, spec_key, category_slug, group_id)` + upsert transacional em `CheckpointEntry`; distinção explícita entre `RawBlob` (conteúdo físico, deduplicável) e `RawCapture`/Observation (evento de coleta, identidade própria, nunca colapsada); `idempotency_key` determinístico em `SpecSnapshot`; transação única de finalização. Ver `research.md` §15 e `data-model.md` §4, §13.

**Governança aplicada**: `.specify/memory/constitution.md`, `docs/sdd/EXECUTION_POLICY.md`, `AGENTS.md`, `CLAUDE.md`. Esta PLAN aplica a precedência normativa do projeto sobre qualquer default genérico do Spec Kit (`docs/sdd/EXECUTION_POLICY.md` §"Hierarquia de autoridade") — em particular, nenhuma "informed guess" foi feita para decisões semânticas; decisões técnicas (HOW) foram tomadas e justificadas em [research.md](./research.md).

## Summary

Transformar a spec aprovada em um desenho técnico implementável para um pipeline de ingestão determinístico do catálogo Volkswagen Amarok no mercado `AMA BR` da Amayama. Abordagem: um núcleo Python puro, sem rede e testável offline, organizado em módulos de responsabilidade única que seguem estritamente o pipeline conceitual da Constitution (`transport/acquisition → raw capture → validation → parser → raw domain model → normalization → fingerprints → equivalence/clusters → image resolution → snapshots/revalidation → adapter/export boundary`). A aquisição de HTML é manual/browser-in-the-loop (DEC-001 em `spec.md`); o núcleo recebe HTML/raw já adquirido como entrada (`RawCaptureInput`), permanecendo agnóstico ao mecanismo de aquisição (FR-034). Persistência: SQLite para metadados/estado (armazenando referências/hashes ao raw, não os blobs) + filesystem content-addressed para HTML/imagens brutos — autorizado explicitamente por DEC-002 (PO, 2026-08-25; ver `spec.md` §Decisions e `research.md` §8). Checkpoint é hierárquico, com progresso mínimo rastreável por `Group` (research.md §9, data-model.md §11). Identidade normativa (`stable_key`) é um hash determinístico sobre a tupla de seis campos de identidade, com `display_key` legível separado (research.md §10). Nenhum código é criado nesta fase — apenas os artefatos documentais de planejamento.

## Technical Context

**Language/Version**: Python ≥ 3.11 (dev/CI em 3.12) — ver `research.md` §1.

**Primary Dependencies**: `beautifulsoup4` + `lxml` (parsing HTML — research.md §4); stdlib `sqlite3`, `hashlib`, `json`, `unicodedata`, `dataclasses`, `typing` (núcleo de domínio, sem dependência de framework de validação — research.md §3). Dev-only: `pytest` + `pytest-cov` (research.md §5), `ruff` (research.md §6), `mypy` (research.md §3/§6).

**Storage**: SQLite (metadados/estado: registry, runs, snapshots, fingerprint sets, cluster assignments, asset resolutions, checkpoints hierárquicos por group — armazena referências/hashes, não blobs de HTML/imagem) + filesystem content-addressed (HTML bruto e imagens, endereçado por `sha256(raw_content)`) — autorizado por DEC-002, detalhado em research.md §8. Banco externo/produtivo e integração de persistência com Hubbi permanecem fora de escopo.

**Testing**: `pytest` (unit, parser-fixture, regression/reference, integration), 100% offline — ver `quickstart.md` para os cenários e research.md §5/§12 (Constitution §12).

**Target Platform**: ambiente de desenvolvimento/CI Linux/macOS/WSL (sem servidor/infra de produção — explicitamente fora de escopo do `spec.md`).

**Project Type**: pacote Python interno (biblioteca/pipeline), sem CLI nem API expostos nesta feature (ambos fora de escopo do `spec.md`); ponto de entrada é programático (`orchestration/`), consumido por testes agora e por uma feature futura de transporte/CLI.

**Performance Goals**: nenhum definido por `spec.md` (nenhuma Success Criteria de performance foi aprovada) — não fabricado nesta PLAN; prioridade é determinismo/corretude sobre throughput, consistente com a decisão já tomada na fase SPECIFY de não inventar metas numéricas.

**Constraints**: núcleo de domínio (`validation/` em diante) sem chamadas de rede; saídas determinísticas (mesmo input + mesmas versões de parser/normalizer/fingerprint ⇒ mesmos hashes); snapshots aceitos imutáveis (Constitution §4).

**Scale/Scope**: um modelo (Amarok) × um mercado (`AMA-BR`); tamanho real do catálogo desconhecido e não assumido — descoberto em runtime, sem meta fixa (mesma decisão já registrada em `spec.md`, Success Criteria).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio (Constitution) | Status | Como este PLAN atende |
|---|---|---|
| §1 Missão | ✅ PASS | Escopo restrito a Amarok/AMA-BR; identidade/proveniência preservadas em todas as entidades (`data-model.md`). |
| §2 Fonte e escopo | ✅ PASS | Hierarquia completa modelada (`data-model.md` "Visão geral"); `model_code` isolado nunca é identificador (`SpecIdentity`). |
| §3 Preservação de identidade | ✅ PASS | `SpecIdentity` preserva todos os campos mínimos exigidos; `EquivalenceClass` nunca redefine identidade (FR-021). |
| §4 Raw imutável e auditável | ✅ PASS | `RawBlob` content-addressed (deduplicação física) + `RawCapture`/Observation com identidade própria (nunca colapsada por hash igual), ambos imutáveis, gravados antes de qualquer validação/transformação (`contracts/input-contracts.md`, `data-model.md` §4). |
| §5 Coleta e segurança | ✅ PASS | Aquisição manual/browser-in-the-loop (DEC-001); `validation/` rejeita CAPTCHA/Cloudflare/tradução/HTML inválido sem bypass; challenge roteado a human-in-the-loop. |
| §6 Separação de responsabilidades | ✅ PASS | Módulos dedicados e não fundidos — ver "Project Structure" abaixo; nenhuma classe concentra navegação+parsing+domínio+equivalência+persistência. |
| §7 Normalização conservadora | ✅ PASS | `normalizer_version = amayama-normalizer-v1`, determinística, sem tradução/fuzzy/stemming (`contracts/normalization-fingerprint-contracts.md`). |
| §8 Fingerprints e equivalência | ✅ PASS | SHA-256 com domain separator + versão; multiset em todos os níveis; dedup somente com `comparison_valid AND parts_relation == EXACT`. |
| §9 Classes de equivalência e representante | ✅ PASS | `cluster_key = scope+normalizer_version+fingerprint_version+spec_parts_hash`; critérios de representante medidos deterministicamente (research.md §12). |
| §10 Imagens e fallback | ✅ PASS | Domínio de imagem independente; fallback só dentro de cluster comprovado, com provenance (`contracts/image-contract.md`). |
| §11 Snapshots e revalidação | ✅ PASS | 5 estados, máquina de transição simples, revalidação incremental top-down, finalização atômica com `idempotency_key` único (`contracts/snapshot-contract.md`, `contracts/equivalence-contracts.md`, `data-model.md` §13). |
| §12 Qualidade e testes | ✅ PASS | Estratégia de testes cobre unit/parser-fixture/regression/integration, 100% offline (`quickstart.md`). |
| §13 Versionamento | ✅ PASS | `parser_version`/`normalizer_version`/`fingerprint_version` explícitos e independentes; incompatibilidade produz `UNKNOWN`, nunca comparação direta. |
| §14 SDD e gates | ✅ PASS | Este PLAN não avança para `/speckit-tasks`; aguarda gate explícito do PO. |

Nenhuma violação identificada. **Complexity Tracking não se aplica** (tabela vazia abaixo, conforme regra do template).

## Project Structure

### Documentation (this feature)

```text
specs/001-amarok-ama-br-ingestion/
├── plan.md                                   # este arquivo
├── research.md                               # Phase 0 — decisões técnicas
├── data-model.md                             # Phase 1 — entidades e invariantes
├── quickstart.md                             # Phase 1 — guia de validação
├── contracts/
│   ├── input-contracts.md                    # RawCaptureInput + CaptureValidationResult
│   ├── domain-contracts.md                   # seletores v1 + resultado de parsing
│   ├── normalization-fingerprint-contracts.md
│   ├── equivalence-contracts.md
│   ├── image-contract.md
│   ├── snapshot-contract.md
│   └── export-boundary-contract.md
└── tasks.md                                  # Phase 2 — NÃO criado por este PLAN
```

### Source Code (repository root) — estrutura ALVO, não criada nesta fase

```text
src/amayama_scraper/
├── ingestion/          # RawCaptureInput → RawBlob + RawCapture/Observation (contracts/input-contracts.md §1, data-model.md §4)
├── validation/         # CaptureValidationResult (contracts/input-contracts.md §2)
├── parsing/             # HTML aceito → ParsedSpecEntry (contracts/domain-contracts.md), parser v1 com seletores fixos
├── domain/               # SpecIdentity, Category, Group, Schema, Part, OemReference (data-model.md §1-3)
├── normalization/     # normalizer v1 (contracts/normalization-fingerprint-contracts.md)
├── fingerprints/        # part/group/category/spec_parts_hash, schema_semantic_hash, image_hash, structure_hash
├── equivalence/          # EquivalenceResult, cluster_key, revalidação incremental (contracts/equivalence-contracts.md)
├── assets/                 # resolução de imagem + fallback (contracts/image-contract.md)
├── snapshots/            # SpecSnapshot, máquina de estados, idempotency_key + finalização transacional (contracts/snapshot-contract.md, data-model.md §13)
├── persistence/          # repositórios SQLite (referências/hashes ao raw, upserts transacionais) + storage content-addressed (research.md §8/§15, DEC-002) — único módulo que conhece SQL
├── checkpoint/            # CollectionRun + CheckpointEntry hierárquico (Spec Entry → Category → Group) com chave única + upsert, unidade mínima = Group (data-model.md §11/§13, research.md §9/§15)
├── orchestration/       # coordena os módulos acima; ponto de entrada programático; NÃO conhece transporte
└── export/                  # ExportView / adapter boundary (contracts/export-boundary-contract.md) — desacoplado de Hubbi

tests/
├── unit/                    # normalizer, canonical serialization, hash determinism, multiset, equivalence, representative, image fallback, snapshot state rules
├── parser/                 # fixtures: HTML válido, campos opcionais ausentes, grupos vazios, group_id duplicado, drift estrutural, HTML inválido, tradução contaminada, challenge
├── regression/           # 2HBC3X↔S1BC3X, S6BC74↔S7BC74, S7BC8A-62184↔AGDC8A-62169, S7BC8A-61189 vs. outro catalog_id
├── integration/          # raw → parse → normalize → fingerprint → snapshot → equivalence; checkpoint/resume; idempotência de finalização e atomicidade (data-model.md §13)
└── fixtures/               # HTML bruto de referência (as fixtures acima referenciam esta pasta)
```

**Structure Decision**: projeto único (Option 1 do template, sem frontend/backend/mobile), pacote Python em `src/amayama_scraper/` com 12 submódulos de responsabilidade única (Constitution §6), nenhum deles combinando navegação, parsing, domínio, equivalência ou persistência. `persistence/` é o único módulo com conhecimento de SQL/schema de armazenamento; `orchestration/` é o único módulo que importa de todos os demais para coordená-los — nenhum módulo de domínio (`domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`) importa de `ingestion/`, `persistence/` ou `orchestration/`, preservando baixo acoplamento e testabilidade 100% offline. **Nenhum destes diretórios/arquivos foi criado nesta fase** — esta seção é a especificação da estrutura-alvo para TASKS/implementação.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

Nenhuma violação da Constitution foi identificada nesta PLAN — tabela intencionalmente vazia.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| _(nenhuma)_ | — | — |

## Notas de encerramento desta fase

- **DEC-002 materializada (não é mais interpretação)**: a contradição anterior entre o "Out of Scope" do `spec.md` e a necessidade de persistência interna do pipeline foi corrigida por decisão explícita do PO (2026-08-25), registrada em `spec.md` §Decisions. SQLite (metadados/estado, armazenando referências/hashes ao raw) + filesystem content-addressed (raw) são as escolhas técnicas autorizadas para este PLAN; banco externo/produtivo e integração de persistência com Hubbi continuam fora de escopo; a implementação concreta permanece bloqueada até PLAN → TASKS → aprovação explícita do PO.
- **Checkpoint hierárquico (correção do PO)**: a granularidade de checkpoint deixou de ser apenas por spec entry — `Group` é agora a unidade mínima de progresso retomável, com `Category` como agrupamento/índice e `Spec Entry` como unidade lógica do `SpecSnapshot` final (research.md §9, data-model.md §11, `contracts/snapshot-contract.md`).
- **`pr_codes` fechado fora do fingerprint v1 (correção do PO)**: `pr_codes` nunca participa do `part_fingerprint` em `amayama-fingerprint-v1` — decisão fechada, não mais adiada para TASKS. Continua preservado no domínio/raw/export. Qualquer mudança futura exige nova versão de fingerprint e revalidação (`contracts/normalization-fingerprint-contracts.md`).
- **`stable_key` endurecido (correção do PO)**: a identidade normativa é a tupla explícita de seis campos (`source, manufacturer, vehicle_model, market, model_code, amayama_catalog_id`); `stable_key` passou a ser um hash determinístico sobre essa tupla (não mais uma string delimitada usada como contrato final), com um `display_key` legível e escapado mantido separadamente para logs (research.md §10, data-model.md §1).
- **Gap de pesquisa não bloqueante (sem alteração)**: seletor CSS de "categoria" ainda não pesquisado (`contracts/domain-contracts.md`); não impede o desenho do contrato de parsing, fica registrado como item de pesquisa para TASKS/implementação.
- **Idempotência de checkpoint/snapshot fechada (correção final, 2026-08-26)**: o PLAN anterior afirmava incorretamente que o content-addressing do raw garantia idempotência de checkpoint/resume — isso deduplica apenas bytes físicos, não unidades lógicas de progresso nem finalizações. Corrigido com: chave única `(run_id, spec_key, category_slug, group_id)` + upsert transacional em `CheckpointEntry`; separação `RawBlob` (blob físico) vs. `RawCapture`/Observation (evento de coleta com identidade própria, nunca colapsada por `content_hash` igual); `idempotency_key` determinístico em `SpecSnapshot` (baseado em `raw_capture_id`, não em `content_hash`, preservando a distinção anterior); transação única de finalização (`BEGIN IMMEDIATE ... COMMIT`) cobrindo validação de completude, registro de snapshot, superseder o anterior e atualização de `current_spec_state`. SQLite de escritor único é suficiente para o MVP — nenhum locking adicional foi introduzido (research.md §15, data-model.md §4/§13).
- **Nenhuma nova ambiguidade bloqueante** foi encontrada ao aplicar estas correções — todas as instruções do PO (DEC-002, os três ajustes técnicos anteriores, e esta correção final de idempotência) eram decisões concretas e não deixaram lacuna semântica em aberto sobre requisito, escopo, identidade ou comportamento observável.

Esta PLAN não avança para `/speckit-tasks`. Aguarda gate explícito do Product Owner.
