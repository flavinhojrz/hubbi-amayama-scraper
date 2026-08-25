# Feature Specification: MVP de Ingestão Amayama — Volkswagen Amarok (Mercado AMA BR)

**Feature Branch**: `001-amarok-ama-br-ingestion`

**Created**: 2026-08-25

**Status**: Draft

**Amendment (2026-08-25)**: Decisão do Product Owner sobre o mecanismo de aquisição de HTML bruto consolidada — ver seção "Decisions" abaixo. Nenhuma outra parte desta especificação foi alterada por esta emenda.

**Input**: GitHub Issue #3 — "SPECIFY — MVP de ingestão Amayama Amarok AMA-BR". Especificar um MVP vertical de ingestão do catálogo Volkswagen Amarok no mercado `AMA BR` da Amayama: descoberta/enumeração de spec entries, preservação de identidade (market, model_code, amayama_catalog_id, período de produção, source_url), preservação de raw data e proveniência, normalização e fingerprints versionados, equivalência exata e deduplicação segura de peças, fallback de imagem controlado, snapshots auditáveis e revalidação incremental, e coleta retomável/checkpointed — em conformidade com `.specify/memory/constitution.md` e `docs/sdd/EXECUTION_POLICY.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Descoberta e identidade de spec entries Amarok (AMA BR) (Priority: P1)

Como operador de coleta, preciso que o sistema descubra/enumere os spec entries do Volkswagen Amarok no mercado `AMA BR` da Amayama e preserve, para cada um, os campos mínimos de identidade — de modo que nenhuma entrada de catálogo seja tratada como identificada apenas pelo seu `model_code`.

**Why this priority**: É o núcleo do MVP — sem descoberta confiável e identidade preservada, nenhuma outra capacidade (raw, normalização, equivalência, snapshots) tem base para operar corretamente.

**Independent Test**: Pode ser validado isoladamente executando a descoberta sobre o mercado `AMA BR` para o modelo Amarok e verificando que cada spec entry resultante possui `market`, `model_code`, `amayama_catalog_id`, período de produção e `source_url` como campos distintos e inspecionáveis.

**Acceptance Scenarios**:

1. **Given** o mercado `AMA BR` contém múltiplos spec entries para o Amarok, **When** a descoberta é executada, **Then** cada spec entry encontrado é registrado com `market`, `model_code`, `amayama_catalog_id`, período de produção e `source_url` preenchidos ou explicitamente ausentes quando não comprovados pela fonte.
2. **Given** dois spec entries distintos compartilham o mesmo `model_code` (ex.: `S7BC8A`) mas possuem `amayama_catalog_id` diferentes, **When** ambos são descobertos, **Then** o sistema os trata como duas entradas de catálogo distintas, nunca como uma única.
3. **Given** a hierarquia declarada (modelo → mercado → spec entry → categoria → grupo → schema → OEM), **When** um spec entry é registrado, **Then** sua posição nessa hierarquia é representada de forma rastreável.

---

### User Story 2 - Preservação de raw data auditável com human-in-the-loop (Priority: P2)

Como operador de coleta, preciso que todo dado bruto capturado seja preservado antes de qualquer transformação, e que situações de CAPTCHA/Cloudflare/challenge sejam roteadas para intervenção humana em vez de bypass automatizado — para que a coleta seja auditável e não dependa de burlar proteções da fonte.

**Why this priority**: Sem preservação de raw e sem uma resposta segura a challenges, qualquer dado adaptado adiante perde rastreabilidade e a coleta corre risco de violar a política de segurança do projeto.

**Independent Test**: Pode ser validado isoladamente submetendo uma captura simulada com conteúdo raw íntegro e verificando que o raw é preservado inalterado antes da transformação; e submetendo uma captura simulada com challenge, verificando que o fluxo é desviado para human-in-the-loop em vez de prosseguir automaticamente.

**Acceptance Scenarios**:

1. **Given** uma página de spec entry foi capturada com sucesso, **When** a captura é aceita, **Then** o conteúdo bruto é preservado de forma imutável antes de qualquer limpeza ou adaptação, e evidência suficiente para auditoria é gerada.
2. **Given** uma página apresenta um challenge do tipo CAPTCHA ou Cloudflare, **When** o sistema encontra essa condição, **Then** ele não tenta contornar o challenge automaticamente e sinaliza a necessidade de intervenção humana.
3. **Given** uma página retorna HTML inválido ou malformado, **When** essa página é avaliada, **Then** ela é rejeitada como conteúdo de catálogo válido.
4. **Given** uma página foi alterada por tradução automática do navegador, **When** essa contaminação é detectada, **Then** o conteúdo não é aceito como catálogo válido.

---

### User Story 3 - Normalização determinística e fingerprints versionados (Priority: P3)

Como operador de coleta, preciso que peças e schemas sejam normalizados de forma determinística e versionada, e que fingerprints independentes sejam calculados para peças, schema semântico e imagens — para que a base de comparação de equivalência seja estável e auditável.

**Why this priority**: A normalização e os fingerprints são o alicerce técnico sobre o qual a equivalência exata (User Story 4) é avaliada; sem eles, não há base determinística para decidir duplicidade.

**Independent Test**: Pode ser validado isoladamente aplicando a normalização/fingerprint a um mesmo conjunto de peças duas vezes e verificando que o resultado é idêntico (determinismo), e aplicando-a a duas versões com uma peça a mais/a menos e verificando que o fingerprint muda.

**Acceptance Scenarios**:

1. **Given** um mesmo conjunto de peças de um spec entry, **When** a normalização/fingerprint é aplicada duas vezes de forma independente, **Then** o resultado é idêntico.
2. **Given** um spec entry cujas peças mudam (adição, remoção ou alteração de quantidade), **When** o fingerprint é recalculado, **Then** o valor resultante é diferente do anterior.
3. **Given** peças, schema semântico e imagens de um mesmo spec entry, **When** os fingerprints são calculados, **Then** cada um desses três é independente dos demais.
4. **Given** uma regra de normalização é alterada, **When** a nova versão é aplicada, **Then** ela é identificada por uma versão distinta e não é comparada diretamente com fingerprints calculados por versões anteriores como se fossem equivalentes.

---

### User Story 4 - Equivalência exata e deduplicação segura de peças (Priority: P4)

Como operador de coleta, preciso que dois spec entries só sejam considerados equivalentes em peças quando a comparação for válida e exata, preservando integralmente a identidade e aplicabilidade originais de cada um — para que a deduplicação técnica nunca apague proveniência.

**Why this priority**: É o comportamento central de valor do projeto (evitar retrabalho de coleta sem perder identidade), mas depende das User Stories 1–3 já estarem em vigor.

**Independent Test**: Pode ser validado isoladamente usando os pares de evidência já documentados (ex.: `2HBC3X` ↔ `S1BC3X`) e verificando que o sistema reporta `parts_relation == EXACT` e mantém ambos como aplicações/origens distintas e consultáveis.

**Acceptance Scenarios**:

1. **Given** os pares de evidência documentados (`2HBC3X` ↔ `S1BC3X`; `S6BC74` ↔ `S7BC74`; `S7BC8A-62184` ↔ `AGDC8A-62169`), **When** a equivalência é avaliada, **Then** o sistema reporta `parts_relation == EXACT` para cada par e preserva a identidade original de ambos os lados.
2. **Given** dois spec entries cujo conteúdo de peças não é idêntico, **When** a equivalência é avaliada, **Then** eles não são tratados como equivalentes, mesmo que compartilhem outras semelhanças superficiais.
3. **Given** uma comparação entre dois spec entries não pode ser considerada válida (ex.: um deles está em snapshot INCOMPLETE ou INVALID), **When** a avaliação de equivalência é solicitada, **Then** a deduplicação não é aplicada.
4. **Given** um spec entry pertence a uma classe de equivalência com múltiplos membros, **When** um representante precisa ser escolhido, **Then** ele é selecionado deterministicamente pelos critérios, em ordem: snapshot válido, maior cobertura de imagens, catálogo mais atual, maior completude de metadados, chave estável como desempate — e os demais membros continuam existindo como aplicações/origens válidas.
5. **Given** códigos de geração observados (2H, S1, S6, S7, AGD), **When** a equivalência é avaliada, **Then** o sistema não assume automaticamente que representam gerações sequenciais.
6. **Given** atributos como body, engine, drivetrain, transmission, grade ou configuração não são comprovados pela fonte para um spec entry, **When** esse spec entry é processado, **Then** o sistema não infere esses atributos.

---

### User Story 5 - Fallback de imagem controlado dentro de equivalência comprovada (Priority: P5)

Como operador de coleta, preciso que a cobertura de imagens seja tratada de forma independente da equivalência de peças, e que uma imagem só seja reaproveitada entre spec entries dentro de uma classe de equivalência já comprovada, sempre preservando a origem real da imagem usada.

**Why this priority**: Refina a qualidade de dados (cobertura de imagem) sem comprometer a garantia de proveniência já estabelecida pelas histórias anteriores; depende da equivalência (User Story 4) já estar em vigor.

**Independent Test**: Pode ser validado isoladamente simulando um spec entry sem imagem própria dentro de uma classe de equivalência comprovada e verificando que a imagem de outro membro da classe é usada com a origem real registrada; e simulando uma tentativa de fallback entre specs sem equivalência comprovada, verificando que ela é recusada.

**Acceptance Scenarios**:

1. **Given** um spec entry sem imagem própria pertence a uma classe de equivalência comprovada (`parts_relation == EXACT`) que contém outro membro com imagem, **When** o fallback é aplicado, **Then** a imagem do outro membro é usada e sua origem real (spec entry de onde veio) é registrada e exposta.
2. **Given** dois spec entries cuja equivalência de peças não foi comprovada, **When** um fallback de imagem entre eles é tentado, **Then** ele não é permitido.
3. **Given** uma mudança ocorre apenas na cobertura de imagens de um spec entry, **When** o cluster de peças é reavaliado, **Then** essa mudança não altera a classe de equivalência de peças.

---

### User Story 6 - Snapshots auditáveis e revalidação incremental (Priority: P6)

Como operador de coleta, preciso que cada coleta completa aceita gere um snapshot imutável em um dos estados definidos, e que revalidações futuras possam ser feitas de forma incremental usando os fingerprints hierárquicos para localizar divergências.

**Why this priority**: Fecha o ciclo de auditabilidade e permite que o sistema evolua sem reprocessamento completo; depende de raw preservado (User Story 2) e fingerprints (User Story 3) já existirem.

**Independent Test**: Pode ser validado isoladamente gerando duas coletas sucessivas do mesmo spec entry (sem e com alteração de peças) e verificando que a segunda gera um novo snapshot em vez de sobrescrever o anterior, e que o estado (`VALID`/`INCOMPLETE`/`STALE`/`SUPERSEDED`/`INVALID`) é atribuído corretamente.

**Acceptance Scenarios**:

1. **Given** uma coleta completa de um spec entry é aceita, **When** o snapshot é gerado, **Then** ele é imutável e recebe um dos estados definidos: `VALID`, `INCOMPLETE`, `STALE`, `SUPERSEDED` ou `INVALID`.
2. **Given** um spec entry já possui um snapshot `VALID`, **When** ele é reprocessado, **Then** um novo snapshot é criado e o snapshot anterior não é sobrescrito silenciosamente.
3. **Given** um snapshot está em estado `INCOMPLETE` ou `INVALID`, **When** a avaliação de equivalência é executada, **Then** esse snapshot não participa da comparação.
4. **Given** o `spec_parts_hash` de um spec entry muda entre duas coletas, **When** a revalidação é executada, **Then** o spec entry passa a pertencer a outra classe de equivalência.
5. **Given** múltiplos spec entries já possuem fingerprints hierárquicos calculados, **When** uma revalidação incremental é solicitada, **Then** o sistema é capaz de localizar quais partes da hierarquia divergem sem reprocessar tudo do zero.

---

### User Story 7 - Coleta retomável/checkpointed (Priority: P7)

Como operador de coleta, preciso interromper e retomar uma execução de descoberta/coleta sem que o trabalho já validado seja refeito.

**Why this priority**: É uma capacidade operacional que aumenta a resiliência da coleta; tem valor mesmo isolada, mas naturalmente se apoia nas garantias de raw e snapshot já estabelecidas.

**Independent Test**: Pode ser validado isoladamente interrompendo uma execução após pelo menos um spec entry ser registrado com snapshot `VALID`, reiniciando a execução, e verificando que esse spec entry não é coletado novamente.

**Acceptance Scenarios**:

1. **Given** uma execução de coleta é interrompida após alguns spec entries já estarem em snapshot `VALID`, **When** a coleta é retomada, **Then** esses spec entries não são recoletados.
2. **Given** uma execução é retomada, **When** a coleta prossegue, **Then** ela continua a partir dos spec entries ainda não processados ou não validados.

---

### Edge Cases

- O que acontece quando um challenge (CAPTCHA/Cloudflare) bloqueia o acesso no meio de uma enumeração? → A situação é roteada para human-in-the-loop; a execução pode ser retomada depois que o acesso legítimo for restabelecido.
- O que acontece quando o DOM foi alterado por tradução automática do navegador? → O conteúdo é rejeitado como catálogo inválido, não é preservado como raw válido.
- O que acontece quando o mesmo `model_code` (ex.: `S7BC8A`) aparece com `amayama_catalog_id` diferentes? → Cada ocorrência é mantida como spec entry distinto.
- O que acontece quando dois spec entries têm peças idênticas mas cobertura de imagem diferente? → São tratados como equivalentes em peças; a diferença de imagem é tratada separadamente via fallback controlado.
- O que acontece quando um campo opcional (ex.: grade/configuração, ou um campo de peça como PR codes) está legitimamente ausente na fonte? → O campo é registrado como ausente, não como erro.
- O que acontece quando a comparação de equivalência entre dois spec entries é inválida ou incompleta? → A deduplicação não é aplicada; os spec entries permanecem distintos até uma revalidação válida.
- O que acontece quando um spec entry é reprocessado após uma mudança na fonte? → Um novo snapshot é gerado; o snapshot anterior válido não é sobrescrito.
- O que acontece quando há empate entre candidatos a representante de uma classe de equivalência? → O empate é resolvido pelos critérios determinísticos em ordem, terminando na chave estável.
- O que acontece se a coleta for interrompida por falha, perda de rede ou parada manual no meio do processamento? → Spec entries já registrados em snapshot válido não são reprocessados na retomada.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE descobrir/enumerar os spec entries do Volkswagen Amarok no mercado `AMA BR` da Amayama.
- **FR-002**: O sistema DEVE representar, para cada spec entry descoberto, sua posição na hierarquia modelo → mercado → spec entry → categoria → grupo → schema → OEM.
- **FR-003**: O sistema NÃO DEVE tratar `model_code` isoladamente como suficiente para identificar um spec entry.
- **FR-004**: O sistema DEVE registrar, para cada spec entry aceito, no mínimo: `market`, `model_code`, `amayama_catalog_id`, período de produção e `source_url` como campos distintos.
- **FR-005**: O sistema DEVE registrar grade/configuração de um spec entry somente quando comprovada pela fonte; a ausência não deve ser tratada como erro.
- **FR-006**: O sistema NÃO DEVE inferir atributos de body, engine, drivetrain, transmission, grade ou configuração que não sejam comprovados pela fonte.
- **FR-007**: O sistema NÃO DEVE tratar os códigos 2H, S1, S6, S7 e AGD como gerações sequenciais por padrão.
- **FR-008**: O sistema DEVE preservar o dado bruto coletado de um spec entry antes de qualquer adaptação, limpeza ou transformação.
- **FR-009**: O sistema DEVE gerar evidência suficiente para cada coleta aceita, de modo a permitir auditoria posterior do que foi capturado e quando.
- **FR-010**: O sistema DEVE detectar e rejeitar, como conteúdo de catálogo inválido, qualquer página afetada por CAPTCHA, challenge de Cloudflare (ou similar), HTML inválido/malformado, ou contaminação do DOM por tradução automática do navegador.
- **FR-011**: Quando um challenge impedir acesso legítimo, o sistema DEVE encaminhar a situação para um passo human-in-the-loop, em vez de tentar bypass automatizado.
- **FR-012**: O sistema DEVE suportar retomada de uma execução de coleta interrompida, sem recoletar spec entries já registrados em snapshot válido.
- **FR-013**: O sistema DEVE preservar, quando disponíveis na fonte, os seguintes campos por peça associada a um spec entry: `schema_id`, PNC/position, código OEM, descrição, detalhes, texto de período/aplicação, PR codes, quantidade e URL de imagem.
- **FR-014**: O sistema NÃO DEVE tratar a ausência legítima de um campo opcional de peça como erro obrigatório.
- **FR-015**: O sistema DEVE aplicar normalização determinística e versionada.
- **FR-016**: O sistema NÃO DEVE aplicar tradução, stemming, fuzzy matching, correção ortográfica ou substituição por sinônimos como parte da normalização usada para equivalência exata.
- **FR-017**: O sistema DEVE manter fingerprints independentes para conteúdo de peças, schema/conteúdo semântico e imagens.
- **FR-018**: O sistema NÃO DEVE considerar imagens na decisão de equivalência de peças.
- **FR-019**: O sistema DEVE considerar dois spec entries equivalentes para fins de deduplicação de peças somente quando a comparação for válida e `parts_relation == EXACT`.
- **FR-020**: O sistema NÃO DEVE usar geração de candidatos por heurística como prova de equivalência.
- **FR-021**: O sistema NÃO DEVE apagar ou ocultar a identidade, mercado ou aplicabilidade original de qualquer spec entry como resultado de deduplicação; spec entries não representantes DEVEM permanecer consultáveis como aplicações/origens válidas.
- **FR-022**: Quando múltiplos spec entries pertencerem à mesma classe de equivalência, o sistema DEVE selecionar um representante determinístico usando, em ordem: snapshot válido, maior cobertura de imagens, catálogo mais atual, maior completude de metadados e chave estável como desempate final.
- **FR-023**: O sistema DEVE permitir fallback de imagem entre spec entries somente quando a equivalência entre eles tiver sido comprovada como `EXACT` dentro de uma classe de equivalência válida.
- **FR-024**: O sistema DEVE preservar e expor a origem real (spec entry de origem) de qualquer imagem usada, inclusive quando usada via fallback.
- **FR-025**: O sistema NÃO DEVE atribuir silenciosamente uma imagem de um spec entry a outro sem registrar sua proveniência.
- **FR-026**: O sistema DEVE gerar um snapshot imutável para cada coleta completa aceita de um spec entry.
- **FR-027**: O sistema DEVE representar cada snapshot em um dos estados: `VALID`, `INCOMPLETE`, `STALE`, `SUPERSEDED` ou `INVALID`.
- **FR-028**: O sistema DEVE excluir snapshots em estado `INCOMPLETE` ou `INVALID` da avaliação de equivalência.
- **FR-029**: O sistema DEVE gerar um novo snapshot ao reprocessar um spec entry, em vez de sobrescrever silenciosamente um snapshot válido anterior.
- **FR-030**: Uma mudança limitada a dados de imagem NÃO DEVE alterar a classe de equivalência de peças de um spec entry.
- **FR-031**: Uma mudança no conteúdo de peças de um spec entry DEVE movê-lo para outra classe de equivalência quando o `spec_parts_hash` mudar.
- **FR-032**: O sistema DEVE suportar revalidação incremental capaz de usar fingerprints hierárquicos para localizar divergências, sem exigir reprocessamento completo.
- **FR-033**: O sistema DEVE produzir sua saída como uma representação de domínio interna que preserve toda a identidade, hierarquia e proveniência exigidas por esta especificação, sem acoplamento a um schema de exportação externo específico (ex.: Hubbi).
- **FR-034**: O núcleo funcional desta feature (descoberta/identidade, preservação de raw, normalização, fingerprints, equivalência, imagens, snapshots) DEVE operar recebendo HTML/raw já adquirido como entrada, permanecendo independente de qual mecanismo de aquisição (manual/browser-in-the-loop ou, futuramente, transporte automatizado) forneceu esse HTML/raw.

### Key Entities *(include if feature involves data)*

- **Model**: Representa o modelo de veículo em escopo nesta feature (Volkswagen Amarok). Atributo-chave: identificador/nome do modelo.
- **Market**: Representa o mercado da Amayama em escopo (`AMA BR`). Relaciona-se a um Model para formar o contexto de descoberta.
- **Spec Entry (Catalog Entry)**: A unidade de catálogo descoberta para um Model em um Market. Atributos-chave: `market`, `model_code`, `amayama_catalog_id`, período de produção, grade/configuração (quando comprovada), `source_url`. Não é identificada unicamente por `model_code` isolado.
- **Category / Group**: Níveis intermediários da hierarquia de catálogo entre spec entry e schema, conforme documentado na Constitution.
- **Schema**: Nível da hierarquia associado ao conjunto semântico/estrutural de peças de um spec entry; possui fingerprint próprio, independente do fingerprint de peças e de imagens.
- **OEM Reference**: Nível da hierarquia que referencia a origem/fabricante associada ao schema/peça, conforme a hierarquia definida pela Constitution.
- **Part**: Peça associada a um spec entry via schema. Atributos conhecidos como relevantes, quando disponíveis: `schema_id`, PNC/position, código OEM, descrição, detalhes, texto de período/aplicação, PR codes, quantidade, URL de imagem.
- **Image**: Recurso visual associado a uma peça ou spec entry. Possui fingerprint independente do conteúdo de peças; sua cobertura é tratada separadamente da equivalência de peças; mantém referência à sua origem real.
- **Raw Snapshot**: Registro imutável de uma coleta completa aceita de um spec entry, em um dos estados `VALID`/`INCOMPLETE`/`STALE`/`SUPERSEDED`/`INVALID`. Reprocessamento gera um novo Raw Snapshot, nunca sobrescreve um existente.
- **Equivalence Class**: Agrupamento determinístico de spec entries cujo conteúdo de peças foi comprovado como `EXACT` (dado escopo + versão de fingerprint + `spec_parts_hash`). Possui um representante selecionado deterministicamente; os demais membros permanecem como aplicações/origens válidas.
- **Checkpoint / Resume State**: Registro do progresso de uma execução de coleta que permite retomar sem reprocessar spec entries já validados.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Todo spec entry aceito para o Amarok no mercado `AMA BR` retém, no mínimo, `market`, `model_code`, `amayama_catalog_id`, período de produção e `source_url` como campos distintos e individualmente inspecionáveis.
- **SC-002**: Nenhum par de spec entries com `amayama_catalog_id` diferentes é fundido ou representado como uma única identidade, mesmo quando o conteúdo de peças é idêntico.
- **SC-003**: Páginas com CAPTCHA, challenge de Cloudflare, HTML inválido ou contaminação por tradução automática nunca são persistidas como conteúdo de catálogo válido; cada ocorrência é registrada e encaminhada para human-in-the-loop.
- **SC-004**: Uma execução de coleta interrompida após pelo menos um spec entry alcançar snapshot `VALID` pode ser retomada sem recoletar esse spec entry.
- **SC-005**: Para os três pares de evidência documentados (`2HBC3X` ↔ `S1BC3X`; `S6BC74` ↔ `S7BC74`; `S7BC8A-62184` ↔ `AGDC8A-62169`), a avaliação de equivalência do sistema reporta `parts_relation == EXACT` e preserva ambas as identidades originais como aplicações/origens distintas.
- **SC-006**: Valores distintos de `amayama_catalog_id` observados para o mesmo `model_code` (ex.: `S7BC8A`) são mantidos como spec entries separados, nunca colapsados em um só.
- **SC-007**: Fallback de imagem nunca é aplicado entre dois spec entries cuja equivalência não tenha sido estabelecida como `EXACT`; toda imagem usada registra seu spec entry de origem real.
- **SC-008**: Toda coleta aceita produz exatamente um snapshot imutável em um estado definido; reprocessar o mesmo spec entry produz um novo snapshot em vez de sobrescrever o anterior.
- **SC-009**: Uma mudança isolada na cobertura de imagens de um spec entry nunca altera sua classe de equivalência de peças; uma mudança no `spec_parts_hash` sempre move o spec entry para outra classe.

## Decisions

- **DEC-001 — Mecanismo de aquisição de HTML bruto (aprovado pelo PO em 2026-08-25)**: Para a feature `001-amarok-ama-br-ingestion`, o HTML bruto de origem pode ser fornecido por aquisição manual/browser-in-the-loop (conforme Constitution §5 — "o navegador pode ser usado como transporte validado"). Esta é uma decisão de produto aprovada, não mais uma suposição de trabalho. Regras associadas, também aprovadas:
  - Selenium/CDP automatizado continua fora do escopo desta feature (ver "Out of Scope").
  - Automação de transporte será especificada separadamente, em uma feature futura.
  - O núcleo funcional desta feature (descoberta/identidade, raw, normalização, fingerprints, equivalência, imagens, snapshots — ver FR-034) permanece independente de como o HTML/raw foi adquirido.
  - Human-in-the-loop continua permitido e é o único caminho aceito diante de challenge (FR-011).
  - Nenhum bypass de CAPTCHA/Cloudflare é permitido, sob nenhuma circunstância (FR-010, FR-011).

## Assumptions

- O "operador" desta feature é um usuário interno da equipe de coleta (Hubbi/PO/Claude/Codex/Antigravity), não um usuário final do produto Hubbi — não há interface gráfica nem API pública nesta feature.
- A saída desta feature é um modelo de domínio interno (representação estruturada), não persistida em um banco de dados concreto nem exposta via CLI ou API — ambos explicitamente fora de escopo desta feature.
- A granularidade exata do checkpoint (por spec entry, por página, ou outra unidade) e os limiares concretos de política de freshness (quando um snapshot se torna `STALE`) são decisões de implementação a serem definidas em PLAN/TASKS; esta especificação exige apenas que a capacidade de retomada e a configurabilidade da política de freshness existam.
- `AMA BR` é o identificador de mercado já validado por evidência externa consolidada (conforme Constitution §2), usado como dado de entrada desta feature — sua descoberta/validação não faz parte do escopo desta feature.
- Os três pares de evidência documentados (`2HBC3X`↔`S1BC3X`, `S6BC74`↔`S7BC74`, `S7BC8A-62184`↔`AGDC8A-62169`) são usados como casos de referência para validar o comportamento de equivalência; eles não implicam que todo par de spec entries do Amarok será equivalente, nem que 2H/S1/S6/S7/AGD formam uma sequência de gerações.

## Out of Scope

- Todos os demais modelos Volkswagen além do Amarok.
- Generalização automática do comportamento de equivalência/identidade para outras montadoras.
- Integração produtiva com o ecossistema Hubbi (apenas uma saída interna adaptável é exigida, sem acoplamento).
- Bypass automatizado de Cloudflare/CAPTCHA sob qualquer circunstância.
- Implementação do transporte de automação (Selenium/CDP).
- Escolha ou implementação de um banco de dados concreto.
- Infraestrutura de produção (deploy, orquestração, monitoramento operacional).
- Interface gráfica.
- API pública.
- Tratar 2H, S1, S6, S7 e AGD como sequência automática de gerações.
- Inferência de body, engine, drivetrain, transmission, grade ou configuração não comprovados pela fonte.
