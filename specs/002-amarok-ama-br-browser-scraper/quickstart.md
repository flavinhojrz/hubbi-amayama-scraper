# Quickstart / Guia de Validação: Scraper Real Amarok AMA-BR — Navegador Assistido

**Feature**: `002-amarok-ama-br-browser-scraper` | **Spec**: [spec.md](./spec.md) | **Data Model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/)

> Este guia descreve cenários de validação **executáveis quando a implementação existir** (TASKS futura, sob aprovação do PO). Nenhum código é criado por este documento. A maior parte dos cenários (0–9) é 100% offline (Constitution §12); os cenários de Fase A–E (validação real) exigem um Chrome real e a Amayama acessível, e são evidência de integração — nunca substituto da suíte automatizada (FR-036).

## Pré-requisitos (quando implementado)

- Python ≥ 3.11, ambiente virtual, `pip install -e .[dev]`.
- Para os cenários 0–9 (offline): nenhuma rede, nenhum Chrome — apenas o `BrowserTransport` fake em memória (`tests/unit/fakes.py`, estendido com `FakeBrowserTransport`).
- Para as Fases A–E (validação real): um Chrome real, iniciado pelo operador com depuração remota habilitada e **sem** tradução automática ativa, por exemplo:
  ```
  google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/amayama-chrome-profile
  ```
  (o `--user-data-dir` dedicado evita interferir no perfil pessoal do operador; a porta/host são apenas o *default* — sempre configuráveis via `--cdp-host`/`--cdp-port`/env, research.md §3).
- Confirmar manualmente, uma vez por sessão de Chrome, que a tradução automática está desativada para o domínio da Amayama (ícone de tradução do Chrome / configurações de idioma) — pré-condição operacional, não resolvida por código (research.md §11, FR-004).

## Cenário 0 — `BrowserTransport` fake conecta o transporte ao core

**Valida**: FR-001, FR-005, contracts/browser-transport-contract.md §1.

```
pytest tests/unit/test_browser_transport_to_process_capture.py
```

**Esperado**: uma `BrowserCapture` fake (page_source/effective_url/captured_at) é convertida em `RawCaptureInput` e roteada por `process_capture()` produzindo exatamente o mesmo resultado que uma `RawCaptureInput` construída manualmente com o mesmo conteúdo (paridade de comportamento — nenhuma lógica de validação/parsing é recriada no caminho do transporte).

## Cenário 1 — Seleção de run: zero/uma/múltiplas execuções incompletas

**Valida**: FR-019, FR-026, DEC-005, contracts/orchestration-contract.md §1.

```
pytest tests/unit/test_run_selection.py
```

**Esperado**: zero `CollectionRun` incompleta → `select_run()` cria uma nova; exatamente uma → resume automaticamente sem gravar nada; duas ou mais → `AmbiguousResumeError` contendo os candidatos, nenhuma escolhida; `--resume` para `run_id` de escopo incompatível ou já completo → `IncompatibleResumeRunError`; `--new-run` sempre cria, mesmo com incompleta compatível existente.

## Cenário 2 — Classificação de retry nunca mistura transporte com validação

**Valida**: FR-020, DEC-006, contracts/orchestration-contract.md §2.

```
pytest tests/unit/test_retry_classification.py
```

**Esperado**: `CheckpointEntry` ausente/`PENDING` → `NOT_YET_ATTEMPTED`; `IN_PROGRESS` (órfã) → `TRANSPORT_RETRY`; `REJECTED` com `evidence.outcome == "CHALLENGE"` → `CHALLENGE_PAUSED`; `REJECTED` com `evidence.outcome` em `INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED`, ou com `critical_error` em `evidence` → `REQUIRES_EXPLICIT_RETRY`.

## Cenário 3 — Rejeição de validação nunca é retentada automaticamente

**Valida**: FR-020, SC-011, DEC-006.

```
pytest tests/integration/test_no_auto_retry_on_validation_rejection.py
```

**Esperado**: um `FakeBrowserTransport` serve a mesma página `INVALID` em N passadas sucessivas do driver sobre o mesmo run; a unidade permanece `REJECTED` com `attempt_count == 1` (uma única tentativa real) através de todas as N passadas — zero novas capturas/tentativas de navegação são observadas no fake após a primeira, até que o driver seja explicitamente invocado com o filtro de retry manual.

## Cenário 4 — Pausa e retomada automática por challenge

**Valida**: FR-011, FR-012, SC-005, contracts/browser-transport-contract.md §4.

```
pytest tests/integration/test_challenge_pause_and_resume.py
```

**Esperado**: `FakeBrowserTransport` retorna uma página de challenge nas primeiras K leituras e uma página válida a partir da (K+1)-ésima; o driver entra no laço de poll, nunca marca a unidade `ACCEPTED` enquanto challenge persiste, e retoma automaticamente assim que a página válida aparece — sem reinício do processo de teste.

## Cenário 5 — Página errada após challenge não é aceita silenciosamente

**Valida**: proteção descrita em contracts/browser-transport-contract.md §4.

```
pytest tests/integration/test_challenge_wrong_page_after_resolution.py
```

**Esperado**: após o challenge, o fake retorna uma página que não corresponde à estrutura esperada do `capture_kind` em curso; o resultado é `INVALID` (via `detect_invalid_structure()` real), a unidade vira `REQUIRES_EXPLICIT_RETRY`, e o driver não reentra automaticamente no laço de poll para essa unidade.

## Cenário 6 — Resume não recoleta `ACCEPTED`; skip de spec já `VALID`

**Valida**: FR-018, SC-003, SC-004.

```
pytest tests/integration/test_resume_skips_accepted_and_valid.py
```

**Esperado**: um `Group` `ACCEPTED` numa passada anterior do driver (mesmo `run_id`) não é renavegado numa passada seguinte; uma spec com `CurrentSpecState`/`SpecSnapshot` já `VALID` é ignorada por completo (nenhuma captura `SPEC_NAVIGATION`/`GROUP_DETAIL` é emitida para ela) — a menos que `--force` inclua explicitamente essa spec.

## Cenário 7 — `--dry-run` produz zero mutação

**Valida**: FR-022, SC-014, DEC-009, contracts/orchestration-contract.md §3.

```
pytest tests/unit/test_dry_run_zero_mutation.py
```

**Esperado**: `plan_operation()` é chamado com um `ReadOnlyRepos` cujas leituras retornam um estado pré-populado não-trivial; o teste verifica, por inspeção de tipo/assinatura, que nenhuma função de escrita foi sequer passada como dependência — a mutação é estruturalmente impossível, não apenas observada como ausente.

## Cenário 8 — Descoberta real sem hardcode

**Valida**: FR-006, FR-009, SC-001, SC-008.

```
pytest tests/regression/test_market_index_discovery_no_hardcode.py
grep -rn "2HBC3X\|S1BC3X\|S6BC74\|S7BC74\|S7BC8A\|AGDC8A" src/amayama_scraper/  # deve retornar vazio
```

**Esperado**: `list_all_spec_identities()` após uma captura `MARKET_INDEX` fake reflete exatamente as entradas da fixture, sem qualquer lista fixa de códigos de catálogo em `src/`.

## Cenário 9 — Fronteira de arquitetura do transporte

**Valida**: research.md §5, §13.

```
pytest tests/unit/test_no_browser_automation_dependency.py
pytest tests/unit/test_architecture_boundaries.py
```

**Esperado**: `selenium` é importado exclusivamente por `transport/chrome_cdp_adapter.py`; nenhum módulo de domínio/parsing/validação/normalização/fingerprints/equivalência/assets/snapshots/persistência/checkpoint/ingestion/`orchestration/pipeline.py` importa `transport` nem `selenium`.

---

## Validação real (Fases A–E) — evidência de integração, não substitui a suíte acima

### Fase A — Attach + descoberta real

```
amayama-scraper run --dry-run
amayama-scraper run --limit-specs 0   # ou equivalente: só MARKET_INDEX, nenhuma spec processada
```

**Esperado**: attach bem-sucedido ao Chrome aberto na Fase de pré-requisitos; ao menos um spec entry real do Amarok `AMA BR` aparece em `list_all_spec_identities()`/no plano exibido.

### Fase B — Uma spec, manifesto real, poucos grupos

```
amayama-scraper run --spec <STABLE_KEY_DESCOBERTO> --limit-groups 3
```

**Esperado**: manifesto autoritativo real persistido; até 3 `GROUP_DETAIL` reais capturados e `ACCEPTED`.

### Fase C — Mesma spec, completa

```
amayama-scraper run --spec <STABLE_KEY_DESCOBERTO>
```

**Esperado**: todos os grupos do manifesto real `ACCEPTED`; `SpecSnapshot.state == VALID` (mesmos critérios de `001`, sem alteração).

### Fase D — Interrupção e resume

```
# Ctrl+C no meio da Fase C, depois:
amayama-scraper run --resume <RUN_ID>
```

**Esperado**: grupos já `ACCEPTED` antes da interrupção não são renavegados (observável nos logs `SPEC_STARTED`/`GROUP_SKIPPED_CHECKPOINT` — nenhum `GROUP_ACCEPTED` repetido para o mesmo grupo).

### Fase E — Challenge real (quando ocorrer naturalmente)

**Esperado, se e quando um challenge real ocorrer durante A–D**: a execução pausa com a instrução objetiva no terminal; após resolução manual na mesma janela do Chrome, a execução retoma automaticamente. Não é necessário provocar/fabricar um CAPTCHA deliberadamente — os cenários 4–5 (offline, com fakes) já provam esse comportamento; a Fase E é apenas confirmação quando a condição surgir organicamente.

---

## Não confundir dry-run com execução real reduzida

`amayama-scraper run --dry-run` (Fase A, primeiro exemplo) e `amayama-scraper run --limit-specs 1 --limit-groups 3` são **categoricamente diferentes** (DEC-009): o primeiro não navega nem escreve nada; o segundo navega e persiste normalmente, apenas com escopo reduzido. Nenhum exemplo acima usa `--dry-run` para uma execução que se espera que colete dados reais.
