# Quickstart / Guia de Validação: MVP de Ingestão Amayama — Amarok (AMA BR)

**Feature**: `001-amarok-ama-br-ingestion` | **Spec**: [spec.md](./spec.md) | **Data Model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/)

> Este guia descreve cenários de validação **executáveis quando a implementação existir** (produzida em uma fase TASKS/implementação futura, sob aprovação do PO). Nenhum código é criado por este documento — ele é a referência que a implementação deve satisfazer e que os testes devem exercitar. Não inclui corpo de implementação, migrations ou suíte de testes completa (isso pertence a `tasks.md`/implementação).

## Pré-requisitos (quando implementado)

- Python ≥ 3.11 instalado, ambiente virtual criado (`python -m venv .venv`), pacote instalado em modo editável (`pip install -e .[dev]`).
- Nenhuma credencial, rede ou navegador é necessário para os cenários abaixo — o núcleo é 100% testável offline (Constitution §12), a partir de fixtures de HTML já capturadas.
- Fixtures de HTML residem em `tests/fixtures/` (a criar em TASKS), organizadas por nível de captura (`MARKET_INDEX`/`SPEC_NAVIGATION`/`GROUP_DETAIL` — contracts/domain-contracts.md). Fixtures de regressão dos três pares de evidência (SC-005) e do caso `S7BC8A-61189` (ponto 24 do PLAN) refletem a granularidade real por `spec/category/group` (manifesto + páginas de detalhe individuais) — nunca uma única "mega-página" sintética fingindo conter a árvore inteira; fixtures unitárias sintéticas continuam permitidas para os demais cenários, sempre identificadas como sintéticas.

## Cenário 0 — Enumeração do market index (AMA BR → spec entries)

**Valida**: FR-001, contracts/domain-contracts.md "Nível A", data-model.md §14.

```
pytest tests/parser/test_market_index_discovery.py
```

**Esperado**: dada uma fixture de página de índice do mercado `AMA-BR` com múltiplas spec entries, `parse_market_spec_index()` produz uma `DiscoveredSpecEntry` por entrada, preservando `market`/`model_code`/`amayama_catalog_id`/`production_period_raw`/`source_url` quando presentes, e `grade`/`configuração` somente quando comprovados; duas entradas com o mesmo `model_code` e `amayama_catalog_id` diferentes produzem duas `DiscoveredSpecEntry` distintas (nunca uma só); um período open-ended e um campo opcional ausente não produzem erro; uma estrutura inesperada produz falha explícita (drift), nunca uma lista vazia silenciosa.

## Cenário 1 — Identidade nunca depende só de `model_code`

**Valida**: FR-003, SC-002, SC-006.

```
pytest tests/regression/test_identity_non_uniqueness.py
```

**Esperado**: duas `DiscoveredSpecEntry`/fixtures com `model_code == "S7BC8A"` e `amayama_catalog_id` diferentes (`62184` e `61189`, por exemplo) produzem duas `SpecIdentity`/`stable_key` distintas após conversão + normalização — nunca uma única entrada.

## Cenário 2 — Raw preservado antes de qualquer transformação

**Valida**: FR-008, FR-009.

```
pytest tests/unit/test_raw_capture_immutability.py
```

**Esperado**: ao processar uma `RawCaptureInput` de fixture, o `RawBlob` persistido (data-model.md §4a) é bit-a-bit idêntico ao `raw_content` de entrada, e uma `RawCapture` (Observation, §4b) é criada referenciando-o — independentemente do resultado de parsing/validação subsequente (inclusive quando a validação rejeita a captura).

## Cenário 3 — Rejeição de challenge/tradução/HTML inválido

**Valida**: FR-010, FR-011, SC-003.

```
pytest tests/parser/test_capture_validation_outcomes.py
```

**Esperado**: fixtures rotuladas `challenge_cloudflare.html`, `translation_contaminated.html` e `invalid_structure.html` produzem, respectivamente, `CHALLENGE`, `TRANSLATION_CONTAMINATED` e `INVALID` — nunca `ACCEPTED`, e nunca tratadas como página vazia válida.

## Cenário 4 — Determinismo de normalização/fingerprint

**Valida**: FR-015, FR-017, User Story 3.

```
pytest tests/unit/test_fingerprint_determinism.py
```

**Esperado**: computar `spec_parts_hash` duas vezes sobre a mesma `AssembledSpecTree` (manifesto + `ParsedGroupDetail` — contracts/domain-contracts.md "Montagem da árvore agregada") produz o mesmo valor; alterar a quantidade de uma peça produz um valor diferente; `image_hash` não muda quando apenas `parts` mudam, e vice-versa.

## Cenário 5 — Equivalência exata nos pares de evidência

**Valida**: FR-019, SC-005, User Story 4.

```
pytest tests/regression/test_evidence_pairs.py
```

**Esperado**: para os três pares (`2HBC3X`↔`S1BC3X`, `S6BC74`↔`S7BC74`, `S7BC8A-62184`↔`AGDC8A-62169`), `comparison_valid == True` e `parts_relation == EXACT`; ambas as `SpecIdentity` de cada par permanecem consultáveis separadamente após o cluster ser formado (`member_spec_refs` contém as duas).

## Cenário 6 — Representante determinístico e preservação de identidade

**Valida**: FR-021, FR-022.

```
pytest tests/unit/test_representative_selection.py
```

**Esperado**: dado um cluster com 3+ membros sintéticos variando em cobertura de imagem/recência/completude, o representante escolhido é reprodutível (mesma entrada → mesma saída) e segue estritamente a ordem de critérios de `research.md` §12; os não-representantes continuam presentes em `member_spec_refs`.

## Cenário 7 — Fallback de imagem controlado

**Valida**: FR-023 a FR-025, SC-007, SC-009.

```
pytest tests/unit/test_image_fallback.py
```

**Esperado**: uma spec sem imagem própria, dentro de um cluster com `parts_relation == EXACT` comprovado, recebe um `ResolvedImage` com `is_fallback=True` e `origin_spec_ref` apontando para a spec de onde a imagem veio; a mesma tentativa entre specs sem equivalência comprovada não produz fallback.

## Cenário 8 — Snapshots imutáveis e reprocessamento

**Valida**: FR-026, FR-029, SC-008.

```
pytest tests/unit/test_snapshot_lifecycle.py
```

**Esperado**: reprocessar a mesma fixture com uma nova `RawCapture` (nova coleta legítima, novo `capture_id`) produz dois `SpecSnapshot` distintos com `idempotency_key` diferentes (o primeiro transita para `SUPERSEDED`); nenhum campo do primeiro snapshot é alterado retroativamente.

## Cenário 9 — Checkpoint/resume hierárquico e idempotente

**Valida**: FR-012, SC-004, User Story 7, research.md §9, data-model.md §11.

```
pytest tests/integration/test_checkpoint_resume.py
```

**Esperado**:
- Cenário A (nível spec entry): simular uma `CollectionRun` interrompida após processar 2 de 5 spec entries de fixture (cada uma já com manifesto autoritativo capturado); retomar a run não duplica os 2 `SpecSnapshot` já `VALID`, e processa apenas as 3 restantes.
- Cenário B (nível group, dentro de uma única spec entry): dado um `SpecGroupManifest` autoritativo listando N grupos, simular a run interrompida após alguns `Group`s alcançarem `CheckpointEntry.status == ACCEPTED`; retomar a run não reprocessa esses `Group`s (nenhum novo `CheckpointEntry`/evidência duplicado para eles) e continua a partir dos `(category_slug, group_id)` do manifesto ainda `PENDING`/`IN_PROGRESS`/`REJECTED`; o `SpecSnapshot` final só é gerado como `VALID` após todos os grupos **do manifesto** estarem `ACCEPTED`.
- Cenário C (challenge não conclui group): simular um `Group` cuja captura de origem é classificada como `CHALLENGE`; verificar que o `CheckpointEntry` correspondente nunca atinge `status == ACCEPTED` (permanece `PENDING`/`REJECTED`), e que isso impede `collection_complete == True` para a spec entry até uma captura `ACCEPTED` suceder o challenge.
- Cenário D (sem manifesto autoritativo): simular `CheckpointEntry` `ACCEPTED` para alguns grupos capturados diretamente, **sem** um `SpecGroupManifest` autoritativo correspondente; verificar que `collection_complete` permanece `False` e `finalize_spec_entry()` não produz snapshot `VALID` — captura parcial de detalhe nunca define sozinha o universo esperado (data-model.md §15/§17).
- Cenário E (restart real do processo — data-model.md §13c, contracts/ports-contract.md "Replay / Reconstrução determinística"): persistir um `SpecGroupManifest` autoritativo; aceitar `Group A` e `Group B` (`CheckpointEntry.status == ACCEPTED`, cada um com seu `raw_capture_id`); **descartar toda representação em memória** (nenhuma referência a `ParsedGroupDetail`, à árvore agregada ou ao manifesto do passo anterior); instanciar novos repositórios/serviços (simulando um processo novo); chamar `finalize_spec_entry(spec_key, run_id)` a partir dessa nova instância. Esperado: `Group A` e `Group B` são reconstruídos exclusivamente a partir da persistência (`manifest_repo.get_authoritative()` + `checkpoint_repo.list_accepted()` + `capture_repo.get()` + `blob_store.read()` + `parse_group_detail()`); nenhum dos dois é recoletado; o `SpecSnapshot` resultante é `VALID`.

## Cenário 10 — Pipeline integrado (raw → parse → normalize → fingerprint → snapshot → equivalence)

**Valida**: integração ponta-a-ponta do núcleo, sem rede.

```
pytest tests/integration/test_pipeline_end_to_end.py
```

**Esperado**: partindo de uma captura `MARKET_INDEX` (descoberta), uma `SPEC_NAVIGATION` (manifesto) e as capturas `GROUP_DETAIL` correspondentes a todos os grupos do manifesto, o pipeline completo produz um `SpecSnapshot` `VALID`, fingerprints coerentes com `contracts/normalization-fingerprint-contracts.md`, e (quando aplicável, comparando com outra fixture do mesmo cluster) um resultado de equivalência coerente com `contracts/equivalence-contracts.md` — sem qualquer chamada de rede.

## Cenário 11 — Idempotência de checkpoint/snapshot e atomicidade da finalização

**Valida**: correção técnica final do PLAN — data-model.md §13, contracts/snapshot-contract.md, contracts/input-contracts.md.

```
pytest tests/unit/test_checkpoint_idempotency.py
pytest tests/integration/test_finalization_atomicity.py
```

**Esperado**:
- **Chave única de checkpoint**: chamar `upsert_checkpoint` duas vezes com a mesma `(run_id, spec_key, category_slug, group_id)` nunca produz duas linhas de `CheckpointEntry` — a segunda chamada é um upsert sobre a mesma linha (nunca um `INSERT` incondicional).
- **Observações distintas, mesmo blob**: duas fixtures com `raw_content` byte-idêntico, submetidas com `run_id`/`collected_at` diferentes, produzem um único `RawBlob` (mesmo `content_hash`) mas duas `RawCapture` distintas (`capture_id` diferentes, `run_id`/`collected_at` próprios preservados) — nenhuma das duas observações é descartada ou fundida com a outra.
- **Retry de finalização não duplica snapshot**: chamar `finalize_spec_entry` duas vezes seguidas para o mesmo `(run_id, spec_key)`, sem nenhum novo `CheckpointEntry` `ACCEPTED` entre as chamadas, produz o mesmo `idempotency_key` e **não** insere um segundo `SpecSnapshot` — a segunda chamada retorna o snapshot já existente.
- **Nova coleta legítima gera novo snapshot**: reexecutar a finalização após um `Group` ser reaceito via uma nova `RawCapture` (novo `capture_id`, mesmo que o conteúdo seja idêntico ao anterior) produz um `idempotency_key` diferente e um novo `SpecSnapshot`, sucedendo o anterior (`SUPERSEDED`).
- **Atomicidade**: simular uma falha entre os passos de `finalize_spec_entry` (ex.: interromper após inserir o snapshot mas antes de atualizar `current_spec_state`) e verificar que, graças à transação única, o estado observável após a falha é consistente — nunca um `current_spec_state` apontando para um snapshot inexistente, nem um snapshot "órfão" sem `current_spec_state` atualizado (a transação inteira não é confirmada, ou é confirmada por completo).

## Suíte completa

```
pytest --cov=amayama_scraper --cov-report=term-missing
mypy --strict src/
ruff check src/ tests/
ruff format --check src/ tests/
```

**Nota**: os comandos acima descrevem o fluxo de validação esperado quando o pacote existir; nenhum deles é executável hoje, pois nenhum código foi criado por esta fase PLAN.
