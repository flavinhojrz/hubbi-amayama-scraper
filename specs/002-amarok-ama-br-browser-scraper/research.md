# Phase 0 Research: Scraper Real Amarok AMA-BR — Navegador Assistido, Human-in-the-Loop e Resume

**Feature**: `002-amarok-ama-br-browser-scraper` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md)

Cada decisão segue o formato Decision / Rationale / Alternatives considered. Todas são decisões de nível PLAN (técnicas, HOW) — nenhuma altera requisito, escopo, identidade, retry, challenge, resume, freshness, dry-run ou completion definidos em `spec.md` (DEC-001 a DEC-009). Antes de cada decisão estrutural, o código real de `001-amarok-ama-br-ingestion` foi inspecionado para provar que a estrutura existente não atende — não apenas assumido.

---

## 1. Inventário do que já existe e é reutilizado sem alteração

Inspeção direta do código mergeado (não apenas de `data-model.md`/`contracts/` de `001`, que documentam a intenção — o código é a fonte de verdade):

| Capacidade | Local real | Reutilizado como |
|---|---|---|
| Roteamento de captura por nível | `orchestration/pipeline.py::process_capture()` | chamado pelo novo driver, sem alteração de assinatura |
| Validação/precedência DEC-003 | `validation/classify.py::classify_capture()` | chamado indiretamente via `process_capture()`, nunca reimplementado |
| Detecção de challenge | `validation/detectors/challenge.py::detect_challenge()` | autoridade única — nenhum detector paralelo na camada de navegador |
| Sinalização human-in-the-loop | `validation/human_in_the_loop.py::route_if_challenge()` | reutilizado tal como está |
| Resume em nível de `Group` | `checkpoint/resume.py::get_pending_groups()` | consumido pelo novo driver a cada passada |
| Finalização de spec | `orchestration/pipeline.py::try_finalize_spec_entry()` / `snapshots/finalize.py` | chamado sem alteração; já é invocado automaticamente após `GROUP_DETAIL` aceito em `run_collection()` — o novo driver reproduz esse mesmo acoplamento (chama `try_finalize_spec_entry()` a cada `GROUP_DETAIL` aceito), não `run_collection()` em si (que assume uma lista estática, não serve ao caso dinâmico — ver §7) |
| Identidade | `domain/identity.py::SpecIdentity`, `stable_key()` | inalterado |
| `CollectionRun` | `checkpoint/collection_run.py` — `scope` é uma **constante fixa** (`FIXED_SCOPE = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"`, validada em `__post_init__`) | descoberta crítica para DEC-005 — ver §8 |
| `CheckpointEntry` / máquina de estados | `checkpoint/checkpoint_entry.py::transition()` | **já permite** `REJECTED → IN_PROGRESS` via `START_ATTEMPT` — descoberta crítica para DEC-006 (§9), nenhuma nova transição é necessária |
| Persistência SQLite + filesystem | `persistence/db.py`, `persistence/blob_store.py`, `persistence/repositories/*`, migrations `0001`–`0008` | reutilizada; nenhuma nova tabela — apenas 2 novas *queries* de leitura (§8, §12) |
| `AcquisitionMode` | `ingestion/capture_kind.py` | enum já documentado como ponto de extensão explícito para automação futura (docstring: "o enum existe para que uma automação futura só precise adicionar um novo valor, não alterar o contrato") — ver §6 |

Esta tabela é a prova textual exigida antes de propor qualquer estrutura nova: nenhuma das capacidades acima precisa ser recriada, movida ou ter sua assinatura alterada.

---

## 2. Mecanismo de attach ao Chrome real (DEC-007)

**Decision**: Selenium ≥ 4.15 configurado em modo *attach* via a opção `debuggerAddress` do Chrome DevTools Protocol (`chrome_options.add_experimental_option("debuggerAddress", "<host>:<port>")`), nunca `webdriver.Chrome()` no modo padrão de lançamento/gestão de processo.

**Rationale**: A pesquisa exploratória já realizada neste repositório (`amayama_browser_fixture_collector.py`, script temporário explicitamente marcado como "must not be added to the production scraper feature") já validou exatamente este padrão — "Attaches to an already-open Chrome via remote debugging" — usando `selenium.webdriver` + `Options` + `Service`. DEC-007 cita textualmente esse comportamento já validado como motivo aprovado. Implementar CDP JSON-RPC/WebSocket bruto à mão (sem Selenium) seria reinventar um protocolo de baixo nível (framing de mensagens, correlação de `id`, espera de `Page.loadEventFired`) que o Selenium já resolve de forma madura e amplamente testada pela comunidade — não há motivo técnico para pagar esse custo/risco em um MVP. `debuggerAddress` é o mecanismo documentado e suportado pela própria Selenium para **anexar** a uma instância já em execução — o processo não é filho do scraper, não é lançado por ele, e fecha-lo/reiniciá-lo é responsabilidade exclusiva do operador (Constitution/DEC-007: "nunca lançando/gerenciando sua própria instância de Chrome").

**Alternatives considered**:
- **CDP puro via `websockets`/`http.client` da stdlib** (sem Selenium): elimina a dependência nova, mas exige reimplementar manualmente a navegação (`Page.navigate`, `Page.getFrameTree`, esperar `Page.loadEventFired`/`Page.frameStoppedLoading`), extração de `outerHTML` (`Runtime.evaluate` ou `DOM.getOuterHTML`) e tratamento de reconexão — superfície de bugs desproporcional ao ganho (uma dependência a menos) para o escopo do MVP. Rejeitada por robustez.
- **Playwright em modo `connect_over_cdp`**: também suporta attach via CDP com API moderna, mas introduz uma dependência não usada em nenhum lugar do projeto até agora e sem precedente de validação já feita no repositório (ao contrário do Selenium, que já foi exercitado no script exploratório). Rejeitada por não ser a "abordagem mínima" dado que Selenium já tem precedente comprovado neste projeto especificamente.
- **`pychrome`/bibliotecas de CDP de terceiros dedicadas**: pacotes pequenos, menos mantidos, sem histórico de uso no projeto. Rejeitada pelo mesmo motivo de robustez/precedente.

O adapter concreto (`transport/chrome_cdp_adapter.py`) é o **único** módulo em todo `src/amayama_scraper/` autorizado a importar `selenium` — ver §5 (fronteira de arquitetura) e §13 (teste de fronteira).

---

## 3. Endereço CDP configurável

**Decision**: `host`/`port` do CDP são parâmetros explícitos do adapter, resolvidos nesta ordem de precedência: flag CLI (`--cdp-host`/`--cdp-port`) > variáveis de ambiente (`AMAYAMA_CDP_HOST`/`AMAYAMA_CDP_PORT`) > default `127.0.0.1:9222`.

**Rationale**: `9222` é a porta convencional de depuração remota do próprio Chrome (documentada publicamente pelo projeto Chromium, não uma invenção deste projeto) — usá-la como *fallback* não viola "não fixar número arbitrário", porque não é um parâmetro de negócio (como um intervalo de rate-limit) e sim uma convenção de plataforma amplamente conhecida; o requisito de DEC-007 ("não hardcodar host/porta específica da máquina do desenvolvedor") é satisfeito porque o valor é sempre sobrescrevível e nunca a única forma de configurá-lo.

**Alternatives considered**: exigir sempre a flag explícita, sem default — rejeitada por gerar fricção operacional desnecessária no caso comum (Chrome local na porta padrão), sem ganho de segurança (o valor continua 100% configurável).

---

## 4. Falha ao conectar / Chrome ausente

**Decision**: o adapter tenta o attach uma única vez ao ser construído (fail-fast); se o endpoint HTTP `http://<host>:<port>/json/version` (endpoint padrão do CDP para listar a versão/sessões disponíveis) não responder, o adapter levanta `ChromeNotReachableError` (nova exceção em `transport/errors.py`) imediatamente — o CLI captura essa exceção e encerra com uma mensagem objetiva de erro, sem tentar lançar um Chrome por conta própria e sem retry automático (esta falha não é "falha de transporte transitória" no sentido de DEC-006 — é uma pré-condição operacional ausente, não uma instabilidade de rede pontual).

**Rationale**: Consistente com FR-003/Out of Scope ("o MVP depende do operador já ter aberto o Chrome"); falhar imediatamente e de forma clara é mais seguro e mais simples que qualquer lógica de espera/retry para uma pré-condição que só o operador pode resolver (abrir o Chrome com `--remote-debugging-port`).

**Alternatives considered**: aguardar/repetir a tentativa de conexão por um tempo antes de desistir — rejeitada por adicionar complexidade sem benefício claro; se o Chrome não está de pé quando o comando é executado, o operador sabe disso imediatamente e pode simplesmente rodar o comando de novo depois de abrir o Chrome.

---

## 5. Fronteira de arquitetura do transporte

**Decision**: novo pacote `src/amayama_scraper/transport/` — único ponto de contato com Selenium/CDP em todo o `src/`. Contém:
- `port.py` — `BrowserTransport` (Protocol) + `BrowserCapture` (dataclass imutável: `page_source: str`, `effective_url: str`, `captured_at: datetime`).
- `errors.py` — `TransportError` (base), `ChromeNotReachableError`, `NavigationTimeoutError`, `NavigationFailedError` — nunca confundidos com `ValidationOutcome` (DEC-006 §9).
- `chrome_cdp_adapter.py` — `ChromeCdpTransport`, única classe que importa `selenium`.

Nenhum módulo de `domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`, `validation/`, `parsing/`, `persistence/`, `checkpoint/`, `ingestion/` ou `orchestration/pipeline.py` importa `transport/` nem `selenium` — a dependência é unidirecional: `transport/` → nada de `amayama_scraper` (é uma folha); os novos módulos de orquestração (`orchestration/collection_driver.py`) é que importam `transport.port.BrowserTransport` (o Protocol, nunca o adapter concreto — a composição do adapter real acontece apenas em `cli/main.py`, a raiz de composição, exatamente como `orchestration/pipeline.py` já não conhece `FilesystemRawBlobStore`/`SqliteRawCaptureRepository` diretamente, apenas os *ports* `RawBlobStore`/`RawCaptureRepository`).

**Rationale**: espelha exatamente o padrão de inversão de dependência já usado por `contracts/ports-contract.md` de `001` (`RawBlobStore`/`RawCaptureRepository`) — não é um padrão novo introduzido por esta feature, é o mesmo padrão já aprovado, aplicado a uma nova fronteira (transporte de navegador em vez de armazenamento).

**Prova de que a estrutura existente não atende**: `contracts/ports-contract.md`/`ingestion/ports.py` de `001` definem `RawBlobStore`/`RawCaptureRepository` — ambos sobre *armazenamento*, não sobre *aquisição* de HTML. Não existe, em nenhum lugar do código mergeado, um port para "obter HTML de uma URL real" — `RawCaptureInput` já assume que `raw_content: bytes` foi adquirido por *algum* mecanismo externo (FR-034 de `001`: "permanecendo independente de qual mecanismo de aquisição... forneceu esse HTML/raw"). Esta é exatamente a lacuna que `transport/` preenche — sem tocar em `ingestion/`.

**Alternatives considered**: colocar o adapter dentro de `orchestration/` diretamente (sem pacote próprio) — rejeitada porque misturaria a única classe que importa Selenium com módulos que hoje são livres dessa dependência (o teste `test_no_browser_automation_dependency_anywhere_in_src` — ver §13 — provaria isso imediatamente); um pacote de folha dedicado deixa a fronteira auditável por uma única regra de importação.

---

## 6. Extensão do `AcquisitionMode`

**Decision**: adicionar um único novo membro ao enum existente — `AcquisitionMode.AUTOMATED_BROWSER_CDP = "AUTOMATED_BROWSER_CDP"` em `ingestion/capture_kind.py`. Nenhuma outra alteração nesse arquivo, nenhuma migration (a coluna `raw_capture.acquisition_mode` já é `TEXT NOT NULL` sem `CHECK` restritivo — `migrations/0003_raw.sql`).

**Rationale**: a própria docstring do enum em `001` já antecipa exatamente esta extensão: "o enum existe para que uma automação futura só precise adicionar um novo valor, não alterar o contrato" (FR-034 de `001`). Isso não é uma decisão nova sendo inventada — é a realização de um ponto de extensão já projetado e documentado.

**Prova de que nenhuma outra mudança é necessária**: `accept_capture()`/`RawCaptureInput`/`process_capture()` tratam `acquisition_mode` como um valor opaco, passado adiante sem ramificação de comportamento sobre ele — inspecionado diretamente no código (`ingestion/accept.py`, `orchestration/pipeline.py`). Nenhuma lógica depende do valor específico `MANUAL_BROWSER`.

---

## 7. Driver de coleta dinâmico — por que `run_collection()` não atende

**Decision**: novo módulo `orchestration/collection_driver.py`, que **não** reutiliza `run_collection()` como está, mas reutiliza tudo que `run_collection()` também usa por baixo (`process_capture()`, `try_finalize_spec_entry()`).

**Prova de que a estrutura existente não atende**: `run_collection(conn, blob_store, capture_repo, run_id, captures: list[CollectionInput])` (inspecionado em `orchestration/pipeline.py`) recebe a lista **completa e já conhecida** de capturas a processar como parâmetro de entrada — ela não descobre nada, apenas itera. Um scraper real não pode construir essa lista antecipadamente: o conjunto de `SPEC_NAVIGATION` a visitar só é conhecido depois que `MARKET_INDEX` é processado (e persistido), e o conjunto de `GROUP_DETAIL` só é conhecido depois que cada `SPEC_NAVIGATION` produz seu manifesto autoritativo. `run_collection()` foi desenhada para o caso de teste/replay determinístico (lista fixa conhecida a priori), não para o caso de descoberta ao vivo. Reescrever `run_collection()` para aceitar um gerador preguiçoso mudaria o contrato de uma função já testada e usada por `001` sem necessidade — mais simples e mais seguro é um novo módulo que chama exatamente as mesmas duas primitivas (`process_capture()`, `try_finalize_spec_entry()`) em uma ordem dirigida por descoberta.

**Rationale do desenho do laço** (pseudo-código completo em `contracts/browser-transport-contract.md` §3):
1. Navegar/capturar `MARKET_INDEX` → `process_capture()` → (novo) `list_all_spec_identities(conn)` para ler de volta o que foi persistido (§12).
2. Para cada spec entry (filtrada por limites/filtros operacionais — FR-023 a FR-025) cujo `CurrentSpecState` não é `VALID`/`STALE` (ou está sob `--force` — DEC-008): navegar/capturar `SPEC_NAVIGATION` → `process_capture()` → `get_authoritative()` para ler o manifesto de volta.
3. Para cada `(category_slug, group_id)` em `get_pending_groups(conn, run_id, spec_key)`, classificado por `retry_classification.py` (§9): navegar/capturar `GROUP_DETAIL` → `process_capture(..., category_slug=..., group_id=..., spec_key=...)` → se aceito, `try_finalize_spec_entry()` (mesmo acoplamento que `run_collection()` já usa).
4. Em qualquer nível, se o outcome for `CHALLENGE`: entrar no laço de pausa (`contracts/browser-transport-contract.md` §4) antes de prosseguir para a próxima unidade.

**Alternatives considered**: modificar `run_collection()` para aceitar um `Iterator[CollectionInput]` preguiçoso em vez de `list[CollectionInput]` — tecnicamente possível, mas exigiria que a *geração* de cada próximo item dependesse de estado só disponível depois de processar o item anterior (o manifesto só existe depois do `SPEC_NAVIGATION` ser aceito) — ou seja, o "iterator" precisaria ser, na prática, o próprio driver de descoberta reescrito por dentro de `run_collection()`, o que efetivamente moveria toda a lógica nova para dentro de um arquivo de `001` já revisado/aprovado, aumentando o raio de mudança em código estável sem necessidade. Rejeitada — mais simples e mais seguro adicionar um módulo novo que **consome** as mesmas primitivas.

---

## 8. Seleção de `run_id` (DEC-005)

**Decision**: novo módulo puro `orchestration/run_selection.py::select_run()`, dependente apenas de callables injetadas (nenhum `sqlite3` direto) — algoritmo completo em `contracts/orchestration-contract.md` §1.

**Prova de que a estrutura existente não atende**: `checkpoint/collection_run.py`/`persistence/repositories/checkpoint_repo.py` (inspecionados) só expõem `get_collection_run(run_id)` (busca por chave exata) e `save_collection_run(run)` — não existe nenhuma consulta "listar runs incompletos de um escopo". Isso é uma lacuna de leitura, não uma lacuna de modelagem: `collection_run.scope`/`collection_run.completed_at` já existem na tabela (`migrations/0004_checkpoint.sql`) e já são exatamente os dois campos que DEC-005 exige para decidir compatibilidade — falta apenas a *query*.

**Nova função (única adição a `checkpoint_repo.py`)**:
```python
def list_incomplete_runs(conn: sqlite3.Connection, scope: str) -> list[CollectionRun]:
    """CollectionRun com scope == scope e completed_at IS NULL, mais antigo primeiro."""
```
Implementação trivial sobre a tabela existente (`SELECT * FROM collection_run WHERE scope = ? AND completed_at IS NULL ORDER BY started_at`) — nenhuma migration.

**Nota sobre `scope` fixo**: como `CollectionRun.scope` é uma constante (`FIXED_SCOPE`) validada em `__post_init__`, todo `CollectionRun` desta feature tem necessariamente o mesmo `scope`. Isso significa que, **nesta feature especificamente**, a cláusula `WHERE scope = ?` é sempre satisfeita por qualquer `CollectionRun` existente — o filtro por escopo é, na prática atual, redundante, mas é mantido explicitamente porque (a) é o mecanismo que DEC-005 exige documentar como determinístico, e (b) uma feature futura (outro modelo VW) introduzirá `CollectionRun` com `scope` diferente, e a query já está correta para esse cenário sem precisar ser revisitada — exatamente o motivo de `FIXED_SCOPE` existir como constante versionável em vez de uma string espalhada pelo código.

**Rationale da rejeição de `--resume` para run incompatível**: usar `get_collection_run(run_id)` (já existente) + comparar `run.scope`/`run.completed_at` no próprio `select_run()` — nenhuma nova leitura é necessária para esse caso, apenas validação sobre o resultado já retornado.

---

## 9. Classificação de retry (DEC-006)

**Decision**: novo módulo puro `orchestration/retry_classification.py::classify_pending_unit()` — função determinística sobre um `CheckpointEntry | None` já lido (nenhum I/O próprio). Algoritmo completo em `contracts/orchestration-contract.md` §2.

**Prova de que a estrutura existente não atende, e de que nenhuma mudança na máquina de estados é necessária**: inspeção de `checkpoint/checkpoint_entry.py::transition()` mostra que `REJECTED → IN_PROGRESS` via evento `START_ATTEMPT` **já é uma transição permitida** pela máquina de estados existente (`if current in (PENDING, REJECTED): return IN_PROGRESS`). Ou seja, "tentar de novo uma unidade `REJECTED`" já é uma operação que o núcleo de checkpoint suporta nativamente — o que falta não é uma nova transição, é a **decisão de quando o driver deve emitir esse evento automaticamente vs. só sob pedido explícito**. Essa decisão é inerentemente de orquestração (não de domínio de checkpoint), logo pertence a `orchestration/`, não a `checkpoint/`.

**Prova adicional — de onde vem o sinal de classificação**: `CheckpointEntry.evidence` (campo já existente, `evidence_json` na tabela) já carrega `{"outcome": <ValidationOutcome>}` para rejeições de validação (`orchestration/pipeline.py::_route_group_detail`) ou `{"critical_error": <mensagem>}` para falha estrutural de parsing pós-aceitação. Nenhum novo campo é necessário — `classify_pending_unit()` apenas lê essas chaves já existentes.

**Algoritmo (resumo — completo em `contracts/orchestration-contract.md`)**:
- `entry is None` ou `status == PENDING` → `NOT_YET_ATTEMPTED` (tentar agora).
- `status == IN_PROGRESS` (órfã — processo anterior morreu no meio, nunca chegou a `classify_capture()`) → `TRANSPORT_RETRY` (tentar agora, com a política configurável de retry de transporte — §10).
- `status == REJECTED` e `evidence.outcome == "CHALLENGE"` → `CHALLENGE_PAUSED` (tentar agora, dentro do laço de pausa — `contracts/browser-transport-contract.md` §4).
- `status == REJECTED` e (`evidence.outcome` em `{INVALID, INCOMPLETE, TRANSLATION_CONTAMINATED}` ou `"critical_error" in evidence`) → `REQUIRES_EXPLICIT_RETRY` (NUNCA tentado automaticamente; só entra na passada do driver quando o operador passa `--retry-rejected`, que apenas amplia o conjunto de classificações incluídas na passada atual — nenhuma nova operação de escrita/reset é necessária, o driver simplesmente emite `START_ATTEMPT` para essas unidades também, reaproveitando a transição já permitida acima).

**Alternatives considered**: introduzir um novo `CheckpointStatus` (ex.: `RETRYABLE`/`BLOCKED`) — rejeitada explicitamente pela spec (FR-021: "nenhum vocabulário de estado paralelo é criado") e desnecessária, já que a distinção é inteiramente derivável do `status`+`evidence` já existentes.

---

## 10. Retry de falha de transporte

**Decision**: a política de retry para falha de transporte/rede (nunca chegou a `classify_capture()`) vive inteiramente em `transport/chrome_cdp_adapter.py` — um retry local, síncrono, com número máximo de tentativas e backoff simples (exponencial com jitter mínimo), ambos configuráveis via CLI (`--transport-max-retries`, default técnico `3`; `--transport-backoff-seconds`, default técnico `2.0`, dobrando a cada tentativa). Esgotadas as tentativas, o adapter propaga a exceção de transporte (`transport/errors.py`) para o driver, que registra a unidade como não processada nesta passada (o `CheckpointEntry` correspondente permanece `IN_PROGRESS` — órfão — e será reclassificado como `TRANSPORT_RETRY` na próxima passada/execução, sem estado adicional).

**Rationale**: manter o retry de transporte **dentro do adapter** (não no driver/orquestração) preserva a separação FR-020: o driver nunca precisa saber que uma tentativa "internamente" foi repetida 3 vezes antes de finalmente ter sucesso ou falhar — ele só vê "sucesso" (uma `BrowserCapture`) ou "falha de transporte" (uma exceção), nunca vê `INVALID`/`REJECTED` nesse caminho (essas só existem depois de `classify_capture()`, que nunca é alcançado numa falha de transporte pura). Os defaults técnicos (3 tentativas, backoff 2s dobrando) são decisões mecânicas de engenharia — não afetam nenhum critério de aceite/produto — e são sempre configuráveis via CLI, nunca um valor fixo sem escape (consistente com FR-029/FR-020.1).

**Persistência de `attempt_count`**: o `CheckpointEntry.attempt_count` já existente é incrementado a cada `START_ATTEMPT` (já implementado em `upsert_checkpoint()`), então cada nova passada do driver sobre uma unidade órfã já produz auditoria de quantas vezes ela foi tentada, sem necessidade de um contador paralelo específico de "falha de transporte" — o contador combinado (transporte + validação) já é suficiente para observabilidade (FR-027 mostra "RETRY-de-transporte" como uma contagem de execução corrente, não uma leitura de `attempt_count` histórico).

**Abandono da unidade**: esta feature nunca abandona uma unidade automaticamente (nenhum "desistir depois de N execuções inteiras" é definido) — apenas o retry *dentro* de uma única tentativa de navegação tem limite. Entre execuções, uma unidade `IN_PROGRESS` órfã é sempre reconsiderada (comportamento idêntico a `PENDING`, já coberto por `get_pending_groups()`). Nenhuma política adicional de "desistência permanente" é inventada — se necessária no futuro, é uma nova decisão de produto, não uma suposição desta PLAN.

**Alternatives considered**: retry com fila/circuito assíncrono — rejeitada, desproporcional a um MVP sequencial de baixa concorrência (spec.md FR-028).

---

## 11. Ciclo de pausa/retomada por challenge (human-in-the-loop)

**Decision**: ao encontrar `CHALLENGE`, o driver entra em um laço de polling **bloqueante** sobre a mesma unidade (não avança para outras unidades enquanto espera) — consistente com uma única sessão/janela de Chrome sendo dirigida sequencialmente (FR-028, DEC de concorrência mínima). A cada `--challenge-poll-interval` segundos (default técnico `5.0`, configurável), o driver chama `transport.current_capture()` (novo método do port — relê a página atual sem nova navegação) e reprocessa o resultado pelo pipeline autoritativo completo (`process_capture()`, nunca um atalho). O laço só termina quando `process_capture()` deixa de retornar `CHALLENGE` para aquela unidade — nunca por um "parece resolvido" decidido pelo transporte. Não há timeout por padrão (espera humana é inerentemente não limitada); `--challenge-timeout` opcional permite ao operador impor um limite, após o qual o driver desiste **daquela unidade** (permanece `REJECTED`/evidência `CHALLENGE`, retomável depois) e segue para a próxima, sem abortar a execução inteira.

**Prova de que nenhum novo detector é necessário**: `classify_capture()`/`detect_challenge()` já são exatamente a autoridade que decide se a página deixou de ser challenge — chamá-los de novo a cada poll é reutilização direta, não duplicação.

**Proteção contra "usuário navegou para a página errada"**: nenhum código novo de verificação de URL é necessário como mecanismo *autoritativo* — se a página para a qual o operador navegou não corresponde à estrutura esperada pelo `capture_kind` daquela unidade, `detect_invalid_structure(html, capture_kind)` (já existente, `validation/detectors/structure.py`, contrato de estrutura por `capture_kind`) produz `INVALID`, não `ACCEPTED` — e por DEC-006 essa unidade se torna `REQUIRES_EXPLICIT_RETRY` (não é automaticamente re-tentada), evitando um laço infinito de poll sobre uma página errada. Esta é uma descoberta de reuso, não uma decisão nova: a proteção pedida pelo Issue #10 ("verificação da URL/identidade esperada") já existe no core, aplicada de novo a cada poll. Como sinal **adicional, não-autoritativo** (permitido por FR-015), o driver também compara `BrowserCapture.effective_url` com a `source_url` esperada da unidade e inclui essa comparação em `evidence`/no log de progresso — apenas para diagnóstico humano mais rápido, nunca para decidir `ACCEPTED`/`REJECTED` por conta própria.

**Comportamento se o Chrome for fechado durante a espera**: a próxima chamada a `transport.current_capture()` levanta `ChromeNotReachableError` (adapter, §4) — o driver trata isso como "sessão de navegador perdida", interrompe a execução corrente com uma mensagem objetiva (não como erro real de dados — a unidade permanece exatamente como estava, `REJECTED`/`CHALLENGE`, retomável quando o operador reabrir o Chrome e rodar de novo com `--resume`).

**Persistência durante a espera**: nenhuma escrita adicional é necessária enquanto o laço de poll está ativo — o `CheckpointEntry` já foi gravado como `REJECTED`/`CHALLENGE` na primeira tentativa (via `process_capture()`); o poll apenas re-tenta a mesma unidade, que só transiciona quando de fato aceita.

**Alternatives considered**: exigir uma tecla (Enter) do operador antes de cada nova verificação, em vez de polling automático por tempo — rejeitada porque FR-012 exige detecção automática ("sem exigir reinício manual do processo... retomar automaticamente"); um requisito de tecla ainda funcionaria tecnicamente, mas adicionaria uma dependência de I/O interativo (stdin) desnecessária a um processo que também pode ser observado remotamente/em background. Polling por tempo, configurável, atende ao requisito com menos superfície.

---

## 12. Enumeração — nova leitura necessária em `spec_registry_repo.py`

**Decision**: nova função `list_all_spec_identities(conn: sqlite3.Connection) -> list[SpecIdentity]` (`SELECT * FROM spec_registry`), usada pelo driver para saber quais spec entries já foram descobertas (por esta execução ou por qualquer execução anterior) e assim decidir quais `SPEC_NAVIGATION` navegar.

**Prova de que a estrutura existente não atende**: `spec_registry_repo.py` (inspecionado) só expõe `get_spec_identity(stable_key)` (requer já saber a chave), `find_by_model_code_and_catalog_id(...)` (idem) e `list_discovered_spec_entries(stable_key)` (idem) — nenhuma função lista **todas** as identidades sem já conhecer a chave de antemão. Como o próprio propósito do driver é descobrir essas chaves pela primeira vez a partir do `MARKET_INDEX`, uma leitura "listar tudo" é estritamente necessária e não pode ser substituída por nenhuma função existente.

**Alternativa descartada dentro da própria decisão**: fazer `process_capture()` retornar a lista de entradas descobertas diretamente (alterando `ProcessCaptureResult`) — rejeitada porque alteraria a assinatura pública de uma função já testada/revisada de `001` sem necessidade; ler de volta o que já foi persistido (via uma nova *query* aditiva) é estritamente mais simples e não toca nenhum contrato existente.

---

## 13. Fronteiras de teste — testes de arquitetura existentes que esta feature precisa estender (não substituir)

Inspeção de `tests/unit/test_no_browser_automation_dependency.py` e `tests/unit/test_architecture_boundaries.py` revela dois testes de fronteira já existentes cujo escopo esta feature altera **deliberadamente e de forma restrita**:

1. `test_no_browser_automation_dependency_anywhere_in_src` — hoje afirma que **nenhum** arquivo em `src/` importa `selenium`/`playwright`/`pyppeteer`/`requests_html`. Essa afirmação foi escrita sob a decisão de `001` de que automação de transporte estava fora de escopo (DEC-001 de `001`: "Selenium/CDP automatizado continua fora do escopo desta feature"). Esta feature **é** essa automação futura antecipada — o teste precisa evoluir de "em lugar nenhum" para "em lugar nenhum, exceto `transport/chrome_cdp_adapter.py`". Isso não enfraquece a invariante original (o *propósito* — nenhuma lógica de domínio/parsing/validação/persistência toca Selenium — continua 100% verdadeiro e passa a ser verificado com uma allowlist explícita de um único arquivo, mais preciso que antes, não menos).
2. `test_pyproject_declares_no_browser_automation_dependency` — precisa ser ajustado porque `pyproject.toml` passará a declarar `selenium` como dependência real (§14) — o teste muda de "nunca" para "apenas quando não estava em escopo", e um novo teste equivalente assume seu lugar: `pyproject.toml` declara `selenium`, mas nenhum `extras`/dependência de scraping adicional (`playwright`, `pyppeteer`, `undetected-chromedriver`, `selenium-stealth`, etc.) é declarada — reforçando a proibição de stealth/evasão (Constitution/DEC-007) de forma automaticamente verificável.

Ambos os ajustes são apresentados como parte do trabalho de TASKS (não implementados por este PLAN), mas documentados aqui porque provam que a arquitetura proposta é compatível com — e continua sendo verificada por — testes de fronteira já existentes, apenas com escopo corrigido para refletir que a automação antes "fora de escopo" agora existe, isolada.

`test_orchestration_no_duplicated_logic.py::test_orchestration_only_imports_from_domain_modules_or_stdlib` hoje analisa apenas `orchestration/pipeline.py` (path fixo no teste, não o pacote inteiro) — os novos arquivos de `orchestration/` (`collection_driver.py`, `run_selection.py`, `retry_classification.py`, `dry_run.py`, `progress_reporter.py`) não são automaticamente cobertos por ele. TASKS deve decidir se estende esse teste para os novos arquivos (parametrizando sobre todos os arquivos do pacote, com `amayama_scraper.transport.port` — nunca `.chrome_cdp_adapter` — adicionado à allowlist apenas para `collection_driver.py`) ou cria um teste irmão equivalente — de qualquer forma, `pipeline.py` em si permanece sem nenhuma importação de `transport/`, preservando o núcleo de `001` inteiramente agnóstico de navegador.

---

## 14. Dependências novas

**Decision**: adicionar `selenium>=4.15,<5` a `[project] dependencies` (não `dev`, não um extra opcional) em `pyproject.toml` — o pacote publicado precisa dele para o CLI funcionar de ponta a ponta; a suíte de testes automatizada, porém, continua majoritariamente livre dele: o driver/orquestração são testados exclusivamente contra o `BrowserTransport` Protocol com um double em memória (`tests/unit/fakes.py`, estendido — nenhum teste de `collection_driver.py`/`run_selection.py`/`retry_classification.py`/`dry_run.py` importa Selenium). Apenas um pequeno conjunto de testes do adapter (`tests/unit/test_chrome_cdp_adapter.py`) importa `selenium`, e faz isso substituindo (`monkeypatch`) o `webdriver.Chrome`/`Options` por stubs — nunca abrindo um Chrome real — mantendo a suíte 100% offline (FR-034/FR-035/FR-036).

**Nenhuma outra dependência nova é necessária**: o CLI usa `argparse` (stdlib); a leitura de configuração usa `os.environ` (stdlib); nenhuma biblioteca de logging externa é necessária (`orchestration/logging.py::log_event()` já existente é reutilizado — §15); `webdriver-manager` **não** é adicionado, pois o MVP nunca baixa/gerencia um binário de ChromeDriver por conta própria — o attach via `debuggerAddress` não instancia um novo processo de driver gerenciado da mesma forma que o modo padrão do Selenium exigiria (e, mesmo que exigisse, gerenciar downloads de binário está fora do espírito de "não iniciar evasão/gerenciamento automático" — a responsabilidade de ter um `chromedriver` compatível instalado, se necessário pela versão do Selenium usada, é documentada como pré-requisito operacional no `quickstart.md`, não resolvida por código).

---

## 15. Observabilidade — reuso de `orchestration/logging.py`

**Decision**: novo módulo fino `orchestration/progress_reporter.py`, que **não** reimplementa logging — apenas chama `log_event(run_id=..., event=..., **fields)` (já existente) para cada marco (`RUN_STARTED`, `SPEC_STARTED`, `GROUP_ACCEPTED`, `GROUP_SKIPPED_CHECKPOINT`, `CHALLENGE_WAITING`, `RETRY_TRANSPORT`, `GROUP_REJECTED`, `SPEC_COMPLETE`, `RUN_SUMMARY`), e mantém um contador simples em memória para o resumo final (`dict[str, int]`).

**Rationale**: `log_event()` já garante JSON lines correlacionadas por `run_id` e já proíbe ativamente vazar `raw_content`/HTML completo (`RawContentInLogError`) — exatamente a garantia de auditoria/segurança que a observabilidade desta feature precisa, sem reinventar formatação ou proteção contra vazamento de dados brutos no log.

**Alternatives considered**: `logging` da stdlib com handlers customizados, ou uma biblioteca de UI de terminal (`rich`/`tqdm`) para barra de progresso — rejeitadas: `rich`/`tqdm` seriam uma dependência nova só para estética, sem necessidade funcional (spec.md: "sem framework de logging excessivo se o existente atender" — e atende); o `stdlib logging` reintroduziria formatação/configuração que `log_event()` já resolve de forma mais simples e já testada (`test_logging_no_raw_dump.py`).

---

## 16. Concorrência entre dois processos do scraper

**Decision**: nenhum mecanismo novo de locking distribuído. Duas proteções já existentes/quase-existentes são suficientes para o MVP:
1. **Seleção de run (DEC-005)** já impede que uma segunda execução escolha silenciosamente o mesmo `run_id` incompleto sem `--resume` explícito (§8) — reduz drasticamente o caso comum de "dois processos pisando no mesmo trabalho por acidente".
2. **SQLite WAL + transação `BEGIN IMMEDIATE`** (`persistence/db.py`, já existente) — um segundo processo tentando escrever durante a transação de outro recebe `sqlite3.OperationalError: database is locked` em vez de corromper dados. Hoje, porém, `connect()` não define `PRAGMA busy_timeout`, então essa espera é `0` (falha imediata em vez de esperar um pouco) — uma pequena adição justificada: `conn.execute("PRAGMA busy_timeout = 5000")` em `persistence/db.py::connect()`. É uma mudança aditiva de comportamento (só afeta o que acontece sob contenção concorrente, que hoje falharia imediatamente da mesma forma) — não altera nenhum comportamento observável de execução single-process, não requer migration, e é a recomendação padrão de operação de SQLite em WAL com múltiplos processos.

Duas execuções **intencionalmente** apontadas para o mesmo `run_id` ao mesmo tempo (o operador ignorando a orientação operacional) continuam sendo um cenário não coberto por locking de aplicação — documentado no `quickstart.md` como recomendação operacional ("não rode dois processos simultâneos contra o mesmo `run_id`"), não resolvido por um sistema distribuído (explicitamente fora de escopo).

**Rationale**: satisfaz "reutilize mecanismo existente de persistência/locking, se houver" (o SQLite WAL já é esse mecanismo) e "não invente sistema distribuído" — a única adição (`busy_timeout`) é uma configuração padrão de SQLite, não uma nova peça de infraestrutura.

---

## 17. CLI — desenho mínimo

Ver `contracts/orchestration-contract.md` §3 para o contrato completo de opções e `quickstart.md` para exemplos executáveis. Resumo da decisão: `argparse` da stdlib, um único subcomando `run` (mais `--dry-run` como flag do mesmo comando, não um subcomando à parte, porque compartilha toda a resolução de escopo/filtros — DEC-009 exige que o dry-run reporte a mesma decisão de run que a execução real tomaria). Nenhuma biblioteca de CLI externa (`click`/`typer`) — `argparse` é suficiente para a superfície de opções definida (≈13 flags, nenhuma delas com sub-parsing complexo).

---

Fim de `research.md`. Nenhuma decisão acima altera requisito/escopo/comportamento observável fixado em `spec.md` — todas são HOW, justificadas por inspeção direta do código real.
