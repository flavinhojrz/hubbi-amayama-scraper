# Contrato: Transporte por Navegador (BrowserTransport)

**Feature**: `002-amarok-ama-br-browser-scraper` — ver [../research.md](../research.md) §2–§5, §11 para as decisões e justificativas completas.

## Motivação

`process_capture()` e o resto do núcleo de `001` recebem `RawCaptureInput` já pronto — permanecem, por desenho (FR-034 de `001`), agnósticos de como o HTML foi adquirido. Este contrato define a fronteira pela qual esta feature adquire HTML real via Chrome, sem que nenhuma linha de `domain/`, `parsing/`, `validation/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`, `persistence/`, `checkpoint/`, `ingestion/` ou `orchestration/pipeline.py` precise saber que Selenium/CDP existem.

## 1. Port

```python
class BrowserTransport(Protocol):
    def navigate(self, url: str) -> BrowserCapture:
        """Navega até `url`, aguarda o carregamento da página, e retorna o
        estado capturado (page_source, effective_url, captured_at).

        Levanta uma subclasse de TransportError quando a navegação falha
        antes que qualquer conteúdo possa ser lido — nunca retorna uma
        BrowserCapture parcial/vazia como se fosse sucesso."""
        ...

    def current_capture(self) -> BrowserCapture:
        """Relê o estado ATUAL da página sem realizar nova navegação — usado
        exclusivamente pelo laço de pausa/retomada de challenge (§4), para
        verificar se a página mudou sem reemitir uma requisição de navegação
        (que poderia reiniciar um fluxo de resolução de CAPTCHA em curso)."""
        ...
```

```python
@dataclass(frozen=True, slots=True)
class BrowserCapture:
    page_source: str
    effective_url: str
    captured_at: datetime  # UTC
```

**Regras**:
- Nenhum método de "resolver challenge", "aguardar N segundos" ou "decidir se é challenge" existe neste port — essas responsabilidades nunca pertencem ao transporte (Constitution §5).
- `page_source` é sempre o HTML tal como o navegador o expõe no momento da leitura — o adapter não filtra, não reescreve, não injeta nada.
- O port não sabe o que é `CaptureKind`, `spec_key`, `category_slug` ou `group_id` — é o driver (`orchestration/collection_driver.py`) que sabe qual unidade está sendo capturada e faz a conversão para `RawCaptureInput`.

## 2. Adapter concreto: `ChromeCdpTransport`

Único ponto de todo o `src/` autorizado a importar `selenium` (research.md §5; verificado por teste de fronteira — research.md §13).

```python
class ChromeCdpTransport:
    def __init__(self, host: str, port: int) -> None:
        """Anexa (attach) a um Chrome já em execução via debuggerAddress
        (research.md §2). NUNCA lança/gerencia um processo de Chrome.

        Levanta ChromeNotReachableError imediatamente se o endpoint
        http://{host}:{port}/json/version não responder (fail-fast,
        research.md §4) — o construtor não tenta lançar um Chrome como
        fallback sob nenhuma circunstância."""

    def navigate(self, url: str) -> BrowserCapture: ...
    def current_capture(self) -> BrowserCapture: ...
```

**Configuração**: `host`/`port` resolvidos por CLI > env (`AMAYAMA_CDP_HOST`/`AMAYAMA_CDP_PORT`) > default `127.0.0.1:9222` (research.md §3) — nunca hardcoded fora deste ponto único de resolução.

**Retry interno de falha de transporte** (research.md §10): `navigate()`/`current_capture()` podem reter internamente (número máximo de tentativas + backoff, ambos configuráveis pelo construtor/CLI) antes de finalmente levantar a exceção — o chamador (driver) nunca vê tentativas intermediárias, apenas o resultado final (sucesso ou exceção).

**Proibições explícitas** (Constitution §5, DEC-007, Out of Scope de `spec.md`) — nenhum destes é implementado em `ChromeCdpTransport` nem em qualquer outro lugar desta feature:
- Nenhuma tentativa de resolver/preencher um CAPTCHA.
- Nenhuma manipulação de fingerprint de navegador, user-agent spoofing, ou qualquer técnica de stealth/anti-detecção.
- Nenhuma rotação de proxy.
- Nenhuma extração/injeção de cookies ou tokens com finalidade de bypass.
- Nenhum controle de tradução automática via manipulação de flags do Chrome além de garantir que a sessão operacional simplesmente não a acione (pré-condição operacional documentada em `quickstart.md`, não um hack de automação — research.md).

## 3. Fluxo do driver de coleta (`orchestration/collection_driver.py`)

Pseudo-código completo — reutiliza exclusivamente primitivas já existentes de `001` (`process_capture`, `try_finalize_spec_entry`, `get_pending_groups`) mais as novas leituras aditivas (`list_all_spec_identities`, `list_incomplete_runs` via `run_selection.py`) e a classificação de retry (`retry_classification.py`):

```
run_collection_driver(transport, conn, blob_store, capture_repo, run, filters):

  # Nível A — MARKET_INDEX
  capture = transport.navigate(MARKET_INDEX_URL)
  input = to_raw_capture_input(capture, capture_kind=MARKET_INDEX, run_id=run.run_id)
  result = process_capture(conn, blob_store, capture_repo, run.run_id, input)
  if result.validation_outcome == CHALLENGE:
      await_challenge_resolution(transport, conn, blob_store, capture_repo, run, input, capture_kind=MARKET_INDEX)
      # após resolução, reprocessa a MESMA unidade antes de prosseguir

  all_specs = list_all_spec_identities(conn)              # NOVO — data-model.md §7
  specs_to_process = apply_operational_filters(all_specs, filters)  # --spec / --limit-specs, nunca hardcode

  for spec in specs_to_process:
      current_state = get_current_state(conn, spec.stable_key())   # já existente (001)
      if current_state is not None and current_state.state in (VALID, STALE) and spec.stable_key() not in filters.force:
          report(SPEC_SKIPPED_ALREADY_VALID, spec)
          continue

      # Nível B — SPEC_NAVIGATION (se ainda não há manifesto autoritativo desta run)
      manifest = get_authoritative(conn, spec.stable_key(), run.run_id)   # já existente (001)
      if manifest is None:
          capture = transport.navigate(spec.source_url)
          input = to_raw_capture_input(capture, capture_kind=SPEC_NAVIGATION, run_id=run.run_id,
                                        expected_identity_context=spec)
          result = process_capture(conn, blob_store, capture_repo, run.run_id, input, spec_key=spec.stable_key())
          if result.validation_outcome == CHALLENGE:
              await_challenge_resolution(...)
          manifest = get_authoritative(conn, spec.stable_key(), run.run_id)
          if manifest is None:
              report(SPEC_NAVIGATION_REJECTED, spec, result)
              continue   # não força — próxima execução tenta de novo (get_pending_groups não se aplica ainda)

      # Nível C — GROUP_DETAIL
      pending = get_pending_groups(conn, run.run_id, spec.stable_key())   # já existente (001)
      pending = apply_group_limit(pending, filters.limit_groups)
      for (category_slug, group_id) in pending:
          entry = get_checkpoint_entry(conn, run.run_id, spec.stable_key(), category_slug, group_id)  # já existente
          classification = classify_pending_unit(entry)      # NOVO — retry_classification.py
          if classification == REQUIRES_EXPLICIT_RETRY and not filters.retry_rejected:
              report(GROUP_REJECTED_AWAITING_MANUAL_RETRY, spec, category_slug, group_id)
              continue

          group_url = manifest.source_url_for(category_slug, group_id)
          capture = transport.navigate(group_url)
          input = to_raw_capture_input(capture, capture_kind=GROUP_DETAIL, run_id=run.run_id,
                                        expected_identity_context=spec)
          result = process_capture(conn, blob_store, capture_repo, run.run_id, input,
                                    category_slug=category_slug, group_id=group_id, spec_key=spec.stable_key())
          if result.validation_outcome == CHALLENGE:
              await_challenge_resolution(...)
              continue   # a mesma unidade será reconsiderada na próxima leitura de get_pending_groups()

          if result.routed_to_parser and not result.critical_error:
              try_finalize_spec_entry(conn, blob_store, capture_repo, run.run_id, spec.stable_key())  # já existente
              report(GROUP_ACCEPTED, spec, category_slug, group_id)
          else:
              report(GROUP_REJECTED, spec, category_slug, group_id, result)

      report(SPEC_PASS_COMPLETE, spec)

  report(RUN_SUMMARY, run)
```

**Nunca**: nenhuma linha acima decide `ACCEPTED`/`CHALLENGE`/`INVALID`/`INCOMPLETE` por conta própria — todo outcome vem de `result.validation_outcome`, que vem de `process_capture()` → `classify_capture()`. Nenhuma unidade é reportada como `GROUP_ACCEPTED` sem que `process_capture()` já a tenha aceito.

## 4. Laço de pausa/retomada por challenge

```
await_challenge_resolution(transport, conn, blob_store, capture_repo, run, original_input, capture_kind, *, poll_interval=5.0, timeout=None):
  report(CHALLENGE_WAITING, original_input.source_url,
         message="CHALLENGE detectado. Resolva manualmente na janela do Chrome anexada, "
                 "então aguarde — a execução detecta automaticamente quando a página "
                 "voltar a ser válida.")
  started_at = now()
  while True:
      sleep(poll_interval)
      if timeout is not None and (now() - started_at) > timeout:
          report(CHALLENGE_TIMEOUT, original_input.source_url)
          return   # desiste desta unidade; permanece REJECTED/CHALLENGE, retomável depois

      try:
          capture = transport.current_capture()
      except ChromeNotReachableError:
          report(CHROME_LOST_DURING_CHALLENGE_WAIT)
          raise   # interrompe a execução — sessão de navegador perdida

      input = to_raw_capture_input(capture, capture_kind=capture_kind, run_id=run.run_id,
                                    expected_identity_context=original_input.expected_identity_context)
      result = process_capture(conn, blob_store, capture_repo, run.run_id, input, ...)  # mesmos kwargs de contexto
      if result.validation_outcome != CHALLENGE:
          report(CHALLENGE_RESOLVED, result.validation_outcome)
          return   # a chamada acima já persistiu o novo outcome — driver continua seu fluxo normal
      # continua no laço — ainda CHALLENGE
```

**Proteção contra página errada** (Issue #10 "verificação da URL/identidade esperada"): nenhuma lógica nova de comparação de URL decide `ACCEPTED`/`REJECTED` — se o operador navegou para uma página diferente da esperada, `detect_invalid_structure(html, capture_kind)` (já existente) recusa a estrutura como `INVALID`, e a unidade se torna `REQUIRES_EXPLICIT_RETRY` (DEC-006) em vez de reentrar automaticamente no laço de poll (evitando loop infinito sobre uma página errada). `BrowserCapture.effective_url` é comparado com a `source_url` esperada apenas como sinal de diagnóstico não-autoritativo em `report()` (FR-015).

## 5. `raw_content` vazio / navegação para página em branco

Se `page_source` estiver vazio (ex.: página ainda carregando, ou erro do navegador que não levantou exceção), `to_raw_capture_input()` levanta o mesmo `ValueError` já existente em `RawCaptureInput.__post_init__` (`raw_content must not be empty`) — o driver trata isso como falha de transporte (research.md §10), nunca como uma captura `INVALID` persistida (Constitution §4: nada é persistido/roteado até haver conteúdo genuíno).

**Rastreabilidade**: FR-001 a FR-005, FR-010 a FR-013, FR-014 a FR-016, FR-020, FR-027, DEC-006, DEC-007.
