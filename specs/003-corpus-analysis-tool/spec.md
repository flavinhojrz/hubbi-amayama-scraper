# Feature Specification: Ferramenta de Análise do Corpus Coletado

**Feature Branch**: `003-corpus-analysis-tool`

**Created**: 2026-09-01

**Status**: Aprovado pelo PO diretamente nesta conversa (Flávio) — registrado aqui para rastreabilidade conforme Constitution §16, sem passar pelos gates intermediários de `/speckit-clarify`/aprovações sequenciais por artefato.

**Input**: Pedido direto do Product Owner nesta conversa: transformar as análises/auditorias hoje feitas manualmente com SQL sobre `amayama.db` em uma ferramenta versionada, reproduzível e testada dentro do projeto, cobrindo resumo geral, qualidade da coleta, redundância entre specs (via fingerprints já existentes) e comparação detalhada entre duas specs — com saída humana e JSON, determinística, sem pandas, sem alterar dados.

## Contexto confirmado do dataset (na data desta spec)

- Banco: `amayama.db` (SQLite). Escopo atual: `VOLKSWAGEN / AMAROK / AMA-BR`.
- 242 specs em `spec_registry` para esse escopo; 242 `spec_snapshot` com `state=VALID` e `collection_complete=1`.
- Totais (soma por spec, a partir de `spec_snapshot.counts_json`): 7.769 grupos, 27.909 schemas, 415.758 ocorrências de peças.
- `2HBC34` (catálogo `56058`) é uma spec legítima com 1 grupo, 1 schema, 0 peças — a tabela OEM está genuinamente vazia no HTML bruto (confirmado por inspeção manual). Zero peças não é, por si só, erro.
- Fingerprints já persistidos por snapshot: `structure_hash`, `spec_parts_hash`, `schema_semantic_hash`, `image_hash`, todos independentes (Constitution §8).

## Restrição de dados descoberta durante a inspeção arquitetural (não é ambiguidade — é fato de schema)

Não existe tabela relacional de Category/Group/Schema/Part — apenas os totais agregados em `spec_snapshot.counts_json` e a árvore de grupos esperados em `spec_group_manifest.categories_json`. Comparação de OEM/peças individuais entre duas specs exigiria reprocessar o HTML bruto (`raw_capture`/`raw_blob`) pelo pipeline de parsing — isso está fora do escopo desta ferramenta (ver "Fora de escopo"). O próprio pedido do PO já previa essa condição ("quando a camada atual permitir, diferença de OEMs/peças"): a camada atual não permite via SQL, então a comparação D reporta isso explicitamente como indisponível, e usa `spec_group_manifest` (grupos, não peças) para o diff de grupos exclusivos/compartilhados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Resumo geral de um escopo (Priority: P1)

Como operador/PO, preciso ver, para um escopo (`manufacturer`/`vehicle_model`/`market`), quantas specs foram descobertas, quantas estão `VALID`+completas, quantas são incompletas/problemáticas, os totais de categorias/grupos/schemas/peças, quantas specs têm zero peças, e a distribuição (mín/máx/média/mediana) de grupos/schemas/peças por spec — sem escrever SQL manualmente.

**Independent Test**: rodar o resumo sobre uma fixture SQLite pequena e determinística com specs conhecidas e conferir cada número reportado contra o valor calculado manualmente a partir das linhas inseridas.

**Acceptance Scenarios**:
1. **Given** um escopo com specs cujo snapshot mais recente é `VALID`+completo, **When** o resumo é gerado, **Then** os totais e a distribuição batem exatamente com os `counts_json` das specs consideradas.
2. **Given** uma spec sem nenhum snapshot, **When** o resumo é gerado, **Then** ela conta em `specs_discovered` e em `specs_incomplete_or_problematic`, mas é excluída do cálculo de distribuição (min/máx/média/mediana), que é calculado apenas sobre specs com pelo menos um snapshot.
3. **Given** um escopo sem nenhuma spec (escopo inexistente) ou um banco vazio, **When** o resumo é gerado, **Then** a ferramenta retorna contagens zeradas e distribuições vazias (sem exceção, sem divisão por zero).

---

### User Story 2 — Qualidade da coleta (Priority: P2)

Como operador/PO, preciso que a ferramenta aponte, com severidade e motivo explícito, problemas de coleta: spec sem snapshot atual, snapshot não `VALID`, `collection_complete != 1`, manifest ausente/incompleto, divergência entre grupos do manifest e do snapshot, grupos esperados nunca `ACCEPTED` (quando houver manifest+checkpoint suficientes para comparar), snapshots suspeitos com zero categorias/grupos/schemas, e specs com zero peças reportadas apenas como informação (nunca como erro automático).

**Independent Test**: fixtures cobrindo cada condição isoladamente (corpus saudável / manifest divergente / snapshot incompleto / spec com zero peças legítima) e verificar que exatamente os achados esperados aparecem, com a severidade esperada.

**Acceptance Scenarios**:
1. **Given** um corpus totalmente saudável (todas as specs `VALID`+completas, manifest presente e batendo com o snapshot, todos os grupos esperados `ACCEPTED`), **When** a auditoria de qualidade roda, **Then** nenhum achado de severidade `ERROR`/`WARNING` é produzido.
2. **Given** uma spec cujo manifest lista mais grupos do que `counts_json.groups` do snapshot mais recente, **When** a auditoria roda, **Then** um achado de divergência é produzido citando os dois números.
3. **Given** uma spec cujo snapshot mais recente tem `collection_complete=0` ou `state != VALID`, **When** a auditoria roda, **Then** um achado correspondente é produzido com a severidade apropriada.
4. **Given** uma spec com snapshot `VALID`+completo e `counts_json.parts == 0` (caso `2HBC34`), **When** a auditoria roda, **Then** um achado de severidade `INFO` é produzido (nunca `ERROR`/`WARNING` só por isso).

---

### User Story 3 — Redundância via fingerprints (Priority: P3)

Como operador/PO, preciso saber quantos `spec_parts_hash`/`structure_hash`/`schema_semantic_hash`/`image_hash` distintos existem no escopo, quais specs formam clusters de `spec_parts_hash` idêntico (reaproveitando a chave normativa de `equivalence/cluster.py::cluster_key()`, Constitution §9), o tamanho de cada cluster, quantas specs são isoladas, o maior cluster, e a taxa de redução potencial — sem que isso implique qualquer fusão real de specs.

**Independent Test**: fixture com specs conhecidas de `spec_parts_hash` repetido e únicos; conferir que os clusters e a contagem de distintos batem exatamente.

**Acceptance Scenarios**:
1. **Given** duas specs com `spec_parts_hash` idêntico (mesma `normalizer_version`/`fingerprint_version`) e uma terceira com hash distinto, **When** a análise de redundância roda, **Then** um cluster de tamanho 2 e uma spec isolada são reportados, e a taxa de redução reflete `(specs_considerados - hashes_distintos) / specs_considerados`.
2. **Given** uma spec com snapshot `INCOMPLETE`/`INVALID`, **When** a análise de redundância roda, **Then** essa spec é excluída do cálculo (Constitution §11 — `INCOMPLETE`/`INVALID` não participam de equivalência).

---

### User Story 4 — Comparação detalhada entre duas specs (Priority: P4)

Como operador/PO, preciso comparar duas specs específicas e ver metadados, contagens, quais dos 4 hashes são iguais/diferentes, grupos exclusivos de cada lado e grupos compartilhados (via manifest) — reaproveitando `equivalence/evaluate.py` para a relação de peças/schema/imagem, nunca reimplementando comparação de hash.

**Independent Test**: fixture com duas specs conhecidas (uma via evidência já documentada em `001`, ex. par `EXACT`) e conferir que a saída da comparação bate com o resultado esperado de `evaluate_equivalence()`.

**Acceptance Scenarios**:
1. **Given** duas specs com snapshot `VALID`+completo e mesmo `spec_parts_hash`, **When** comparadas, **Then** a saída reporta `parts_relation=EXACT` e preserva identidade/metadados de ambas.
2. **Given** duas specs com manifest disponível, **When** comparadas, **Then** os grupos exclusivos de cada lado e os compartilhados são listados corretamente a partir de `spec_group_manifest`.
3. **Given** uma das duas specs sem snapshot, **When** comparadas, **Then** a comparação de hashes é reportada como indisponível (não uma exceção), e os campos de metadados/contagens disponíveis ainda aparecem.

---

## Requisitos funcionais

- **FR-001**: A ferramenta deve expor resumo geral (US1), qualidade (US2), redundância (US3) e comparação (US4) sem exigir SQL manual do operador.
- **FR-002**: Toda saída deve estar disponível em texto legível e em JSON estruturado, ambos determinísticos para a mesma base (mesma ordenação, sem depender de iteração não ordenada de dict/set).
- **FR-003**: A ferramenta nunca escreve no banco — apenas leitura (conexão somente-leitura quando o arquivo existir; nunca cria o arquivo).
- **FR-004**: A ferramenta reaproveita `equivalence/cluster.py::cluster_key()` e `equivalence/evaluate.py` para qualquer lógica de hash/equivalência — não reimplementa comparação de fingerprint.
- **FR-005**: Specs com zero peças nunca são classificadas automaticamente como erro — apenas relatadas como informação (Constitution, contexto `2HBC34`).
- **FR-006**: `INCOMPLETE`/`INVALID` nunca participam do cálculo de redundância/equivalência (Constitution §11).
- **FR-007**: A ferramenta não modifica `cluster_assignment`, não persiste nenhuma decisão de deduplicação, e não funde/apaga specs — é somente informativa (Constitution §3/§9).
- **FR-008**: Toda regra estrutural nova (US1–US4, classificação de severidade) deve ter teste automatizado (Constitution §12; Execution Policy "Política de testes").
- **FR-009**: A ferramenta não depende de `pandas` nem de nenhuma dependência nova além do que já está em `pyproject.toml`.

## Fora de escopo

- Diff de OEMs/peças individuais entre duas specs (exigiria reprocessar raw HTML — não é uma leitura SQL; ver seção "Restrição de dados" acima). Reportado explicitamente como indisponível na saída de comparação, não omitido silenciosamente.
- Qualquer fusão, deduplicação real ou alteração de `cluster_assignment`/specs a partir dos achados de redundância.
- Alterar `cli/main.py`/`cli/options.py` (pertencem à feature `002-amarok-ama-br-browser-scraper`, em implementação não commitada nesta mesma branch) — a ferramenta de análise ganha seu próprio entrypoint (`cli/analyze.py`) para não interferir no trabalho em andamento de outra feature.

## Decisões registradas

- **DEC-001**: Fluxo SDD completo (spec → PO approval → plan → PO approval → tasks → PO approval → implementa) foi explicitamente comprimido pelo PO nesta conversa — aprovação única cobrindo os três artefatos e autorizando implementação direta, mantendo o registro para rastreabilidade (Constitution §16).
- **DEC-002**: "Categorias/grupos/schemas/peças" no resumo geral (US1) são somas por spec (`counts_json`), não contagens de valores distintos — mesma metodologia usada para conferir os totais já confirmados pelo PO (7.769 grupos / 27.909 schemas / 415.758 peças).
- **DEC-003**: Distribuições (mín/máx/média/mediana) de grupos/schemas/peças por spec são calculadas apenas sobre specs com pelo menos um snapshot — specs sem nenhum snapshot entram nas contagens de descoberta/problema, mas não distorcem a distribuição com um "0" que não é comparável a um catálogo genuinamente vazio.
- **DEC-004**: Diff de grupos (US4) usa `spec_group_manifest` (grupos esperados), não uma reconstrução de árvore de domínio — o manifest mais recente com `manifest_complete=True` de cada spec é a fonte usada.
