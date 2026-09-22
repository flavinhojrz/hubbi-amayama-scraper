# Feature Specification: Performance Worker Pool — Paralelismo Controlado por Spec

**Feature Branch**: `005-performance-worker-pool`

**Created**: 2026-09-03

**Status**: Especificação para aprovação do PO (gate SPECIFY, Constitution §14).
Nenhuma implementação iniciada nesta entrega — apenas `spec.md`/`plan.md`/
`tasks.md`, conforme pedido explícito do PO.

**Input**: pedido do PO (verbatim, resumido): a coleta do GOL tem 290 specs e
está lenta porque o scraper é sequencial e a taxa de challenge é alta, então
paralelização agressiva pode piorar o throughput. Adicionar paralelismo
controlado por spec + limitação global adaptativa, priorizando throughput
real e integridade, sem alterar parsing, fingerprints, qualidade de dados ou
comportamento human-in-the-loop dos challenges. 14 blocos de requisitos
numerados (CLI `--workers`; unidade de paralelismo = spec; claim/lease
atômico; banco SQLite/WAL; arquitetura de navegador/processos; challenges
inalterados; rate limiter adaptativo determinístico; métricas; polling;
resume; segurança de contexto da feature 004; testes; artefatos SDD; primeiro
objetivo de benchmark real). "Não faça coleta real. Não faça commit."

## Contexto e motivação

A feature 002 introduziu o transporte real via `ChromeCdpTransport` e o laço
de coleta sequencial (`run_collection_driver`); a feature 004 tornou esse
laço seguro para múltiplos modelos/mercados no mesmo banco via
`CollectionContext`. Nenhuma das duas altera o fato de que uma execução
processa exatamente uma spec por vez, uma navegação por vez — para 290 specs
(GOL) com pausas humanas frequentes por challenge, o tempo total de parede é
dominado por E/S serializada, não por CPU.

Esta feature (005) introduz paralelismo **entre specs** (nunca dentro de uma
spec — grupos de uma mesma spec continuam sequenciais) coordenado por um
mecanismo de claim/lease sobre o SQLite existente, com um limitador de
concorrência adaptativo que reage à taxa observada de challenges. Ela **não
reabre** parsing, fingerprints, equivalência, normalização, snapshots,
detecção de challenge/CAPTCHA nem o isolamento de contexto de 004 — todos
permanecem exatamente como estão; 005 adiciona apenas a camada de
orquestração de quantas/quais specs avançam ao mesmo tempo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - `--workers 1` é bit-a-bit o comportamento atual (Priority: P1)

Como operador, ao não passar `--workers` (ou passar `--workers 1`), quero que
a coleta se comporte exatamente como hoje — mesmo código de execução, mesma
ordem de processamento, nenhum overhead de lease/rate-limiter observável.

**Why this priority**: é a rede de segurança de toda a feature — sem ela, a
introdução de paralelismo é, por si só, um risco de regressão sobre um
pipeline já validado (Constitution §12, §14).

**Independent Test**: rodar a suíte de integração completa existente
(collection_driver, challenges, resume) sem nenhuma flag nova e confirmar que
passa inalterada; comparar o caminho de código executado com `--workers 1`
contra o `run_collection_driver()` de hoje (mesma função, sem wrapper).

**Acceptance Scenarios**:

1. **Given** um run novo sem `--workers`, **When** a coleta executa,
   **Then** o comportamento (ordem de navegação, eventos emitidos, checkpoints
   gravados) é idêntico ao pipeline pré-005.
2. **Given** `--workers 1` explícito, **When** a coleta executa, **Then** o
   resultado é idêntico ao caso (1) — `--workers 1` não é "pool de um
   worker", é o caminho de código legado.

---

### User Story 2 - Claim/lease atômico: nenhuma spec processada por dois workers (Priority: P1)

Como operador rodando `--workers N > 1`, preciso ter certeza absoluta de que
duas specs nunca são processadas simultaneamente por dois workers, e que um
worker morto/travado libera sua spec automaticamente após um tempo, sem
intervenção manual.

**Why this priority**: é a garantia de integridade fundamental do
paralelismo — sem ela, dois workers podem intercalar grupos da mesma spec e
corromper manifest/checkpoint/snapshot dela.

**Independent Test**: dois workers (fakes, em memória ou processos reais)
competindo pelo mesmo conjunto de specs nunca obtêm lease simultâneo para a
mesma `spec_key`; um lease cujo `expires_at` já passou é reclamável por outro
worker; um worker que renova (heartbeat) sua lease nunca a perde para outro
enquanto está genuinamente vivo.

**Acceptance Scenarios**:

1. **Given** duas tentativas concorrentes de claim para a mesma `spec_key`
   no mesmo `run_id`, **When** ambas competem, **Then** exatamente uma
   consegue o lease; a outra recebe "não disponível" e tenta outra spec.
2. **Given** um lease com `expires_at` no passado (worker que morreu sem
   renovar), **When** outro worker tenta claim da mesma spec, **Then** o
   claim é bem-sucedido (recovery), e o novo owner assume a partir do
   checkpoint já persistido (nenhum grupo `ACCEPTED` é reprocessado).
3. **Given** um worker vivo que renova sua lease periodicamente enquanto
   processa grupos, **When** outro worker tenta claim da mesma spec antes da
   expiração, **Then** o claim falha (spec permanece do owner original).

---

### User Story 3 - Rate limiter adaptativo reage a challenges (Priority: P1)

Como operador, quando challenges começam a ocorrer com frequência, quero que
a concorrência efetiva caia automaticamente (nunca acima do `--workers`
configurado); quando a coleta fica estável por um período sem novos
challenges, quero que a concorrência suba gradualmente de volta, sem nunca
ultrapassar o teto configurado.

**Why this priority**: é a garantia de throughput real do pedido do PO —
"não suponha que mais workers = mais rápido"; paralelismo sem esse
mecanismo pode aumentar a taxa de challenge e piorar o throughput líquido.

**Independent Test**: política determinística testada como função pura
(estado → evento → novo estado), sem SQLite/rede — dado um clock injetado,
uma sequência de eventos `CHALLENGE_OBSERVED`/tempo decorrido produz a mesma
sequência de `effective_concurrency` sempre.

**Acceptance Scenarios**:

1. **Given** `effective_concurrency == workers configurado` e nenhum
   challenge recente, **When** um challenge é observado dentro da janela
   configurada, **Then** `effective_concurrency` cai em 1 (nunca abaixo de 1).
2. **Given** `effective_concurrency < workers configurado` e nenhum
   challenge observado por `stability_seconds` consecutivos, **When** o
   período estável se completa, **Then** `effective_concurrency` sobe em 1
   (nunca acima do `--workers` configurado), e o relógio de estabilidade
   reinicia para a próxima subida.
3. **Given** `effective_concurrency == N` workers já com lease ativo,
   **When** um worker adicional tenta reivindicar uma nova spec, **Then**
   ele aguarda/recua em vez de reivindicar — trabalho já em andamento nunca é
   interrompido (a degradação nunca preempta specs já em progresso).

---

### User Story 4 - Métricas periódicas observáveis (Priority: P2)

Como operador acompanhando um run longo (290 specs), quero ver
periodicamente: specs concluídas, grupos `ACCEPTED`, grupos/min,
requests/navegações, challenges, challenges/hora, tempo total esperando
challenge, workers ativos e concorrência efetiva — para decidir se o
paralelismo está ajudando ou atrapalhando.

**Why this priority**: sem visibilidade, "throughput real" (critério de
sucesso do pedido do PO) não é observável durante a execução, só depois.

**Independent Test**: função pura de snapshot de métricas sobre um estado de
banco fabricado (contagens conhecidas) produz os 9 campos exigidos com os
valores esperados; dois snapshots sucessivos produzem `grupos/min` correto
pela diferença.

**Acceptance Scenarios**:

1. **Given** um run em andamento com `--workers > 1`, **When** o intervalo de
   métricas configurado decorre, **Then** uma linha de métricas com os 9
   campos é emitida pelo processo orquestrador (nunca duplicada por cada
   worker filho).

---

### User Story 5 - Resume reaproveita `ACCEPTED`/`VALID` existentes sob worker pool (Priority: P1)

Como operador, ao retomar (`--resume`) um run que foi parcialmente coletado
— com ou sem `--workers` na execução anterior — quero que grupos `ACCEPTED`
e specs já `VALID` nunca sejam reprocessados, exatamente como hoje.

**Why this priority**: é a garantia de não-regressão sobre o comportamento
de resume já validado (002/004) — paralelismo não pode custar checkpoints.

**Independent Test**: banco pré-populado com specs `ACCEPTED`/`VALID` de uma
execução anterior (sequencial ou com pool); um novo run com `--workers N`
reivindica apenas specs pendentes, e o driver por-spec usa
`get_pending_groups()` normalmente — zero navegação para grupos já
`ACCEPTED`.

**Acceptance Scenarios**:

1. **Given** um `CollectionRun` incompleto com 3 de 10 specs já `VALID` e uma
   4ª com 2 de 5 grupos `ACCEPTED`, **When** `--resume <run_id> --workers 2`
   executa, **Then** as 3 `VALID` são puladas, a 4ª retoma dos 3 grupos
   pendentes, e nenhuma navegação ocorre para as unidades já `ACCEPTED`.

---

### User Story 6 - Isolamento de contexto (004) preservado sob concorrência (Priority: P1)

Como operador, ao rodar `--workers N` num banco compartilhado entre modelos
(ex.: Amarok + GOL), quero a mesma garantia estrutural de 004: nenhum worker
pode processar/persistir sob um `CollectionContext` diferente do
`CollectionRun.scope` do run que está executando — mesmo com múltiplos
processos concorrentes.

**Why this priority**: 005 não pode reabrir a garantia de integridade
multi-modelo entregue em 004; concorrência é uma dimensão nova, não uma
substituição das validações existentes.

**Independent Test**: todos os testes de isolamento de 004 (cenários A–F)
permanecem verdes sob `--workers 1`; um teste novo comprova que cada worker
filho recebe/valida o mesmo `CollectionContext` do run pai antes de
reivindicar qualquer spec (reusa `_require_matching_context`/
`_require_matching_spec_context`, já existentes, sem enfraquecê-los).

**Acceptance Scenarios**:

1. **Given** um run de GOL com `--workers 2` rodando concorrentemente com um
   run de Amarok `--workers 1` no mesmo `amayama.db`, **When** ambos
   executam, **Then** nenhuma spec/checkpoint/manifest/snapshot de um
   aparece sob o `run_id`/contexto do outro (mesma prova estrutural de 004,
   agora também entre processos).

---

### Edge Cases

- `--workers` fora de `[1, 4]` (ex.: 0, 5, negativo) é rejeitado pela CLI
  antes de qualquer navegação/DB (mesmo padrão de validação fail-fast de
  `--manufacturer/--vehicle-model/--market` em 004).
- Menos specs pendentes do que `--workers` configurado: workers ociosos
  encerram normalmente ao não encontrarem mais nada para reivindicar — nunca
  ficam bloqueados esperando trabalho que não existe.
- Todas as specs já `VALID`/`ACCEPTED` (run já completo): `--workers N > 1`
  não navega nada, mesmo comportamento de "nada a fazer" que `--workers 1`
  já tem hoje.
- Um worker recebe `ChromeNotReachableError` ao iniciar (Chrome daquela
  porta não está aberto): esse worker específico falha ao iniciar e o
  orquestrador reporta o erro; os demais workers continuam normalmente
  (falha de um worker nunca derruba o pool inteiro) — a menos que nenhum
  worker consiga sequer iniciar, caso em que o run inteiro falha (mesmo
  exit code 3 de hoje, escopo do worker que falhou).
  **[DECISÃO DE DESIGN — não é requisito ambíguo do PO, ver plan.md
  "Riscos"]**: este comportamento (workers parciais falhando vs. run inteiro
  falhando) é uma escolha de arquitetura registrada para revisão do PO no
  gate de PLAN, não uma suposição sobre requisito de produto.
- Challenge ocorre em dois workers simultaneamente: cada worker pausa
  independentemente na sua própria janela do Chrome (human-in-the-loop por
  worker, nunca um mutex global bloqueando os demais) — ambos contam para o
  mesmo contador global de challenges do rate limiter.
- Dois workers terminam suas últimas specs no mesmo instante: a checagem de
  "run completo" (`_maybe_mark_run_completed`) só é executada pelo processo
  orquestrador **depois** que todos os workers filhos encerraram — nunca por
  um worker filho isoladamente, eliminando qualquer corrida sobre esse
  cálculo.

## Requirements *(mandatory)*

### Functional Requirements — CLI (US1)

- **FR-001**: A CLI MUST aceitar `--workers N`, `N` inteiro em `[1, 4]`;
  valor fora da faixa MUST ser rejeitado antes de qualquer navegação/escrita.
- **FR-002**: O default de `--workers` MUST ser `1`.
- **FR-003**: `--workers 1` MUST executar exatamente o caminho de código de
  `run_collection_driver()` já existente (nenhuma camada de
  lease/rate-limiter/multiprocessing envolvida).

### Functional Requirements — Unidade de paralelismo (US2)

- **FR-010**: A unidade de paralelismo MUST ser a spec (`stable_key`) —
  nunca categoria, grupo ou capítulo de manifesto.
- **FR-011**: Grupos de uma mesma spec MUST permanecer estritamente
  sequenciais (mesma ordem/lógica de `get_pending_groups()` já existente),
  mesmo sob `--workers > 1`.
- **FR-012**: Uma spec MUST pertencer a no máximo um worker por vez (ver
  claim/lease, FR-020 a FR-027).

### Functional Requirements — Claim/lease atômico (US2)

- **FR-020**: MUST existir uma operação de claim transacional (`BEGIN
  IMMEDIATE` ou equivalente atômico) que só concede uma spec a um worker se
  nenhum outro lease válido (não expirado) existir para essa `spec_key`
  nesse `run_id`.
- **FR-021**: Um lease MUST registrar `owner` (identificador do worker),
  `acquired_at`, `renewed_at` e `expires_at`.
- **FR-022**: Um worker MUST renovar (`renewed_at`/`expires_at`) sua lease
  periodicamente enquanto processa grupos daquela spec; a ausência de
  renovação por `expires_at` MUST tornar a spec reclamável por outro worker.
- **FR-023**: Um worker que morre/trava (processo encerrado sem liberar o
  lease) MUST ter sua spec recuperável por outro worker assim que
  `expires_at` for ultrapassado — sem intervenção manual, sem perda dos
  grupos já `ACCEPTED` (idempotência do checkpoint já existente).
- **FR-024**: Specs com `current_state == VALID`/`STALE` já aceitas
  (skip-if-valid, comportamento pré-existente) MUST continuar sendo
  ignoradas normalmente — nunca reivindicadas por nenhum worker.
- **FR-025**: A liberação normal de um lease (spec concluída ou sem grupos
  pendentes nesta passada) MUST ser explícita — um worker nunca deixa uma
  spec "presa" sob seu lease além do necessário, mesmo em caminho de sucesso.

### Functional Requirements — Banco/persistência (US2, US6)

- **FR-030**: SQLite/WAL MUST continuar sendo a única fonte de verdade —
  nenhum estado de coordenação (lease, rate limiter, métricas) MUST viver
  fora do banco (nenhuma coordenação apenas em memória entre processos
  distintos do SO).
- **FR-031**: Toda escrita de coordenação (claim, renovação, liberação,
  atualização de rate limiter, heartbeat) MUST ser uma transação curta —
  nunca abrangendo uma chamada de rede (`transport.navigate()`/
  `current_capture()`).
- **FR-032**: Porque uma `spec_key` só pode ter um lease válido por vez
  (FR-012, FR-020), nenhuma escrita de manifest/checkpoint/snapshot/
  current_state daquela spec MUST se originar de dois workers
  concorrentemente — nenhuma duplicação estrutural é possível.
- **FR-033**: O cálculo de conclusão de run (`_maybe_mark_run_completed`)
  MUST ser executado exatamente uma vez, pelo processo orquestrador, após
  todos os workers filhos encerrarem — nunca por um worker filho durante a
  execução concorrente (elimina corrida sobre esse cálculo, ver Edge Cases).

### Functional Requirements — Navegador/processos (US1, US2)

- **FR-040**: Cada worker MUST obter sua própria sessão de navegador via um
  `ChromeCdpTransport` independente, anexado (`debuggerAddress`) a um Chrome
  real distinto (host/porta próprios) — nenhum `ChromeCdpTransport`/driver
  Selenium MUST ser compartilhado entre threads ou processos.
- **FR-041**: Workers MUST ser processos do SO independentes (nunca
  threads Python compartilhando um mesmo `ChromeCdpTransport`) — motivo:
  `ChromeCdpTransport` encapsula um `webdriver.Chrome` cujo estado
  (`page_source`/`current_url`) é global à sessão anexada; duas navegações
  concorrentes sobre o mesmo driver corromperiam qual captura pertence a
  qual spec, sem qualquer sinal de erro (corrupção silenciosa — inaceitável
  pela Constitution §4/§6).
- **FR-042**: O operador MUST abrir N instâncias reais de Chrome (uma por
  worker), cada uma com `--remote-debugging-port` distinta, antes de rodar
  `--workers N` — documentado em `quickstart.md` desta feature.
- **FR-043**: `transport/chrome_cdp_adapter.py` permanece o único módulo de
  `src/` autorizado a importar `selenium` (invariante de 002, verificado por
  `tests/unit/test_no_browser_automation_dependency.py`) — 005 não introduz
  nenhum novo import de `selenium` fora dele.

### Functional Requirements — Challenges (US3)

- **FR-050**: Nenhuma forma de resolução/bypass automático de CAPTCHA/
  Cloudflare/challenge MUST ser introduzida — cada worker mantém o mesmo
  laço `await_challenge_resolution()` já existente, pausando na sua própria
  janela de Chrome (human-in-the-loop preservado por worker).
  Reforça FR-005 da Constitution.
- **FR-051**: Um challenge observado em qualquer worker MUST alimentar o
  rate limiter global (US3) — challenges nunca ficam invisíveis à
  coordenação só porque ocorreram num worker específico.

### Functional Requirements — Rate limiter adaptativo (US3)

- **FR-060**: MUST existir um estado global `effective_concurrency`,
  persistido no banco, por `run_id`, inicializado em `--workers` configurado.
- **FR-061**: `effective_concurrency` MUST nunca exceder `--workers`
  configurado, e nunca ser menor que 1.
- **FR-062**: Um worker MUST só reivindicar uma nova spec (claim) se o
  número de leases ativos (não expirados) daquele `run_id` for menor que
  `effective_concurrency` no momento do claim — trabalho já em progresso
  nunca é interrompido por uma queda de `effective_concurrency` (degradação
  é apenas prospectiva, nunca preemptiva — Edge Cases).
- **FR-063**: Ao observar um número de challenges dentro de uma janela de
  tempo configurável (`--challenge-window-seconds`) atingir um limiar
  configurável (`--challenge-threshold`), `effective_concurrency` MUST
  decrementar em exatamente 1 (nunca mais que isso por evento).
- **FR-064**: Após um período configurável sem nenhum challenge
  (`--stability-seconds`), com `effective_concurrency < --workers`,
  `effective_concurrency` MUST incrementar em exatamente 1, e o relógio de
  estabilidade MUST reiniciar (recuperação gradual, um passo por período
  estável — nunca um salto direto ao teto).
- **FR-065**: A política MUST ser uma função determinística e pura
  `(estado, evento, now) -> novo_estado`, testável inteiramente em memória,
  sem SQLite/rede/tempo real — nenhuma heurística probabilística/adaptativa
  além do descrito em FR-063/FR-064.

### Functional Requirements — Métricas (US4)

- **FR-070**: O processo orquestrador (nunca cada worker filho
  individualmente) MUST reportar periodicamente (`--metrics-interval-seconds`)
  uma linha de métricas contendo exatamente: specs concluídas, grupos
  `ACCEPTED`, grupos/min, requests/navegações, challenges, challenges/hora,
  tempo total esperando challenge, workers ativos, concorrência efetiva.
- **FR-071**: Cada métrica MUST ser derivável de estado persistido no banco
  (checkpoint_entry, current_spec_state, raw_capture, e as novas tabelas de
  lease/rate-limiter/challenge-event/heartbeat desta feature) — nunca de
  contadores em memória de um único processo (que não veriam os outros
  workers).

### Functional Requirements — Polling (US1, preservação)

- **FR-080**: `--challenge-poll-interval` MUST continuar aceitando valores
  como `1` (segundo) sem alterar a semântica de challenge — apenas reduz a
  latência de detecção de resolução manual, exatamente como hoje
  (`await_challenge_resolution`, inalterado nesta feature).

### Functional Requirements — Resume (US5)

- **FR-090**: `--resume <run_id>` MUST continuar funcionando com
  `--workers N > 1` — o `CollectionRun` retomado é o mesmo, e a descoberta
  de specs pendentes usa exatamente `list_by_scope()`/`get_current_state()`/
  `get_pending_groups()` já existentes.
- **FR-091**: Nenhuma spec com grupo `ACCEPTED` MUST ser reprocessada por
  causa do worker pool — o pool só muda *quantas specs avançam ao mesmo
  tempo*, nunca o que já está persistido como aceito.

### Functional Requirements — Segurança de contexto 004 (US6)

- **FR-100**: `CollectionContext`, a validação `context == CollectionRun.scope`
  (`_require_matching_context`), a validação `spec_key -> context`
  (`_require_matching_spec_context`), a validação de `capture_input.run_id`
  e o isolamento multi-modelo/multi-mercado (004, cenários A–F) MUST
  permanecer totalmente preservados e inalterados — cada worker filho os
  aplica exatamente como o processo único de hoje aplicaria.
- **FR-101**: Um worker filho MUST receber o mesmo `run_id`/`CollectionContext`
  do processo orquestrador — nunca reconstruído/inferido de forma
  independente por worker (evita divergência estrutural entre processos).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Suíte completa de testes existente (001/002/003/004) permanece
  100% verde com `--workers 1` (nenhuma regressão).
- **SC-002**: Teste de concorrência prova, de forma determinística
  (sem depender de timing real), que dois workers nunca obtêm lease
  simultâneo para a mesma `spec_key`.
- **SC-003**: Teste prova que um lease expirado é recuperável por outro
  worker sem perda de grupos `ACCEPTED` já persistidos.
- **SC-004**: Teste prova que a política do rate limiter (FR-060 a FR-065) é
  pura e determinística — mesma sequência de eventos produz sempre a mesma
  sequência de `effective_concurrency`.
- **SC-005**: Teste prova, com banco compartilhado Amarok+GOL (herdado de
  004), que o isolamento de contexto se mantém sob `--workers > 1`.
- **SC-006**: `ruff`/`mypy src` permanecem limpos nos arquivos alterados.
- **SC-007** *(fora do escopo desta entrega, ver item 14 do pedido do PO)*:
  primeiro benchmark real comparando 1 worker vs. 2 workers (poucas specs
  reais, groups/min e taxa de challenge) — depende de coleta real, portanto
  só ocorre depois de uma implementação aprovada e executada pelo PO; esta
  entrega apenas prepara o comando sugerido (plan.md).

## Key Entities

- **SpecLease**: `(run_id, spec_key, owner, acquired_at, renewed_at,
  expires_at)` — concede posse exclusiva e temporária de uma spec a um
  worker; recuperável após expiração.
- **RateLimiterState**: `(run_id, effective_concurrency, stable_since,
  updated_at)` — estado global adaptativo por run.
- **ChallengeEvent**: `(run_id, capture_kind, spec_key, observed_at,
  resolved_at)` — log de ocorrências de challenge, fonte tanto do rate
  limiter (US3) quanto das métricas de challenge (US4).
- **WorkerHeartbeat**: `(run_id, worker_id, pid, started_at,
  last_heartbeat_at)` — usado exclusivamente para a métrica "workers
  ativos" (US4); não participa de nenhuma decisão de claim/lease.

Detalhamento de schema/transições em `data-model.md`.

## Assumptions

Decisões de design tomadas nesta especificação, dentro do espaço já
delimitado pelo pedido explícito do PO (não são requisitos ambíguos — a
arquitetura interna é responsabilidade do gate de PLAN, sujeita à mesma
aprovação do PO antes de `CLAUDE IMPLEMENTA`):

- Valores default de `--lease-seconds`, `--challenge-window-seconds`,
  `--challenge-threshold`, `--stability-seconds`, `--metrics-interval-seconds`
  são escolhidos em `plan.md` como pontos de partida razoáveis e totalmente
  configuráveis via CLI — o PO explicitamente pediu "não invente heurística
  complexa. Deve ser determinística e testável", não valores numéricos
  específicos.
- Atribuição de porta CDP por worker (como o operador expõe N Chromes
  distintos) é detalhada em `plan.md`/`quickstart.md` — o pedido do PO exige
  "documentar como cada worker obtém sua sessão", não uma convenção de porta
  específica.
- Nenhuma coleta real e nenhum commit são executados como parte desta
  entrega (instrução explícita do PO) — inclui não rodar o benchmark real do
  item 14, que exige coleta real.
- `parsing/*`, `equivalence/*`, `fingerprints/*`, `snapshots/*`,
  `normalization/*`, `assets/*`, `validation/detectors/*` (incluindo
  detecção de challenge) e `analysis/*` (003) não têm nenhum requisito nesta
  especificação — permanecem intocados por design (mesmo padrão de
  "Assumptions" já usado em 004).
