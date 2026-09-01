# Feature Specification: Scraper Real Amarok AMA-BR — Navegador Assistido, Human-in-the-Loop e Resume

**Feature Branch**: `002-amarok-ama-br-browser-scraper`

**Created**: 2026-08-27

**Status**: Draft

**Input**: GitHub Issue #10 — "FEATURE — scraper real Amarok AMA-BR com navegador assistido e resume". Especificar o scraper operacional real da Amayama para o piloto Volkswagen Amarok / mercado `AMA BR`, usando o core de ingestão já mergeado (feature `001-amarok-ama-br-ingestion`): transporte por navegador real (Selenium e/ou Chrome DevTools Protocol) com sessão persistente do usuário, captura de `page_source`/URL efetiva/timestamp roteada para `process_capture()`, pausa human-in-the-loop obrigatória diante de CAPTCHA/Cloudflare (sem bypass), checkpoint/resume determinístico sobrevivendo a interrupção/reinício, controles operacionais seguros (dry-run/limites/filtros/continuação), observabilidade em terminal, e testabilidade 100% offline via double/fake de transporte — em conformidade com `.specify/memory/constitution.md`, `docs/sdd/EXECUTION_POLICY.md` e a arquitetura já aprovada de `001-amarok-ama-br-ingestion`.

**Amendment (2026-08-27) — CLARIFY**: as cinco questões registradas em "Open Questions" na versão original desta spec (resume/`run_id`, retry de unidades rejeitadas, ciclo de vida do navegador, freshness/revalidação, limite do dry-run) foram decididas explicitamente pelo Product Owner. Ver **DEC-005 a DEC-009** na seção "Decisões". Nenhum requisito funcional foi decidido por suposição — todas as mudanças abaixo materializam decisões explícitas do PO, não interpretações do implementador.

## Contexto herdado (não reaberto nesta feature)

Esta feature **não** reimplementa nem redesenha o núcleo de ingestão — ele já existe, está mergeado, e é reutilizado como está:

- `process_capture()` (`orchestration/pipeline.py`) já roteia uma `RawCaptureInput` por `capture_kind` (`MARKET_INDEX`/`SPEC_NAVIGATION`/`GROUP_DETAIL`) para `accept_capture()` → `classify_capture()` → parser correspondente → `CheckpointEntry` (via `upsert_checkpoint()`), preservando raw **antes** de qualquer validação (Constitution §4).
- `try_finalize_spec_entry()`/`finalize_spec_entry()` já finalizam uma spec entry em `SpecSnapshot` (`VALID`/`INCOMPLETE`) assim que todos os `(category_slug, group_id)` do manifesto autoritativo estão `ACCEPTED` — já invocado automaticamente por `run_collection()` após cada `GROUP_DETAIL` aceito.
- `get_pending_groups()` já deriva o universo pendente de um `(run_id, spec_key)` a partir do manifesto autoritativo (`SpecGroupManifest`) menos os `CheckpointEntry` já `ACCEPTED` — é o mecanismo de resume em nível de `Group` já implementado.
- `route_if_challenge()` já sinaliza human-in-the-loop quando `classify_capture()` retorna `CHALLENGE` (DEC-003) — nunca tenta resolver.
- Persistência (SQLite + filesystem content-addressed), identidade (`SpecIdentity`/`stable_key`), estados de checkpoint (`PENDING/IN_PROGRESS/ACCEPTED/REJECTED`) e de snapshot (`VALID/INCOMPLETE/STALE/SUPERSEDED/INVALID`) são os mesmos de `001-amarok-ama-br-ingestion` — nenhum vocabulário paralelo é criado por esta feature.

O que esta feature **efetivamente adiciona** é: (1) um transporte real por navegador Chrome que produz `RawCaptureInput` a partir de páginas reais da Amayama, e (2) um **driver de coleta dinâmico** — hoje `run_collection()` espera uma lista de capturas já conhecida; um scraper real precisa descobrir o que capturar em cada nível (market index → specs → manifesto → grupos pendentes) e agir sobre isso incrementalmente, pausando e retomando diante de challenge. Nenhuma regra de domínio (parsing, validação, identidade, fingerprints, equivalência, imagens, snapshots) é reimplementada na camada de navegador.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Descoberta real dos spec entries Amarok AMA-BR via navegador (Priority: P1)

Como operador de coleta, preciso que o sistema abra a página real de índice de mercado da Amayama para Amarok/`AMA BR` em um Chrome real, capture o HTML e o roteie para `process_capture()`, de modo que os spec entries descobertos sejam os mesmos que um humano veria navegando manualmente — nunca uma lista fixa no código.

**Why this priority**: É o ponto de entrada de toda a feature. Sem transporte real funcionando no nível MARKET_INDEX, nenhuma outra capacidade desta feature (navegação por spec, grupos, checkpoint, challenge) tem o que processar.

**Independent Test**: Executar o transporte apontando para a página real de índice do Amarok/AMA-BR, capturar o `page_source`, alimentar `process_capture(capture_kind=MARKET_INDEX, ...)`, e verificar que `DiscoveredSpecEntry`/`SpecIdentity` são persistidos exatamente como já testado em `001` para o mesmo HTML — sem nenhuma lista hardcoded envolvida na descoberta.

**Acceptance Scenarios**:

1. **Given** um Chrome real navega até a página de índice de mercado do Amarok `AMA BR`, **When** o `page_source`, a URL efetiva e o timestamp são capturados e roteados para `process_capture()`, **Then** cada spec entry presente na página real é descoberto e persistido com sua identidade completa, sem qualquer referência a um código de catálogo específico no caminho de descoberta em produção.
2. **Given** a página de índice real lista múltiplos spec entries, **When** a descoberta é executada duas vezes seguidas (mesma sessão), **Then** o conjunto de spec entries descobertos é o mesmo (determinismo), sem duplicação de identidade.
3. **Given** a página de índice não pôde ser interpretada pelo parser existente (`critical_error`), **When** essa condição ocorre, **Then** o transporte não trata a captura como sucesso e o erro é reportado como evidência, sem inventar spec entries.

---

### User Story 2 - Coleta automática de manifesto e de todos os group-details de uma spec (Priority: P2)

Como operador de coleta, preciso que, para uma spec entry descoberta, o sistema navegue automaticamente até a página de navegação da spec (SPEC_NAVIGATION), capture o manifesto real, e então navegue e capture, um a um, todos os `GROUP_DETAIL` listados nesse manifesto — cada captura roteada para `process_capture()` com `spec_key`/`category_slug`/`group_id` corretos.

**Why this priority**: É o núcleo operacional do MVP — sem isso, nenhuma spec chega a `collection_complete`/`VALID`. Depende da User Story 1 já ter produzido spec entries para navegar.

**Independent Test**: Selecionar uma spec entry já descoberta (via filtro operacional, ver User Story 5), rodar o driver de coleta contra o site real, e verificar que o manifesto autoritativo é salvo e que, ao final, todo `(category_slug, group_id)` do manifesto tem `CheckpointEntry.status == ACCEPTED`.

**Acceptance Scenarios**:

1. **Given** uma spec entry descoberta, **When** sua página de navegação é capturada e roteada como `SPEC_NAVIGATION`, **Then** um `SpecGroupManifest` autoritativo é persistido para aquele `(spec_key, run_id)`.
2. **Given** um manifesto autoritativo existe para uma spec, **When** o driver de coleta é executado, **Then** ele navega e captura cada `GROUP_DETAIL` listado — nunca um grupo fora do manifesto, nunca pulando um grupo listado sem motivo registrado.
3. **Given** todos os grupos do manifesto foram capturados com sucesso, **When** a última captura é aceita, **Then** `try_finalize_spec_entry()` (já existente) produz um `SpecSnapshot` com `state == VALID` sem que a camada de navegador precise calcular completude por conta própria.

---

### User Story 3 - Pausa human-in-the-loop diante de CAPTCHA/Cloudflare, sem bypass (Priority: P3)

Como operador de coleta, preciso que, ao encontrar um challenge real durante a navegação, o sistema pare de avançar naquela unidade de trabalho, me avise claramente no terminal, e nunca tente contornar a proteção — para que a coleta nunca viole a política de segurança do projeto mesmo operando contra o site real.

**Why this priority**: É o requisito de segurança mais crítico da feature (Constitution §5) e o único ponto onde uma decisão errada teria consequência irreversível (bypass de proteção). Prioridade alta mesmo dependendo de US1/US2 já existirem para ter o que pausar.

**Independent Test**: Simular (via double de transporte, sem rede real) uma captura cujo conteúdo aciona `CHALLENGE` em `classify_capture()`, verificar que a unidade correspondente nunca transiciona para `ACCEPTED`, que um sinal human-in-the-loop é emitido, e que a execução não aborta — permanece pausada/retomável.

**Acceptance Scenarios**:

1. **Given** a navegação chega a uma página de challenge real, **When** a captura é roteada para `process_capture()`, **Then** o outcome é `CHALLENGE` (via `classify_capture()` já existente), a unidade correspondente fica `REJECTED`/pendente — nunca `ACCEPTED` — e nenhuma tentativa automática de resolução ocorre.
2. **Given** um challenge pausou o avanço, **When** um humano resolve manualmente o challenge na mesma janela do Chrome real ao qual o sistema está anexado via CDP (DEC-007), **Then** o sistema detecta a página válida sem exigir reinício do processo e retoma automaticamente a partir da mesma unidade pausada.
3. **Given** um challenge ocorre no meio da enumeração (ex.: entre grupos de uma mesma spec), **When** isso acontece, **Then** grupos já `ACCEPTED` antes do challenge permanecem `ACCEPTED` — o challenge nunca invalida trabalho anterior.

---

### User Story 4 - Retomada após interrupção sem recoleta desnecessária (Priority: P4)

Como operador de coleta, preciso interromper a execução (Ctrl+C, falha de rede, navegador fechado, reinício do computador) e retomá-la depois — explicitamente por `run_id` ou automaticamente quando não houver ambiguidade — sem que unidades já `ACCEPTED`/specs já `VALID` sejam recoletadas, e sem que o sistema jamais escolha entre execuções incompletas concorrentes por conta própria.

**Why this priority**: É a garantia de resiliência operacional central do issue; depende de US2 já ter produzido progresso para haver o que retomar.

**Independent Test**: Rodar o driver de coleta (com transporte double) até que ao menos um `Group` fique `ACCEPTED`, interromper o processo, reiniciar apontando para a mesma execução (com e sem `--resume` explícito), e verificar que `get_pending_groups()` não retorna esse grupo e que ele não é renavegado; separadamente, criar duas `CollectionRun` incompletas do mesmo escopo e verificar que uma reinicialização sem `--resume`/`--new-run` recusa-se a escolher uma delas automaticamente.

**Acceptance Scenarios**:

1. **Given** um `Group` já está `ACCEPTED` antes da interrupção, **When** a execução é retomada (via `--resume <run_id>` explícito ou via resume automático de execução única compatível), **Then** esse `Group` não é renavegado nem recapturado.
2. **Given** uma spec entry já possui `SpecSnapshot.state == VALID` de uma execução anterior (mesma ou outra `run_id`), **When** uma nova execução roda sobre o mesmo escopo, **Then** essa spec entry é ignorada por completo (nem sua navegação é refeita) — independente de qual `run_id` está ativo (DEC-005).
3. **Given** a interrupção ocorreu no meio de uma spec (alguns grupos `ACCEPTED`, outros ainda não) sob um `run_id` específico, **When** essa mesma execução é retomada (mesmo `run_id`), **Then** ela continua exatamente pelos grupos pendentes daquela spec, sem refazer os já aceitos.
4. **Given** nenhuma `CollectionRun` incompleta existe para o escopo operacional (Amarok `AMA BR`), **When** o operador inicia uma execução sem `--resume`/`--new-run`, **Then** o sistema cria uma nova `CollectionRun` normalmente (DEC-005).
5. **Given** exatamente uma `CollectionRun` incompleta existe para o mesmo escopo operacional, **When** o operador inicia uma execução sem `--resume`/`--new-run`, **Then** o sistema resume automaticamente essa `CollectionRun` (DEC-005).
6. **Given** duas ou mais `CollectionRun` incompletas existem para o mesmo escopo operacional, **When** o operador inicia uma execução sem `--resume`/`--new-run`, **Then** o sistema NÃO escolhe nenhuma por heurística — recusa-se a prosseguir e exige que o operador informe `--resume <run_id>` explícito (ou `--new-run`).
7. **Given** existe uma `CollectionRun` incompleta compatível, **When** o operador passa `--new-run`, **Then** uma nova `CollectionRun` é criada mesmo assim, sem tocar a execução incompleta anterior.
8. **Given** o operador passa `--resume <run_id>` para um `run_id` cujo escopo não é compatível com Amarok `AMA BR`, ou que já está completo, **When** essa validação ocorre, **Then** o sistema rejeita com erro claro, nunca prossegue silenciosamente sobre um escopo diferente nem finge que há trabalho pendente onde não há.

---

### User Story 5 - Controles operacionais seguros para testar sem centenas de requests (Priority: P5)

Como operador de coleta, preciso de formas seguras de validar o comportamento do scraper sem disparar a coleta completa: um `--dry-run` estritamente somente-leitura para inspecionar o plano operacional sem tocar em nada, e — separadamente, como execuções reais e reduzidas — limite de specs, limite de grupos por spec, filtro por spec específica (dentre as descobertas), e continuação de uma execução existente — com progresso visível no terminal.

**Why this priority**: Viabiliza validação incremental e segura do MVP contra o site real sem risco operacional; não bloqueia US1-US4 tecnicamente, mas é pré-requisito para validar as demais com responsabilidade.

**Independent Test**: (a) Rodar `--dry-run` contra um estado persistido pré-populado e verificar, via inspeção do banco/filesystem antes e depois, que nenhum byte foi escrito e nenhuma navegação ocorreu; (b) separadamente, rodar o driver com `--limit-specs 1 --limit-groups 2` (ou equivalente conceitual) contra um double de transporte com múltiplas specs/grupos disponíveis, e verificar que exatamente 1 spec e no máximo 2 grupos dela são processados **normalmente** (navegação real, pipeline completo, checkpoint alterado), com progresso reportado no terminal a cada etapa.

**Acceptance Scenarios**:

1. **Given** `--dry-run` é ativado, **When** a execução roda, **Then** zero navegação ocorre, zero nova `RawCapture`/`RawBlob` é gravada, zero `CheckpointEntry` é escrito/alterado, e zero `SpecSnapshot` é finalizado — o sistema apenas lê o estado já persistido (specs descobertas, manifestos existentes, checkpoints existentes, runs existentes) e exibe no terminal o plano operacional que seria executado (DEC-009), incluindo qual decisão de resume (nova execução / resume automático / ambiguidade exigindo `--resume`) seria tomada.
2. **Given** `--dry-run` é ativado sobre um estado persistido vazio (nada descoberto ainda), **When** a execução roda, **Then** o plano exibido reflete "nada a fazer sem uma descoberta real primeiro" — sem inventar specs nem simular descoberta.
3. **Given** um filtro de quantidade de specs é definido (sem `--dry-run`), **When** a execução roda, **Then** no máximo essa quantidade de specs é processada, navegando normalmente e persistindo raw/checkpoint como qualquer execução real (DEC-009 — isto não é dry-run).
4. **Given** um filtro de quantidade de grupos por spec é definido (sem `--dry-run`), **When** a execução roda, **Then** no máximo essa quantidade de grupos é capturada por spec naquela execução, navegando e persistindo normalmente.
5. **Given** um filtro por identidade de spec específica (já descoberta) é aplicado (sem `--dry-run`), **When** a execução roda, **Then** apenas essa spec é processada normalmente — o filtro nunca se torna uma regra de descoberta em produção (FR-009).
6. **Given** uma execução real (não dry-run) está em andamento, **When** o operador observa o terminal, **Then** ele vê, no mínimo: spec atual, grupo atual, progresso atual/total, contagens de ACCEPTED/SKIPPED-por-checkpoint/CHALLENGE-aguardando-humano/RETRY-transporte/REJEITADO-aguardando-ação-manual/erro real, e um resumo final ao término.

---

### User Story 6 - Navegação conservadora e responsável (Priority: P6)

Como operador de coleta, preciso que a navegação automática se comporte de forma conservadora — uma sessão real, sem concorrência agressiva, com intervalos configuráveis — para não sobrecarregar a Amayama nem se comportar como um flood de requests.

**Why this priority**: É um requisito de responsabilidade operacional transversal; tem valor mesmo isolado (pode ser validado sem depender das demais histórias em produção), mas normalmente é observado em conjunto com US2/US4.

**Independent Test**: Rodar o driver contra um double de transporte que registra timestamps de cada "navegação" simulada, e verificar que (a) não há duas capturas em paralelo na configuração padrão, e (b) o intervalo entre capturas respeita o valor configurado (não um número fixo no código).

**Acceptance Scenarios**:

1. **Given** a configuração padrão desta feature, **When** o driver executa, **Then** as capturas ocorrem sequencialmente (sem concorrência) nesta versão do MVP.
2. **Given** um intervalo mínimo entre capturas é configurado, **When** o driver executa, **Then** esse intervalo é respeitado entre navegações consecutivas.
3. **Given** nenhuma evidência de necessidade de paralelismo foi apresentada, **When** este MVP é implementado, **Then** nenhum número arbitrário de concorrência/intervalo é fixado no código sem ser configurável.

---

### Edge Cases

- O navegador é fechado manualmente pelo operador no meio de uma captura → a execução deve poder ser retomada depois sem perda de trabalho `ACCEPTED` (mesma garantia de US4).
- A rede cai no meio de uma navegação (falha de transporte, antes de qualquer `RawCaptureInput` existir) → a unidade em curso não deve ser marcada `ACCEPTED`/`REJECTED` pelo pipeline de validação; é tratada como falha de transporte e pode ser tentada de novo automaticamente, com retry configurável (DEC-006) — nunca confundida com uma rejeição de `classify_capture()`.
- Uma captura chega a `classify_capture()` e é `INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED` → a unidade fica `REJECTED` com evidência preservada e raw preservado; ela **não** é retentada automaticamente na próxima passada do driver — permanece assim até ação explícita do operador (DEC-006).
- Um challenge aparece já na primeira página (MARKET_INDEX), antes de qualquer spec ter sido descoberta → a pausa human-in-the-loop se aplica igualmente a esse nível, não apenas a `GROUP_DETAIL`.
- Um grupo listado no manifesto retorna, na prática, uma página estruturalmente incompatível com o parser (`critical_error`) → o grupo fica `REJECTED` com evidência (`outcome=INVALID` ou equivalente); não é tratado como challenge nem como sucesso, e não é retentado automaticamente (DEC-006).
- Duas execuções (`run_id` diferentes) tentam processar a mesma spec entry "ao mesmo tempo" → fora de escopo desta feature garantir correção sob concorrência multi-processo (ver Fora de Escopo); o SQLite de escritor único de `001` continua sendo a premissa. Adicionalmente, a lógica de seleção de run (DEC-005) nunca escolhe automaticamente entre múltiplas execuções incompletas concorrentes — exige `--resume` explícito nesse caso.
- O computador reinicia com o Chrome real ainda "aberto" segundo o sistema operacional, mas o processo do scraper morreu → a retomada (attach via CDP a esse mesmo Chrome, DEC-007) deve funcionar a partir do estado persistido (SQLite/checkpoint), não de nenhum estado em memória do processo anterior.
- Nenhum Chrome com depuração remota habilitada está acessível quando a execução inicia (real, não dry-run) → o sistema deve falhar de forma clara e imediata, nunca lançar/gerenciar um Chrome por conta própria nem simular uma sessão (DEC-007 — o MVP depende do operador já ter aberto o Chrome).
- `--dry-run` é solicitado para uma spec ainda não descoberta (identidade inexistente) → o plano exibido reflete que não há nada a mostrar para essa spec; nenhuma descoberta é simulada (DEC-009).
- `--dry-run` é combinado com `--resume <run_id>`/`--limit-specs`/outros filtros → o dry-run permanece estritamente somente-leitura; ele apenas relata qual seria o efeito desses filtros/decisão de resume, sem executá-los (DEC-009).
- A execução é interrompida antes que qualquer manifesto autoritativo exista para uma spec em andamento → ao retomar (mesmo `run_id`), `get_pending_groups()` não tem universo conhecido (`NoAuthoritativeManifestError`); a spec deve voltar a capturar `SPEC_NAVIGATION` antes de qualquer `GROUP_DETAIL`.
- Uma segunda execução é iniciada quando **todas** as specs do escopo já estão `VALID` → a execução deve concluir rapidamente reportando zero trabalho pendente, sem erro, sem recoletar nada e sem exigir `--force` (DEC-008 — `VALID` é reutilizado por padrão).
- O operador quer forçar a recoleta de uma spec já `VALID` (ex.: suspeita de mudança na fonte) → só ocorre via ação explícita equivalente a `--force` (mecanismo exato definido em PLAN); nunca por inferência automática de tempo decorrido (DEC-008).
- O humano resolve o challenge mas navega para uma página diferente da esperada (ex.: home page) → o sistema não deve tratar isso como "challenge resolvido com sucesso" só porque a página deixou de ser um challenge; a captura resultante ainda passa por `classify_capture()`/parsing normal e pode ser `INVALID`/`INCOMPLETE` se não for o conteúdo esperado — e, por DEC-006, essa rejeição resultante não é retentada automaticamente.

## Requirements *(mandatory)*

### Functional Requirements

**Transporte**

- **FR-001**: O sistema DEVE adquirir HTML real via uma sessão de navegador Chrome real (não simulada/mockada) como mecanismo de transporte de produção desta feature, entregando `page_source`, URL efetiva e timestamp de coleta para o núcleo já existente (`RawCaptureInput` → `process_capture()`), sem reimplementar parsing ou validação de domínio na camada de navegador.
- **FR-002**: O transporte DEVE usar Chrome DevTools Protocol (CDP) como mecanismo de conexão ao Chrome (diretamente ou via uma biblioteca que fale CDP, ex.: Selenium 4+ em modo de conexão remota) — decidido definitivamente por DEC-007; a escolha exata de biblioteca é decisão de PLAN, mas o modelo de ciclo de vida (attach, não lançamento próprio — FR-003) não é.
- **FR-003**: O transporte DEVE operar por *attach* via Chrome DevTools Protocol (CDP) a um Chrome real já aberto pelo próprio operador — nunca lançando/gerenciando sua própria instância de Chrome nesta feature (DEC-007). Isso preserva a sessão persistente do usuário (cookies/login/estado) e garante que a resolução humana de um challenge (User Story 3) ocorra na mesma janela observada pelo sistema.
- **FR-003a**: A arquitetura DEVE manter o transporte (incluindo o mecanismo de attach via CDP) atrás de uma interface/porta própria desta feature, análoga em espírito a `RawBlobStore`/`RawCaptureRepository` (`contracts/ports-contract.md` de `001`) — nenhum módulo de domínio, parsing, normalização, fingerprints, equivalência, persistência ou do `orchestration` core existente conhece detalhes do CDP. Isso permite adicionar, no futuro, outro mecanismo de navegador sem reescrever o núcleo (DEC-007).
- **FR-004**: A sessão operacional do transporte NÃO DEVE habilitar tradução automática de página do navegador; o detector `TRANSLATION_CONTAMINATED` já existente continua sendo a autoridade que rejeita qualquer página contaminada — o transporte não o enfraquece nem o contorna.
- **FR-005**: Toda captura realizada pelo transporte DEVE preencher, sem omissão, os campos já exigidos por `RawCaptureInput` (`capture_kind`, `source_url`, `collected_at`, `acquisition_mode`, `raw_content`) a partir de dados reais da navegação — nunca valores sintéticos ou inferidos.

**Enumeração**

- **FR-006**: O sistema DEVE descobrir spec entries do Amarok `AMA BR` navegando e capturando a página real de índice de mercado (`MARKET_INDEX`), roteada por `process_capture()` — nunca a partir de uma lista fixa de spec entries no código de produção.
- **FR-007**: Para cada spec entry descoberta (ou selecionada por filtro operacional — ver FR-023 a FR-025), o sistema DEVE navegar e capturar sua página de navegação (`SPEC_NAVIGATION`), produzindo o manifesto autoritativo via `process_capture()`.
- **FR-008**: Para cada `(category_slug, group_id)` presente no manifesto autoritativo de uma spec, o sistema DEVE navegar e capturar o `GROUP_DETAIL` correspondente, roteado por `process_capture()` com `spec_key`/`category_slug`/`group_id` corretos.
- **FR-009**: Nenhum código de modelo/catálogo conhecido (`2HBC3X`, `S1BC3X`, `S6BC74`, `S7BC74`, `S7BC8A`, `AGDC8A`, ou qualquer outro) DEVE aparecer como regra de descoberta/enumeração em código de produção; esses valores só podem aparecer em testes/fixtures/evidência de regressão.

**CAPTCHA / Cloudflare / challenge**

- **FR-010**: O transporte DEVE detectar quando a navegação chega a uma página de challenge (CAPTCHA/Cloudflare) e NÃO DEVE tentar resolvê-la ou contorná-la, em conformidade com Constitution §5 e com `classify_capture()`/`route_if_challenge()` já existentes.
- **FR-011**: Ao detectar um challenge, o sistema DEVE pausar o avanço da unidade de trabalho afetada e sinalizar a necessidade de intervenção humana, sem abortar a execução inteira e sem descartar trabalho já `ACCEPTED`.
- **FR-012**: O sistema DEVE detectar, sem exigir reinício manual do processo, quando a página voltou a ser válida para a unidade pausada, e retomar automaticamente essa unidade — o mecanismo exato (cadência de verificação, timeout) é decisão de PLAN e DEVE ser configurável, nunca um número arbitrário fixo.
- **FR-013**: O sistema NÃO DEVE usar nenhum serviço externo de resolução de CAPTCHA, rotação de proxy para evasão, ou técnica de stealth/anti-detecção destinada a burlar as proteções da Amayama.

**Raw, provenance e integridade da validação**

- **FR-014**: Toda captura obtida pelo transporte DEVE ser preservada como `RawBlob`/`RawCapture` imutáveis via os ports já existentes (`RawBlobStore`/`RawCaptureRepository`), antes de qualquer validação/parsing — exatamente como `accept_capture()` já garante; o transporte não escreve o conteúdo bruto em nenhum outro lugar antes disso.
- **FR-015**: A camada de transporte NÃO DEVE decidir por conta própria `ACCEPTED`/`CHALLENGE`/`INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED` — essa decisão permanece exclusivamente de `classify_capture()`, invocada via `process_capture()`. O transporte PODE usar um sinal leve e não-autoritativo próprio (ex.: heurística visível no DOM) apenas para decidir quando continuar tentando durante uma pausa human-in-the-loop — nunca para marcar uma unidade como concluída/aceita.
- **FR-016**: Nenhuma unidade de trabalho (`Group`/spec entry) DEVE ser marcada como concluída/aceita apenas porque o navegador recebeu uma resposta HTTP ou renderizou uma página — a conclusão é sempre resultado de passar por `process_capture()`/`classify_capture()` e, para completude de spec entry, por `finalize_spec_entry()`/completude do manifesto autoritativo, sem alteração ao core existente.

**Checkpoint / estado operacional**

- **FR-017**: Toda captura orientada por navegador DEVE ser associada a um `CollectionRun` (`run_id`) existente e roteada pelo `CheckpointEntry` já existente (`PENDING/IN_PROGRESS/ACCEPTED/REJECTED`) — nenhum segundo modelo de estados é introduzido.
- **FR-018**: O sistema DEVE ser capaz de continuar uma execução interrompida (encerramento voluntário, Ctrl+C, falha de rede, navegador fechado, reinício da máquina, challenge) reutilizando o estado de checkpoint do mesmo `run_id`, de modo que `Group`s já `ACCEPTED` não sejam renavegados (via `get_pending_groups()`), e que spec entries já `VALID` (via `CurrentSpecState`, independente de `run_id`) sejam ignoradas por completo (DEC-005, DEC-008).
- **FR-019**: A seleção de **qual** `run_id` continuar após uma interrupção segue a regra determinística abaixo (DEC-005), usando exclusivamente estado já persistido — `CollectionRun.scope` (já existente em `001`, data-model.md §11 — para esta feature, sempre `AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR`) e `CollectionRun.completed_at` (nulo ⇔ execução incompleta):
  1. `--resume <run_id>` explícito → o sistema usa exatamente esse `run_id`; se seu `scope` não corresponder ao escopo operacional da execução atual, ou se `completed_at` já estiver preenchido, o sistema rejeita com erro claro, sem prosseguir.
  2. `--new-run` explícito → o sistema sempre cria uma nova `CollectionRun`, mesmo que existam execuções incompletas compatíveis; nenhuma delas é tocada.
  3. Sem `--resume` nem `--new-run` → o sistema consulta as `CollectionRun` com `scope` igual ao escopo operacional e `completed_at IS NULL`:
     - **zero** encontradas → cria uma nova `CollectionRun` normalmente;
     - **exatamente uma** encontrada → resume automaticamente essa `CollectionRun`;
     - **duas ou mais** encontradas → o sistema NÃO escolhe por heurística; encerra com erro instruindo o operador a informar `--resume <run_id>` (ou `--new-run`).
- **FR-020**: A política de nova tentativa para uma unidade `REJECTED` distingue duas categorias, nunca misturadas (DEC-006):
  1. **Falha de transporte/rede** (a navegação falhou antes de qualquer `RawCaptureInput`/`process_capture()` existir — a unidade nunca chegou a `classify_capture()`) — o driver PODE tentar novamente automaticamente, com número máximo de tentativas e/ou backoff configuráveis (sem número arbitrário fixo por esta especificação — ver FR-029).
  2. **Rejeição do pipeline de validação** (`classify_capture()` já produziu `INVALID`, `INCOMPLETE` ou `TRANSLATION_CONTAMINATED` para a unidade, refletido em `CheckpointEntry.evidence["outcome"]`) — o driver NÃO DEVE incluir essa unidade automaticamente na próxima passada de trabalho pendente; ela permanece registrada como `REJECTED`, com raw/provenance preservados, e exige ação explícita do operador (mecanismo exato de "retry manual" é decisão de PLAN) para ser tentada de novo.
  `CHALLENGE` continua sendo a única saída de `classify_capture()` retentada automaticamente por padrão, via o fluxo human-in-the-loop já coberto por FR-011/FR-012 — não é afetado por esta regra.
- **FR-021**: O sistema DEVE expor, para cada unidade de trabalho, exclusivamente os estados de checkpoint e de snapshot já definidos em `001` — nenhum vocabulário de estado paralelo é criado. A distinção "falha de transporte" vs. "rejeição de validação" (FR-020) é uma classificação de **consumo** do driver sobre `CheckpointEntry.evidence`/ausência de `RawCapture`, não um novo status de checkpoint.

**Controle de execução**

- **FR-022**: O sistema DEVE suportar um modo `--dry-run` estritamente somente-leitura (DEC-009): zero navegação real, zero nova `RawCapture`/`RawBlob`, zero escrita/mutação de `CheckpointEntry`/`CollectionRun`/`SpecSnapshot`, zero alteração de qualquer estado persistido. `--dry-run` apenas lê o estado já persistido (specs descobertas, manifestos, checkpoints, runs) e exibe no terminal o plano operacional que seria executado — incluindo qual decisão de resume seria tomada pela regra de FR-019.
- **FR-023**: O sistema DEVE suportar limitar a quantidade de spec entries processadas em uma execução real (não `--dry-run`) — essa execução navega normalmente, passa pelo pipeline completo e persiste raw/checkpoint como qualquer execução real (DEC-009: limites de escopo não são dry-run).
- **FR-024**: O sistema DEVE suportar limitar a quantidade de grupos processados por spec entry em uma execução real (não `--dry-run`), com a mesma ressalva de FR-023.
- **FR-025**: O sistema DEVE suportar restringir uma execução real a uma ou mais spec entries selecionadas dentre as já descobertas pelo próprio sistema — esse filtro opera sobre identidade descoberta e NUNCA se torna regra de descoberta em produção (FR-009); como os demais filtros de escopo, não é `--dry-run` (DEC-009).
- **FR-026**: O sistema DEVE suportar continuar uma execução existente via `--resume <run_id>` explícito, resume automático quando não houver ambiguidade, ou `--new-run` para forçar uma nova execução — exatamente conforme a regra determinística de FR-019 (DEC-005).
- **FR-027**: O sistema DEVE reportar em tempo real no terminal, no mínimo: spec atual, grupo atual, progresso atual/total, contagens de ACCEPTED / SKIPPED-por-checkpoint(já `VALID`) / CHALLENGE-aguardando-humano / RETRY-de-transporte / REJEITADO-aguardando-ação-manual (FR-020) / erro real, e um resumo final ao término da execução.

**Rate / comportamento responsável**

- **FR-028**: O sistema DEVE operar, por padrão nesta versão do MVP, com navegação/captura sequencial (sem concorrência).
- **FR-029**: Qualquer intervalo entre navegações/capturas DEVE ser configurável — esta especificação não fixa um valor numérico padrão sem evidência.
- **FR-030**: O sistema NÃO DEVE implementar qualquer estratégia de retry/backoff cuja finalidade seja evadir rate limiting ou bloqueio — distinto (a) do fluxo legítimo de pausa/retomada por challenge (FR-011/FR-012), e (b) do retry configurável de falha de transporte/rede genuína (FR-020.1), que existe para tolerar instabilidade de rede, não para evadir proteção.

**Persistência**

- **FR-031**: O sistema DEVE reutilizar a persistência já existente (SQLite para metadados/estado + filesystem content-addressed para raw, DEC-002 de `001`) para todo estado operacional (checkpoint, runs, manifestos, snapshots) e conteúdo bruto produzidos por esta feature — nenhum banco/serviço externo novo é introduzido.
- **FR-032**: Nenhuma nova entidade persistida é estritamente necessária para a lógica de seleção/compatibilidade de run (FR-019): `CollectionRun.scope` e `CollectionRun.completed_at`, já existentes em `001` (data-model.md §11), são suficientes para a checagem determinística de compatibilidade de escopo e de incompletude. Qualquer refinamento de schema além disso (ex.: índices/otimizações de consulta) é decisão de PLAN, não uma lacuna semântica desta spec.
- **FR-032a**: A recoleta/revalidação explícita de uma spec entry já `VALID` (DEC-008) NÃO exige nenhum novo campo persistido de "forçar" — o mecanismo (nome exato de flag/CLI a definir em PLAN) apenas instrui o driver a não aplicar, para a(s) spec(s) alvo, a checagem de "já `VALID`, pular" de FR-018; a coleta resultante segue o pipeline normal (novo `SpecSnapshot`, o anterior `VALID` transita para `SUPERSEDED`, exatamente como `001` já define).

**Relação com equivalência/deduplicação**

- **FR-033**: O sistema NÃO DEVE usar informação de equivalência/cluster/representante para decidir, antecipadamente, pular a coleta de uma spec entry — toda spec entry descoberta DEVE ser coletada de forma independente, a menos que explicitamente excluída por filtro operacional (FR-025) ou já `VALID` (FR-018); a equivalência só é calculada após a coleta independente, exatamente como no core existente.

**Testabilidade**

- **FR-034**: O transporte por navegador (incluindo o adapter CDP, DEC-007/FR-003a) DEVE ser implementado atrás de uma interface/porta que permita exercitar toda a lógica de orquestração (laço de descoberta-e-ação, pausa/retomada por challenge, roteamento de checkpoint, seleção de run) por testes automatizados usando um double/fake de transporte, sem dependência real de rede, de CDP ou de um Chrome real.
- **FR-035**: Os testes automatizados DEVEM cobrir, no mínimo, sem depender da Amayama estar online: escrita/leitura de checkpoint; retomada após interrupção (mesmo `run_id`); não recoleta de trabalho `ACCEPTED`/spec `VALID`; pausa e retomada disparadas por challenge; integração transporte → `process_capture()` (incluindo roteamento de `GROUP_DETAIL` com `spec_key`/`category_slug`/`group_id`); os quatro ramos de seleção de run de FR-019 (`--resume` válido, `--resume` com escopo/estado inválido, `--new-run`, zero/uma/múltiplas execuções incompletas compatíveis); a distinção de retry de FR-020 (falha de transporte retentada automaticamente vs. `INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED` nunca retentados sem ação explícita); e que `--dry-run` não produz nenhuma escrita observável no double de persistência.
- **FR-036**: A validação final contra o site real da Amayama é evidência de integração e NÃO substitui a suíte automatizada.

**Qualidade**

- **FR-037**: A suíte de testes completa, cobertura ≥ 90%, `ruff` e `mypy --strict` DEVEM permanecer verdes para o código introduzido por esta feature, em conformidade com Constitution §12.

### Key Entities *(include if feature involves data)*

- **Browser Transport Session**: sessão de navegador Chrome real, adquirida por *attach* via Chrome DevTools Protocol (CDP) a um Chrome já aberto pelo operador (DEC-007) — nunca lançada/gerenciada pelo próprio sistema nesta feature. Usada para adquirir `page_source`, URL efetiva e timestamp de uma página real da Amayama; não possui conhecimento de parsing/domínio — apenas entrega esses três dados ao núcleo existente via `RawCaptureInput`, atrás de uma interface/porta própria (FR-003a) que mantém o CDP invisível ao restante do sistema.
- **Collection Driver (laço de descoberta-e-ação)**: comportamento de orquestração novo desta feature que alterna entre navegar (via Browser Transport Session) e invocar o núcleo já existente (`process_capture()`, `get_pending_groups()`, `try_finalize_spec_entry()`) — descobre dinamicamente o que capturar em cada nível (market index → specs → manifesto → grupos pendentes), em vez de operar sobre uma lista pré-computada como `run_collection()` hoje assume. Aplica a classificação de retry de FR-020 (transporte vs. rejeição de validação) ao consumir `get_pending_groups()`/`CheckpointEntry`.
- **Challenge Pause**: estado operacional em que uma unidade de trabalho específica (captura de `MARKET_INDEX`, `SPEC_NAVIGATION` ou `GROUP_DETAIL`) está bloqueada por um challenge detectado e aguarda detecção automática de retorno a página válida na mesma janela do Chrome anexado via CDP — nunca resolução automática do challenge em si.
- **Operational Run Selection**: mecanismo determinístico (DEC-005, FR-019) pelo qual o sistema/operador decide, a cada início de execução, entre `--resume <run_id>` explícito, resume automático (exatamente uma `CollectionRun` incompleta de mesmo `scope`), `--new-run` explícito, ou criação normal de nova execução (zero incompletas compatíveis) — nunca escolhendo por heurística entre múltiplas incompletas compatíveis.
- **Retry Classification**: distinção de consumo (não um novo status persistido) entre **falha de transporte** (nunca chegou a `classify_capture()`; retentável automaticamente, configurável) e **rejeição de validação** (`INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED`; nunca retentada automaticamente, exige ação explícita do operador) — ver FR-020. `CHALLENGE` segue seu próprio fluxo human-in-the-loop (FR-011/FR-012), não coberto por esta distinção.
- **Execution Filters**: `--dry-run` (estritamente somente-leitura, DEC-009) é categoricamente distinto de limite de specs, limite de grupos por spec, filtro por identidade de spec já descoberta e continuação de execução (`--resume`/`--new-run`) — estes últimos executam navegação e persistência reais. Todos operam sobre identidade/estado já conhecidos pelo sistema, nunca sobre uma lista fixa de códigos de catálogo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Executar o transporte contra a página real de índice de mercado do Amarok `AMA BR` produz ao menos um spec entry descoberto com identidade completa, sem que nenhum código de spec entry apareça no código-fonte de descoberta.
- **SC-002**: Uma spec entry completa (manifesto + todos os grupos do manifesto) coletada via navegação Chrome real atinge `SpecSnapshot.state == VALID` usando `finalize_spec_entry()`/completude de manifesto já existentes, sem alteração.
- **SC-003**: Encerrar o processo no meio da coleta de uma spec e continuar a mesma execução depois resulta em zero renavegação de `Group`s já `ACCEPTED` antes do encerramento.
- **SC-004**: Uma spec entry já em `SpecSnapshot.state == VALID` não é renavegada/recoletada por uma execução posterior.
- **SC-005**: Ao encontrar um challenge real ou simulado, nenhuma unidade de trabalho é marcada `ACCEPTED`/`VALID` enquanto o challenge não é resolvido, e o avanço daquela unidade é retomado automaticamente após a resolução humana, sem reinício manual do processo.
- **SC-006**: 100% das capturas produzidas pelo transporte são preservadas como `RawBlob`/`RawCapture` imutáveis antes de qualquer validação/parsing, verificável por auditoria.
- **SC-007**: A suíte automatizada (cobrindo laço de descoberta-e-ação, checkpoint, resume, pausa por challenge e integração transporte→core) passa 100% offline, com cobertura ≥ 90%, `ruff` e `mypy --strict` verdes, sem depender da Amayama estar acessível.
- **SC-008**: Nenhum caminho de código de produção desta feature contém referência literal a `2HBC3X`, `S1BC3X`, `S6BC74`, `S7BC74`, `S7BC8A` ou `AGDC8A` fora de testes/fixtures/evidência de regressão (verificável por busca de código).
- **SC-009**: A mesma arquitetura de transporte/driver usada para uma spec Amarok é capaz de percorrer as demais spec entries Amarok descobertas no mesmo mercado, sem reescrita, quando executada sem os filtros de limite da User Story 5.
- **SC-010**: Com duas ou mais `CollectionRun` incompletas de mesmo `scope` persistidas, iniciar uma execução sem `--resume`/`--new-run` nunca produz navegação real — apenas um erro instruindo escolha explícita (DEC-005).
- **SC-011**: Uma unidade cuja última tentativa terminou em `INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED` permanece com esse status através de N execuções sucessivas do driver sem nenhuma ação explícita do operador — zero tentativas automáticas de recaptura são observadas (DEC-006).
- **SC-012**: Nenhum módulo em `validation/`, `parsing/`, `domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`, `persistence/` ou `orchestration/` (núcleo já existente de `001`) importa ou referencia diretamente uma biblioteca/API de Chrome DevTools Protocol — verificável por busca de código (DEC-007/FR-003a).
- **SC-013**: Uma spec entry já `VALID` permanece `VALID` (mesmo `snapshot_id`) através de qualquer número de execuções subsequentes que não passem `--force`/mecanismo equivalente, independentemente do tempo decorrido entre elas (DEC-008 — nenhuma expiração por tempo).
- **SC-014**: Rodar `--dry-run` contra um estado persistido não-vazio produz zero diferença observável (bytes gravados, linhas alteradas) no SQLite e no filesystem content-addressed, comparando o estado imediatamente antes e imediatamente depois (DEC-009).

## Decisões desta feature (CLARIFY, aprovadas pelo PO em 2026-08-27)

As cinco decisões abaixo resolvem, de forma definitiva, as cinco questões que a versão original desta spec havia registrado como abertas em "Open Questions". Nenhuma foi decidida por suposição do implementador.

- **DEC-005 — Seleção de `run_id` (resume)**: `--resume <run_id>` explícito sempre tem precedência e é validado contra `CollectionRun.scope`/`completed_at`. Sem `--resume` nem `--new-run`, o sistema resume automaticamente somente se existir exatamente uma `CollectionRun` incompleta (`completed_at IS NULL`) de mesmo `scope`; zero incompletas compatíveis → nova execução normal; duas ou mais → erro exigindo escolha explícita, nunca heurística. `--new-run` sempre força nova execução. Compatibilidade de escopo é determinada exclusivamente por `CollectionRun.scope` (já persistido em `001`, data-model.md §11) — nenhum novo campo é necessário. Ver FR-019, FR-026, User Story 4.
- **DEC-006 — Retry de unidades rejeitadas**: `INVALID`, `INCOMPLETE` e `TRANSLATION_CONTAMINATED` (outcomes de `classify_capture()`) NUNCA recebem retry automático nesta feature — permanecem `REJECTED`, com raw/provenance preservados, até ação explícita do operador. Falha pura de transporte/rede (nunca chegou a `classify_capture()`) é categoria separada e PODE usar retry configurável (sem número arbitrário fixo por esta spec). As duas categorias nunca são confundidas. `CHALLENGE` continua no seu próprio fluxo automático de pausa/retomada (FR-011/FR-012), não afetado por esta decisão. Ver FR-020, FR-021, FR-030.
- **DEC-007 — Ciclo de vida do navegador**: o MVP usa exclusivamente *attach* via Chrome DevTools Protocol (CDP) a um Chrome real já aberto pelo operador — nunca lançamento/gestão de Chrome pelo próprio sistema. Motivos aprovados: sessão persistente do usuário, fluxo human-in-the-loop para CAPTCHA/Cloudflare na mesma janela observada, e comportamento já validado na pesquisa exploratória anterior (`amayama_browser_fixture_collector.py`, não promovido a arquitetura de produção, mas cujo padrão de attach via CDP é o aprovado aqui). O transporte permanece atrás de uma interface/porta própria; nenhum módulo de domínio/parsing/normalização/persistência/equivalência/orchestration core conhece CDP diretamente. Ver FR-003, FR-003a, FR-034, SC-012.
- **DEC-008 — Freshness/revalidação**: o MVP não possui expiração automática baseada em tempo. Uma spec/captura já `VALID` é reutilizada normalmente, para sempre, até ação explícita do operador (mecanismo equivalente a `--force`, nome exato definido em PLAN). Nenhum TTL arbitrário é criado; staleness nunca é inferida apenas pelo tempo decorrido. Política automática de freshness permanece fora deste MVP. Ver FR-018, FR-032a, SC-013.
- **DEC-009 — Dry-run**: `--dry-run` é estritamente somente-leitura — zero navegação, zero novas capturas, zero escrita/mutação de qualquer estado persistido (checkpoint, run, snapshot, raw); apenas lê o estado já persistido e exibe o plano operacional que seria executado, incluindo a decisão de resume que seria tomada (DEC-005). Execução real e reduzida (limite de specs, limite de grupos, filtro por spec descoberta) é uma categoria distinta — navega normalmente, passa pelo pipeline completo, persiste raw/provenance e altera checkpoint normalmente; nunca é chamada de dry-run. Ver FR-022 a FR-025, SC-014.

## Decisões herdadas (não reabertas nesta feature)

Estas decisões já foram aprovadas pelo PO durante `001-amarok-ama-br-ingestion` e continuam em vigor sem alteração — esta feature não as reabre:

- **DEC-001 (001)** — aquisição de HTML por navegador é transporte validado (Constitution §5); esta feature apenas passa de manual/browser-in-the-loop para automatizado/browser-assisted, mantendo human-in-the-loop obrigatório em challenge.
- **DEC-002 (001)** — persistência SQLite + filesystem content-addressed é reutilizada sem alteração; nenhum banco externo é introduzido por esta feature.
- **DEC-003 (001)** — precedência `CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED` de `classify_capture()` é reutilizada sem alteração; o transporte não introduz um segundo caminho de decisão.
- **DEC-004 (001)** — a amostragem de evidência de regressão dos pares conhecidos (`2HBC3X`↔`S1BC3X` etc.) permanece como está; esta feature não precisa recoletar nem reafirmar esses pares para seu próprio MVP, mas também não pode contradizer a regra de "nenhum hardcode em produção" já registrada ali.

## Open Questions (requerem decisão do Product Owner antes de PLAN)

As cinco questões registradas na versão original desta spec (resume/`run_id`, retry de unidades rejeitadas, ciclo de vida do navegador, freshness/revalidação, limite do dry-run) foram todas resolvidas pelo PO — ver DEC-005 a DEC-009 acima. Nenhuma nova ambiguidade material foi encontrada durante este CLARIFY que não seja já coberta pela Constitution, pela Execution Policy, pelos artefatos de `001-amarok-ama-br-ingestion` ou pelas cinco decisões acima.

**Nenhuma questão permanece aberta ao final deste CLARIFY.** Caso uma nova ambiguidade semântica surja durante PLAN/TASKS (ex.: nome exato da flag equivalente a `--force` — DEC-008/FR-032a; granularidade exata do mecanismo de "retry manual" — DEC-006/FR-020.2; cadência de polling de retomada de challenge — FR-012), ela deve ser resolvida como decisão técnica de PLAN quando não alterar comportamento observável desta spec, ou retornar a um novo CLARIFY/PO quando alterar.

## Assumptions

- O "operador" desta feature continua sendo um usuário interno da equipe de coleta (Hubbi/PO/Claude/Codex/Antigravity), como já assumido em `001` — não há interface gráfica nem API pública nesta feature.
- O operador dispõe de um Chrome real com acesso legítimo à Amayama (nenhuma credencial/acesso especial é assumido ou fabricado por esta feature).
- O ambiente de execução é uma estação de desenvolvimento/CI, não infraestrutura de produção — mesma premissa de `001`.
- `AMA BR` e Amarok continuam sendo os mesmos identificadores já validados por `001`; esta feature não reabre essa validação.
- A saída funcional (identidade, raw, snapshots, fingerprints, equivalência) continua sendo o modelo de domínio interno já definido por `001` — esta feature não adiciona nem modifica nenhum contrato de export.
- O núcleo (`validation/`, `parsing/`, `domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`) permanece exatamente como está; qualquer necessidade percebida de alteração nele durante esta feature deve retornar ao gate apropriado, não ser feita silenciosamente aqui.

## Out of Scope

- Integração produtiva com o ecossistema Hubbi.
- Scraping de qualquer modelo/montadora além de Volkswagen Amarok nesta execução (a arquitetura deve permitir expansão futura sem reescrever o transporte — Constitution/Issue #10 — mas executar essa expansão não é exigido nesta feature).
- Bypass automatizado de CAPTCHA/Cloudflare, sob qualquer forma.
- Serviço externo automático de resolução de CAPTCHA.
- Rotação de proxy para evasão.
- Técnicas de stealth/anti-detecção destinadas a evitar mecanismos de proteção da Amayama.
- Execução distribuída/multi-processo concorrente sobre o mesmo escopo.
- Deploy em nuvem/infraestrutura de produção.
- Dashboard web (observabilidade é apenas em terminal nesta feature).
- Otimização de coleta que pule specs com base em equivalência/deduplicação histórica.
- Reescrita de parsers, normalização, fingerprints, equivalência, imagens ou snapshots já existentes e mergeados.
- Gatilho automático de revalidação/refresh de specs já `VALID` baseado em tempo decorrido — decidido definitivamente por DEC-008 (nenhum TTL, reuso indefinido até ação explícita).
- Lançamento/gestão de uma instância de Chrome pelo próprio sistema (Selenium `webdriver.Chrome()` gerenciando o processo) — decidido definitivamente por DEC-007 (attach via CDP a um Chrome já aberto pelo operador).
- Retry automático de unidades `REJECTED` por `INVALID`/`INCOMPLETE`/`TRANSLATION_CONTAMINATED` — decidido definitivamente por DEC-006 (exige ação explícita do operador).
- Qualquer manipulação de tokens/cookies com finalidade de bypass de proteção.

## Checklist de qualidade da especificação

- [x] Nenhuma implementação de código foi feita nesta etapa (SPECIFY nem CLARIFY).
- [x] Nenhum PLAN nem TASKS foi produzido nesta etapa.
- [x] Nenhum gate foi avançado além de SPECIFY/CLARIFY.
- [x] Todo requisito funcional é testável e rastreável a uma User Story e/ou Success Criteria.
- [x] Nenhuma lista de códigos de catálogo conhecidos foi introduzida como regra de descoberta (apenas citada como restrição/proibição, conforme o próprio Issue #10 pede).
- [x] As cinco decisões do PO (DEC-005 a DEC-009) foram incorporadas literalmente, sem reinterpretação — nenhuma foi decidida por suposição do implementador; nenhuma nova ambiguidade bloqueante foi introduzida por elas.
- [x] Raw é preservado antes de qualquer parsing/validação (FR-014) — inclusive para falhas de transporte (nunca chegam a gerar `RawCaptureInput`) e para rejeições de validação (`RawBlob`/`RawCapture` já gravados por `accept_capture()` antes de `classify_capture()`).
- [x] Provenance é preservada para todo outcome, incluindo `REJECTED` não retentado automaticamente (DEC-006) — nada é descartado silenciosamente.
- [x] `process_capture()` continua sendo o único pipeline autoritativo de validação/parsing/checkpoint — o transporte nunca decide `ACCEPTED`/`REJECTED` por conta própria (FR-015, FR-016).
- [x] A precedência de validação existente (`CHALLENGE > TRANSLATION_CONTAMINATED > INVALID > INCOMPLETE > ACCEPTED`, DEC-003 de `001`) não foi alterada.
- [x] Challenge continua exclusivamente human-in-the-loop, sem bypass de CAPTCHA/Cloudflare, mesmo com attach via CDP (DEC-007) — a sessão observada é a do próprio operador.
- [x] Nenhum hardcode de spec/catalog_id em produção (FR-009, SC-008); filtros operacionais (FR-025) continuam distintos de regra de descoberta.
- [x] Nenhuma otimização de coleta baseada em equivalência histórica foi introduzida (FR-033).
- [x] Checkpoint/resume permanece sobre o modelo de estados já existente de `001` (FR-021), com a regra de seleção de run explicitada (DEC-005) sem introduzir vocabulário paralelo.
- [x] A sessão operacional do Chrome não usa tradução automática (FR-004); `TRANSLATION_CONTAMINATED` continua sendo rejeitado sem exceção.
- [x] Persistência permanece SQLite + filesystem content-addressed já aprovados (FR-031); nenhuma nova entidade persistida é estritamente exigida pelas decisões desta feature (FR-032).
- [x] Testes offline do transporte/orchestration foram exigidos explicitamente, incluindo os novos ramos de resume/retry/dry-run (FR-034, FR-035).
- [x] Suíte verde, cobertura ≥ 90%, Ruff e mypy strict continuam exigidos sem exceção (FR-037).
