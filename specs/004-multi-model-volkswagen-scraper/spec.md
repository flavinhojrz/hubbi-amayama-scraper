# Feature Specification: Multi-Model Volkswagen Scraper — Isolamento Operacional

**Feature Branch**: `004-multi-model-volkswagen-scraper`

**Created**: 2026-09-02

**Status**: Implementação concluída (Claude), incluindo a correção dos
achados finais do Codex sobre a primeira entrega (Blockers 1–3, HIGH 4,
MEDIUM 5, LOW 6). Aguardando o gate seguinte do fluxo normativo
(`CLAUDE IMPLEMENTA → CODEX REVISA → correção se houver REQUEST_CHANGES →
CHATGPT CONSOLIDA EVIDÊNCIAS → PO VALIDA ENTREGA → MERGE`, Constitution
§14) — nenhuma aprovação formal de gate além da autorização direta do PO,
nesta conversa, para implementar foi registrada até este ponto; não há
histórico de revisão técnica/validação de PO anterior a documentar aqui.

**Input**: User description (PO, verbatim, resumido): "Corrija os achados do Codex na
generalização multi-modelo do scraper. Não faça coleta real. Não faça commit." — seguido
de 10 blocos de requisitos numerados (fonte única de contexto operacional; scope canônico
e validado; normalização única; URL segura; validação do market retornado; isolamento
completo entre modelos com 6 cenários A–F; run completion; compatibilidade; FIXED_SCOPE
como legado; testes e validação).

## Contexto e motivação

A feature 002 introduziu `--manufacturer/--vehicle-model/--market` e removeu os
hardcodes operacionais de Amarok/AMA-BR do fluxo de coleta (`FIXED_SCOPE`,
`MARKET_INDEX_URL`), permitindo reutilizar o mesmo pipeline para outros modelos
Volkswagen. Uma revisão técnica (Codex) identificou uma lacuna arquitetural: o
contexto operacional (manufacturer/vehicle_model/market) chegava a
`run_collection_driver()`/`process_capture()` como parâmetros soltos,
independentes do `run_id`/`CollectionRun.scope` já persistido — nada impedia
que um call site esquecesse de passar o contexto (caindo em um default que
mascara a ausência) ou passasse um contexto divergente do run real, causando
mistura de specs/checkpoints/manifests/snapshots entre modelos no mesmo banco.

Esta feature (004) corrige essa lacuna. Ela **não reabre nem reinterpreta a
feature 002** (que permanece o pipeline Amarok/AMA-BR validado, com scope
`AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR` preservado byte-a-byte); 004 é uma correção
de robustez arquitetural sobre a generalização multi-modelo que 002 introduziu.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Impossibilidade estrutural de mistura de contexto (Priority: P1)

Como operador do scraper, quando inicio uma coleta para um modelo/mercado
específico (ex.: `VOLKSWAGEN/GOL/AMA-BR`), preciso ter certeza absoluta de
que nenhum código interno pode, por engano ou omissão de parâmetro, gravar
conteúdo desse run como se fosse de outro modelo (ex.: `VOLKSWAGEN/AMAROK/AMA-BR`)
— mesmo que um chamador interno (código novo, teste, refactor futuro) erre a
passagem de parâmetros.

**Why this priority**: é a garantia de integridade de dados fundamental desta
feature — sem ela, o banco multi-modelo não é operacionalmente seguro.

**Independent Test**: chamar as funções internas de execução (`process_capture`,
`run_collection_driver`) com um `run_id` de um modelo e um contexto de outro
modelo deve falhar (exceção), antes de qualquer navegação ou persistência.

**Acceptance Scenarios**:

1. **Given** um `CollectionRun` existente com scope `VOLKSWAGEN/AMAROK/AMA-BR`,
   **When** `run_collection_driver()` é chamado com esse `run_id` mas um
   `CollectionContext` de `VOLKSWAGEN/GOL/AMA-BR`, **Then** a chamada levanta
   erro antes de navegar ou persistir qualquer coisa (Cenário E).
2. **Given** o mesmo `CollectionRun`, **When** `process_capture()` é chamado
   diretamente com um contexto divergente do `CollectionRun.scope`, **Then**
   a chamada levanta erro antes de `accept_capture()`/qualquer persistência.

---

### User Story 2 - Scope canônico, determinístico e sem colisão (Priority: P1)

Como mantenedor, preciso que o `scope` de um `CollectionRun` seja construído
de forma determinística e sem ambiguidade — dois contextos operacionais
diferentes nunca podem produzir o mesmo `scope`, e um `scope` persistido deve
poder ser decomposto de volta no contexto original (round-trip).

**Why this priority**: é a base para toda a validação de US1 — sem um scope
sem colisão, a checagem "context == run.scope" não é confiável.

**Independent Test**: testes de propriedade round-trip
(`context -> build_scope -> parse_scope -> context`) e de rejeição de
componentes vazios/com delimitador/com caracteres inseguros.

**Acceptance Scenarios**:

1. **Given** `manufacturer=VOLKSWAGEN, vehicle_model=AMAROK, market=AMA-BR`,
   **When** o scope é construído, **Then** o resultado é exatamente
   `AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR` (scope histórico da Amarok preservado).
2. **Given** qualquer `CollectionContext` válido, **When** `parse_scope(build_scope(ctx))`
   é executado, **Then** o resultado é igual a `ctx` (round-trip).
3. **Given** um componente vazio, contendo `:` (delimitador do scope), ou
   caractere fora do alfabeto canônico, **When** um `CollectionContext` é
   construído, **Then** a construção é rejeitada.

---

### User Story 3 - Isolamento completo entre modelos no mesmo banco (Priority: P1)

Como operador, preciso rodar coletas de vários modelos Volkswagen no mesmo
banco (`amayama.db`) sem que uma interfira nos dados, checkpoints, manifests,
snapshots, estado VALID ou conclusão de run de outra.

**Why this priority**: é o objetivo de produto direto desta feature.

**Independent Test**: os 6 cenários A–F descritos nos Functional Requirements,
com banco compartilhado e Amarok previamente populada.

**Acceptance Scenarios**: ver FR-030 a FR-036 (cenários A–F).

---

### User Story 4 - Validação do conteúdo retornado contra o contexto esperado (Priority: P2)

Como operador, se a página de índice de mercado retornar conteúdo de um
`market` diferente do que pedi (ex.: pedi AMA-BR e a página é de outro
mercado), o sistema não pode persistir esse conteúdo como se fosse do meu
run — deve rejeitar e sinalizar, nunca misturar silenciosamente.

**Why this priority**: fecha o único ponto onde conteúdo *externo* (a
resposta HTTP/HTML real) pode divergir do contexto pretendido — diferente de
US1, que trata de erro *interno* de programação.

**Independent Test**: Cenário F (índice cujo `market` extraído da página
diverge do `context.market` do run) — nenhuma `SpecIdentity`/`DiscoveredSpecEntry`
é persistida, `critical_error=True`, run abortado antes de prosseguir.

**Acceptance Scenarios**:

1. **Given** um run com `context.market=AMA-BR`, **When** o MARKET_INDEX
   capturado tem breadcrumb indicando outro mercado, **Then** nenhuma spec é
   registrada e o run é abortado com evidência explícita.

---

### Edge Cases

- Scope de outra feature/tabela não relacionada (`EquivalenceClass.scope`, um
  campo homônimo mas semanticamente distinto) não é afetado por esta feature.
- Um `CollectionRun` já persistido no banco real da Amarok (antes desta
  feature) continua parseável pelo novo `parse_scope()` sem qualquer migração
  (seu scope já era `AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR`, já compatível com o
  alfabeto canônico).
- MARKET_INDEX com zero entradas (página estruturalmente válida, mas sem
  linhas) não aciona a validação de mercado divergente (nada a comparar) —
  comportamento inalterado.
- `manufacturer`/`vehicle_model` nunca são extraídos da página (são sempre
  atribuídos a partir do `context`), portanto não podem divergir de forma
  observável no MARKET_INDEX — apenas `market` é parseado e, portanto,
  validável nesse ponto.

## Requirements *(mandatory)*

### Functional Requirements — Contexto operacional único (US1)

- **FR-001**: O sistema MUST representar o contexto operacional de uma coleta
  (manufacturer/vehicle_model/market/source) por uma única estrutura tipada
  (`CollectionContext`), não por parâmetros soltos independentes.
- **FR-002**: `process_capture()` e `run_collection_driver()` MUST exigir
  `CollectionContext` como parâmetro obrigatório, sem default — funções
  internas de execução nunca mascaram contexto ausente com um valor default.
- **FR-003**: A CLI (única camada de composição voltada ao operador) PODE
  manter defaults históricos (`VOLKSWAGEN/AMAROK/AMA-BR`) para
  `--manufacturer/--vehicle-model/--market`.
- **FR-004**: `run_collection_driver()` MUST validar, antes de qualquer
  navegação ou persistência, que o `CollectionContext` recebido corresponde
  exatamente ao `CollectionRun.scope` já persistido para o `run_id` dado;
  divergência MUST levantar erro explícito e não navegar/persistir nada.
- **FR-005**: `process_capture()` MUST realizar a mesma validação
  independentemente (defesa em profundidade — nenhum call site,
  mesmo chamando `process_capture()` diretamente, pode persistir conteúdo
  sob um contexto divergente do `CollectionRun.scope`).

### Functional Requirements — Scope canônico (US2)

- **FR-010**: `build_scope()` MUST rejeitar qualquer componente vazio (após
  normalização).
- **FR-011**: `build_scope()` MUST rejeitar qualquer componente contendo o
  delimitador usado pelo próprio scope (`:`).
- **FR-012**: A serialização de scope MUST ser livre de colisão — dois
  `CollectionContext` diferentes nunca produzem o mesmo `scope`, garantido
  por não permitir o delimitador dentro de nenhum componente (nunca por
  escaping ambíguo).
- **FR-013**: MUST existir `parse_scope()` capaz de recuperar um
  `CollectionContext` a partir de uma string de scope persistida
  (`CollectionRun.scope`).
- **FR-014**: `parse_scope(build_scope(context)) == context` MUST valer para
  todo `CollectionContext` válido (round-trip).
- **FR-015**: Para `manufacturer=VOLKSWAGEN, vehicle_model=AMAROK, market=AMA-BR`,
  `build_scope()` MUST produzir exatamente `AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR`
  (compatibilidade byte-a-byte com o scope histórico da feature 002).

### Functional Requirements — Normalização única (US2)

- **FR-020**: MUST existir uma única função de normalização canônica para
  manufacturer/vehicle_model/market, usada em todos os pontos que hoje
  normalizam esses campos operacionalmente (CLI → `CollectionContext`; scope;
  URL do índice de mercado; atribuição de identidade na descoberta
  MARKET_INDEX; `_maybe_mark_run_completed`).
- **FR-021**: A normalização MUST fazer trim de whitespace nas bordas e
  normalizar case de forma consistente (upper — mesma convenção já usada por
  `SpecIdentity`/`_extract_market`/scope desde 001/002).
- **FR-022**: A normalização MUST rejeitar valor vazio após trim.
- **FR-023**: A normalização MUST restringir o alfabeto permitido a letras,
  dígitos e hífen simples interno (`[A-Z0-9]+(-[A-Z0-9]+)*`) — exclui
  simultaneamente o delimitador do scope (`:`) e os caracteres inseguros de
  URL listados em FR-030, eliminando por construção qualquer ambiguidade
  entre a forma canônica e sua forma de URL (nunca dois valores canônicos
  distintos colapsam na mesma URL).
- **FR-024**: `" GOL "` e `"GOL"` MUST normalizar para o mesmo componente
  canônico (`"GOL"`).
- **FR-025** (decisão registrada, não ambígua — ver Assumptions): as leituras
  já existentes de `list_by_scope()` (SQL `UPPER(...)`) e das funções de
  scope de `analysis/comparison.py`/`analysis/redundancy.py` (003) já
  implementam, de forma independente, uma regra equivalente
  (`strip().upper()`) para qualquer valor que passe pela normalização
  canônica desta feature — não são alteradas (Constitution: preservar
  feature 003 intacta); a equivalência é estrutural (mesma regra,
  implementações distintas), não uma migração pendente.

### Functional Requirements — URL segura (US1, US2)

- **FR-030**: `build_market_index_url()` MUST nunca aceitar, mesmo
  silenciosamente, componente contendo `/`, `\`, `..`, `?`, `#`, `:` ou vazio
  — garantido estruturalmente por só aceitar um `CollectionContext` já
  validado (FR-023), nunca strings arbitrárias não normalizadas.
- **FR-031**: A transformação componente-canônico → segmento de URL MUST ser
  lossless e sem colisão (apenas `lower()`, sem substituição de caracteres
  que possa fazer dois valores canônicos diferentes colidirem na mesma URL).
- **FR-032**: Para `manufacturer=VOLKSWAGEN, vehicle_model=AMAROK, market=AMA-BR`,
  `build_market_index_url()` MUST produzir exatamente
  `https://www.amayama.com/en/genuine-catalogs/epc/volkswagen-overall/amarok/ama-br`.

### Functional Requirements — Validação do conteúdo descoberto (US4)

- **FR-040**: Ao processar um MARKET_INDEX com entradas descobertas, o
  sistema MUST comparar o `market` extraído da página (breadcrumb) com
  `context.market`; em caso de divergência, nenhuma `SpecIdentity`/
  `DiscoveredSpecEntry` MUST ser persistida para essa captura.
- **FR-041**: Divergência de FR-040 MUST ser sinalizada via
  `ProcessCaptureResult.critical_error=True`, e `run_collection_driver()`
  MUST abortar o run (evento explícito, mesmo padrão já usado para
  `MARKET_INDEX_CHALLENGE_TIMEOUT`) antes de prosseguir para descoberta de
  specs.
- **FR-042**: `manufacturer`/`vehicle_model` nunca são extraídos de conteúdo
  de página (sempre atribuídos a partir de `context`) — não há, portanto,
  checagem equivalente a FR-040 para esses dois campos no nível MARKET_INDEX
  (estruturalmente impossível divergirem nesse ponto).

### Functional Requirements — Isolamento entre modelos (US3)

- **FR-030-A** *(Cenário A)*: Com Amarok completamente populada (specs,
  manifests, checkpoints ACCEPTED, snapshots VALID, current_state), iniciar
  coleta de GOL MUST resultar em zero specs/manifests/checkpoints/snapshots/
  current_state herdados da Amarok, e o run de GOL MUST permanecer
  incompleto.
- **FR-031-A** *(Cenário B)*: Duas specs com mesmo `model_code`/
  `amayama_catalog_id`/`market` mas `vehicle_model` diferente MUST produzir
  `stable_key()` diferentes — nenhuma colisão de identidade ou de estado.
- **FR-032-A** *(Cenário C)*: Mesmo `vehicle_model`, `market` diferente MUST
  produzir isolamento total (specs, scope) — mesma garantia de B aplicada ao
  eixo `market`.
- **FR-033-A** *(Cenário D)*: `--resume` de um run de outro modelo/mercado
  MUST ser rejeitado (`IncompatibleResumeRunError`, já existente,
  reconfirmado sob a nova arquitetura).
- **FR-034-A** *(Cenário E)*: coberto por FR-004/FR-005.
- **FR-035-A** *(Cenário F)*: coberto por FR-040/FR-041.

### Functional Requirements — Run completion (FR adicional)

- **FR-050**: `_maybe_mark_run_completed()` MUST considerar exclusivamente
  specs/manifests/checkpoints do `CollectionContext` do run avaliado — nunca
  specs de outro modelo/mercado persistidas no mesmo banco.
- **FR-051**: Um run cujo contexto ainda não tem nenhuma spec VALID MUST
  permanecer incompleto mesmo que outro contexto no mesmo banco esteja
  100% VALID.

### Functional Requirements — Compatibilidade (FR adicional)

- **FR-060**: O banco/dados já existentes da Amarok (`stable_key`s, scope,
  raw captures, snapshots, fingerprints) MUST permanecer válidos e legíveis
  sem migração destrutiva.
- **FR-061**: A feature 003 (corpus analysis) MUST permanecer inalterada em
  comportamento.
- **FR-062**: CAPTCHA/challenge human-in-the-loop MUST permanecer inalterado
  em comportamento.
- **FR-063**: A CLI, para quem não informa `--manufacturer/--vehicle-model/--market`,
  MUST se comportar exatamente como antes (scope/URL Amarok/AMA-BR).
- **FR-064**: `FIXED_SCOPE` PODE permanecer no código apenas como default
  histórico documentado; nenhuma lógica operacional nova MUST depender dele
  como fonte de contexto corrente.

### Key Entities

- **CollectionContext**: `(source, manufacturer, vehicle_model, market)`,
  imutável, normalizado e validado na construção — fonte única de verdade do
  contexto operacional de uma coleta. Não persistido diretamente; sua
  serialização determinística é `CollectionRun.scope`.
- **CollectionRun.scope**: string persistida, agora formalmente o resultado
  de `build_scope(CollectionContext)` — recuperável via `parse_scope()`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos testes dos cenários A–F (US3) passam com banco
  compartilhado Amarok+GOL.
- **SC-002**: Nenhuma chamada interna de execução (`process_capture`,
  `run_collection_driver`) aceita contexto ausente/default mascarante —
  verificado por assinatura (sem valor default) e por teste de rejeição
  explícita de contexto divergente.
- **SC-003**: Suíte completa de testes permanece 100% verde após a mudança
  (nenhuma regressão na feature 002/003).
- **SC-004**: `ruff`/`mypy src` permanecem limpos nos arquivos alterados.

## Assumptions

- O alfabeto canônico de componente (`[A-Z0-9]+(-[A-Z0-9]+)*`) cobre todos os
  valores reais observados (Amayama/Volkswagen: `AMA-BR`, `AMAROK`,
  `VOLKSWAGEN`) e é suficiente para os demais modelos Volkswagen esperados
  (ex.: `T-CROSS`, `GOL`, `POLO`, `VIRTUS`). Não é uma NEEDS CLARIFICATION —
  é uma decisão de design explícita desta feature (FR-023), motivada por
  eliminar ambiguidade de colisão entre scope e URL (item 4 do pedido do PO);
  se um modelo Volkswagen real exigir caractere fora desse alfabeto, isso é
  uma nova ambiguidade a ser resolvida em gate futuro, não assumida aqui.
- `list_by_scope()`/`analysis/comparison.py`/`analysis/redundancy.py` (003)
  não são alterados — sua regra de normalização já é equivalente à canônica
  desta feature para qualquer valor que passe por `CollectionContext`
  (ver FR-025).
- `parsing/market_index.py` (parser Nível A) não é alterado — a validação de
  FR-040 ocorre na camada de orquestração (`process_capture`), não no
  parser, preservando a separação parser/pipeline exigida pela Constitution
  §6 e o item 8 do pedido do PO ("não alterar parser EPC").
- Nenhuma coleta real e nenhum commit são executados como parte desta
  entrega (instrução explícita do PO).
