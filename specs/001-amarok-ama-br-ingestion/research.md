# Phase 0 Research: MVP de Ingestão Amayama — Volkswagen Amarok (Mercado AMA BR)

**Feature**: `001-amarok-ama-br-ingestion` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)

Cada decisão abaixo segue o formato Decision / Rationale / Alternatives considered. Todas as decisões são de nível PLAN (técnicas, HOW) — nenhuma altera requisito, escopo, critério de equivalência, identidade ou comportamento observável definido em `spec.md`.

---

## 1. Linguagem e versão mínima

**Decision**: Python ≥ 3.11 como versão mínima suportada; desenvolvimento/CI em 3.12.

**Rationale**: O `.gitignore` já commitado no bootstrap do projeto (`chore: bootstrap SDD governance`) já antecipa um projeto Python (`.venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`) — evidência factual já existente no repositório, não uma suposição nova. Python oferece o ecossistema mais maduro para scraping/parsing HTML, tipagem gradual robusta (`dataclasses`, `typing`), e é a linguagem natural para um data pipeline determinístico e testável offline. A versão 3.11 é o piso mínimo por trazer `typing.Self`, grupos de exceção (`ExceptionGroup`) úteis para agregar erros de parsing por grupo/spec sem abortar a coleta inteira, e `dataclasses(slots=True)` (disponível desde 3.10) para modelos de domínio leves e imutáveis.

**Alternatives considered**: TypeScript/Node (ecossistema de scraping forte, mas menor maturidade em tipagem estrutural de dados de domínio complexos e em bibliotecas de hashing canônico); Rust (determinismo e performance excelentes, mas custo de desenvolvimento/iteração alto para um MVP e menor familiaridade esperada da equipe). Nenhuma das alternativas está sinalizada como preferência do projeto; Python é a escolha padrão justificada pelo contexto e pelo próprio bootstrap já existente.

---

## 2. Empacotamento

**Decision**: `pyproject.toml` (PEP 621) com `hatchling` como build backend, layout `src/`.

**Rationale**: `hatchling` é um backend moderno, sem plugins nem configuração cerimonial, adequado para um pacote Python puro (sem extensões compiladas). O layout `src/` evita que o pacote seja importado acidentalmente a partir do diretório de testes/raiz sem instalação, reforçando baixo acoplamento e reprodutibilidade dos testes.

**Alternatives considered**: `setuptools` clássico (mais verboso, `setup.py`/`setup.cfg` desnecessários para este escopo); `poetry` (gerenciador de dependências completo, mas adiciona um lockfile/ferramenta própria não estritamente necessária para um único pacote interno sem publicação em PyPI).

---

## 3. Validação e tipagem

**Decision**: `dataclasses(frozen=True, slots=True)` para os modelos de domínio (identidade, hierarquia, peça, snapshot, fingerprint), com validação explícita em `__post_init__` (funções puras, sem framework), e `mypy --strict` para checagem estática.

**Rationale**: Modelos imutáveis (`frozen=True`) refletem diretamente a exigência da Constitution de que snapshots aceitos sejam imutáveis e de que o núcleo seja determinístico. `slots=True` reduz overhead de memória (relevante para coleções grandes de peças) e prova de tipagem. Validação explícita em funções/`__post_init__` mantém o domínio livre de acoplamento a um framework de validação externo — alinhado a "baixo acoplamento" e evita que uma biblioteca de terceiros dite a forma como o domínio é modelado.

**Alternatives considered**: `pydantic` v2 (validação rica e rápida, mas acopla o núcleo de domínio a um framework externo com opiniões próprias sobre serialização/coerção de tipos, o que conflita com a exigência de serialização canônica própria para fingerprints); `attrs` (similar a `dataclasses`, sem vantagem clara sobre a stdlib para este escopo).

---

## 4. Parser HTML

**Decision**: `BeautifulSoup4` com o parser `lxml` como backend.

**Rationale**: Tolerante a HTML malformado/real-world (importante pois o parser precisa **detectar** drift estrutural explicitamente em vez de falhar de forma ambígua — FR-010, ponto 20 do PLAN), API estável e amplamente documentada (facilita revisão pelo Codex e QA exploratório do Antigravity), suporte nativo a seletores CSS (`select`/`select_one`) compatível 1:1 com os seletores já pesquisados (`.epcVariation__details`, `.epcSchema__schemas`, etc.). Não há requisito de performance/throughput no `spec.md` que justifique otimizar por velocidade de parsing.

**Alternatives considered**: `selectolax` (mais rápido e leve, engine Modest/Lexbor, mas ecossistema menor e menos legível para revisão de contratos de parsing); `lxml.html` puro + `cssselect` (mais rápido que bs4, mas API menos ergonômica para diferenciar "campo ausente" de "estrutura inesperada", que é um requisito explícito do ponto 7 do PLAN).

---

## 5. Testes

**Decision**: `pytest` + `pytest-cov` (cobertura), sem plugins de snapshot testing (ex.: `syrupy`).

**Rationale**: `pytest` é o padrão de fato para Python, com suporte robusto a fixtures parametrizadas (necessário para os fixtures de HTML descritos no ponto 24). Snapshot testing automático foi deliberadamente evitado: fixtures de HTML e resultados esperados devem ser explícitos e revisáveis por humanos/Codex, não gerados/aceitos automaticamente — alinhado à exigência de auditabilidade e de tratar bugs de revisão como casos de regressão explícitos (Constitution §12).

**Alternatives considered**: `unittest` da stdlib (viável, mas com fixtures/parametrização mais verbosas); `syrupy`/snapshot testing (rejeitado pelo motivo acima).

---

## 6. Lint/format e tipagem estática

**Decision**: `ruff` para lint + format (substitui flake8/isort/black), `mypy --strict` para tipagem.

**Rationale**: Ferramenta única e rápida, já antecipada pelo `.gitignore` do bootstrap (`.ruff_cache/`). `mypy --strict` reforça o requisito de tipagem forte do domínio, pego cedo em CI, sem depender de testes para capturar erros de forma.

**Alternatives considered**: `flake8` + `black` + `isort` separados (mais peças móveis, mesmo resultado prático); `pyright` (bom, mas `mypy` é o padrão mais amplamente adotado em pipelines Python server-side/CI).

---

## 7. Serialização canônica

**Decision**: `json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))` sobre uma estrutura já normalizada (NFKC aplicado antes da serialização), codificada em UTF-8 para hashing.

**Rationale**: JSON textual mantém a saída **inspecionável** (prioridade explícita da feature), ao custo de nenhuma ambiguidade de determinismo: `sort_keys=True` remove dependência de ordem de inserção, `ensure_ascii=True` remove qualquer variação de representação de caracteres não-ASCII entre plataformas/versões do Python (a normalização NFKC já ocorre antes; a serialização apenas fixa a forma de escape), `separators` compactos removem variação de espaçamento.

**Alternatives considered**: MessagePack/Protobuf (determinismo binário igualmente possível, mas perdem a inspecionabilidade humana do conteúdo canônico usado para hashing, o que conflita com a prioridade explícita "facilidade de inspeção de raw data" da feature); `ensure_ascii=False` (rejeitado por introduzir dependência da normalização Unicode do ambiente de execução na serialização, mesmo que NFKC já tenha sido aplicado antes — `ensure_ascii=True` é uma garantia adicional e barata).

---

## 8. Persistência — DEC-002 (aprovado pelo PO)

**Status**: esta seção documentava anteriormente uma *reconciliação de leitura* entre o "Out of Scope" do `spec.md` e a necessidade de persistência interna do PLAN. O PO aprovou explicitamente, em 2026-08-25, **DEC-002 — Persistência interna do MVP** (ver `spec.md` §Decisions), que corrige diretamente essa contradição. Esta seção não é mais uma interpretação — é a materialização técnica de uma decisão de produto já aprovada.

**Decision**: SQLite (via `sqlite3` da stdlib, sem ORM) para metadados/estado (`spec_registry`, `collection_run`, `spec_snapshot`, `fingerprint_set`, `current_spec_state`, `cluster_assignment`, `asset_resolution`, `checkpoint` — este último agora hierárquico, ver §9); armazenamento de conteúdo endereçado por conteúdo (content-addressed) em filesystem para HTML bruto e imagens.

**Regra explícita (DEC-002 + item 5 da correção do PO)**: SQLite armazena **referências/hashes** para o raw (ex.: `content_hash`, caminho relativo no armazenamento content-addressed, tamanho em bytes), **não** os blobs de HTML/imagem em si — esses permanecem exclusivamente no filesystem content-addressed. Isso mantém o banco de metadados pequeno, rápido de indexar/consultar, e preserva a separação entre "onde está o dado" (filesystem, imutável, deduplicado por conteúdo) e "o que sabemos sobre o dado" (SQLite, estado/relações).

**Propriedades garantidas por este desenho**:
- Raw imutável: o path no filesystem é derivado de `sha256(raw_bytes)`; o mesmo conteúdo sempre resolve ao mesmo path, e nada no pipeline sobrescreve um arquivo já existente nesse path.
- Deduplicação física segura por conteúdo: uma captura repetida do mesmo HTML byte-a-byte resolve ao mesmo `content_hash`/path — nenhuma cópia duplicada é gravada, sem exigir lógica adicional de deduplicação.
- Metadados auditáveis: cada linha de metadado em SQLite referencia um `content_hash` verificável contra o arquivo real.
- Last-known-good preservado: nenhuma operação de escrita em SQLite ou no filesystem apaga ou sobrescreve um `SpecSnapshot` `VALID` existente (ver `contracts/snapshot-contract.md`) — uma nova captura malsucedida não afeta o estado anterior.
- Isolamento para troca futura: `persistence/` é o único módulo com conhecimento de SQL; nenhum outro módulo (domínio, equivalência, fingerprints, etc.) importa `sqlite3` ou monta queries — apenas consome interfaces/repositórios tipados.

**Rationale**: Escopo de operação de um único operador/processo por vez (sem requisito de concorrência multi-writer no `spec.md`); zero-ops (arquivo único, sem servidor); trivialmente inspecionável e versionável (auditabilidade, "facilidade de inspeção de raw data"); testável em memória (`sqlite3.connect(":memory:")`) ou arquivo temporário sem infraestrutura externa, mantendo o núcleo testável 100% offline (Constitution §12).

**Alternatives considered**: PostgreSQL — **não projetado nesta PLAN** (por instrução explícita do PO); registrado aqui apenas como fronteira de evolução possível, não como decisão a detalhar agora: se acesso concorrente multi-processo/multi-operador se tornar um requisito futuro, a migração é possível porque `persistence/` já isola todo o acesso a dados por trás de interfaces/repositórios independentes de SQL concreto — nenhuma mudança seria necessária em `domain/`, `equivalence/`, `fingerprints/`, `snapshots/`, etc. Banco orientado a documentos (ex. arquivos JSON soltos) para todo o estado — rejeitado: perde garantias transacionais simples que SQLite oferece de graça, como a atomicidade de "gerar snapshot + atualizar `current_spec_state`".

**Fora de escopo, reafirmado por DEC-002**: banco externo/produtivo, infraestrutura de banco de produção, e integração da persistência com o ecossistema Hubbi.

**Nota de idempotência**: "SQLite oferece atomicidade de graça" acima refere-se a uma única transação; isso por si só **não** garante idempotência entre múltiplas transações/retries — esse mecanismo adicional (chave única + upsert + `idempotency_key`) é detalhado em §15.

---

## 9. Granularidade de checkpoint (revisado — decisão técnica do PO)

**Status**: decisão anterior (checkpoint apenas por spec entry) foi substituída por instrução técnica explícita do PO. Este PLAN agora adota checkpoint **hierárquico**, com progresso mínimo rastreável por **group**.

**Decision**: hierarquia de checkpoint:

```
Collection Run
  ↓
Spec Entry
  ↓
Category
  ↓
Group   ← unidade mínima de progresso retomável
```

- **Spec entry** continua sendo a unidade lógica do `SpecSnapshot` final (o snapshot é gerado e avaliado por spec entry, não por group individualmente).
- **Group** é a unidade mínima de progresso retomável: cada `Group` descoberto para uma spec entry tem seu próprio registro de checkpoint (`CheckpointEntry` — ver `data-model.md` §11), com status independente.
- **Category** é usada como agrupamento/índice de `group_id` (evita colisão de `group_id` entre categorias distintas — consistente com a invariante de `group_id` duplicado *dentro do mesmo escopo* já definida em `data-model.md` §2), mas não é, em si, uma unidade de checkpoint com status próprio — o rastreamento individual acontece no nível de `Group`.
- Um `Group` com checkpoint `ACCEPTED` e persistido não precisa ser recoletado/reprocessado após uma interrupção.
- `CHALLENGE`, `CAPTCHA`/Cloudflare, captura `INVALID` ou `INCOMPLETE` **nunca** marcam um `Group` como `ACCEPTED` (consistente com `contracts/input-contracts.md` §2 — challenge nunca é tratado como conteúdo vazio válido).
- Checkpoint `ACCEPTED` de todos os `Group`s de uma spec entry é uma **precondição necessária, mas não suficiente por si só**, para que o `SpecSnapshot` correspondente alcance `state = VALID`: a avaliação de completude do snapshot (`collection_complete`) consulta o estado agregado dos checkpoints daquela spec entry — ver `contracts/snapshot-contract.md` (atualizado).
- Retomada de uma run continua exatamente a partir dos `Group`s ainda `PENDING`/`IN_PROGRESS`/`REJECTED` (não `ACCEPTED`) — nunca reprocessa um `Group` já `ACCEPTED` na mesma run.
- **Idempotência real** (correção — ver §15): content-addressing do raw (§8) por si só **não** é suficiente para garantir idempotência de checkpoint/snapshot — ele apenas deduplica bytes físicos, não impede duas linhas de checkpoint para a mesma unidade lógica, transições concorrentes/repetidas para `ACCEPTED`, ou snapshots duplicados por retry. A garantia real vem da chave única `(run_id, spec_key, category_slug, group_id)` em `CheckpointEntry` combinada com upsert transacional, e de um `idempotency_key` dedicado em `SpecSnapshot` — ver §15 para o mecanismo completo.

**Rationale**: A estrutura real da fonte (seletores já pesquisados em `contracts/domain-contracts.md`) mostra que uma página de spec entry pode conter múltiplos `Group`s dentro de múltiplos `Category`s (`.epcSchema__schemas` com múltiplos `.epcSchema__schema[data-id]`, tabelas com múltiplos `.entriesPncTable__groupHeader`). Mesmo com aquisição manual/browser-in-the-loop (DEC-001) — tipicamente uma captura por página —, o *processamento* de uma spec entry com muitos grupos pode ser interrompido no meio (falha do processo, não da captura em si). Checkpoint apenas por spec entry perderia todo o progresso de parsing/persistência já feito para os grupos processados com sucesso antes da interrupção. Granularidade por `Group` resolve isso sem exigir que a aquisição em si seja fatiada por grupo — `CheckpointEntry.raw_capture_id` pode (e tipicamente vai, neste MVP) referenciar a mesma captura para múltiplos `Group`s de uma mesma spec entry.

**Alternatives considered**: granularidade só por spec entry (decisão anterior — rejeitada por perder progresso intra-spec-entry em caso de interrupção durante o processamento de uma spec entry com muitos grupos); granularidade por category (rejeitada como unidade *de status* própria — grossa demais para o objetivo de "não recolocar trabalho já aceito", já que uma categoria pode conter muitos grupos; mantida apenas como campo de indexação/agrupamento, não como status independente); granularidade por peça individual (rejeitada por granularidade excessiva sem benefício adicional — peças de um mesmo grupo são sempre processadas e persistidas juntas como parte da aceitação do grupo).

---

## 10. Chave estável (`stable_key`) — endurecida (correção do PO)

**Status**: a decisão anterior (`stable_key` como string delimitada por `:`, usada como única representação da identidade) foi substituída por instrução explícita do PO — o formato anterior não é mais o contrato válido isoladamente.

**Decision**: a identidade normativa de uma `SpecIdentity` é a **tupla explícita de seis campos** — `(source, manufacturer, vehicle_model, market, model_code, amayama_catalog_id)` — cada um mantido como campo individual em `SpecIdentity` (nunca apenas embutido em uma string). `stable_key` é uma **representação derivada e determinística** dessa tupla, calculada como um hash — não uma string delimitada interpretável:

```
stable_key = SHA256_hex("amayama:spec-identity:v1\0" + canonical_json({
  "source": <normalizado: strip+upper>,
  "manufacturer": <normalizado: strip+upper>,
  "vehicle_model": <normalizado: strip+upper>,
  "market": <normalizado: strip+upper>,
  "model_code": <normalizado: strip+upper>,
  "amayama_catalog_id": <normalizado: strip+upper>
}))
```

Nesta feature, os valores esperados são constantes: `source="AMAYAMA"`, `manufacturer="VOLKSWAGEN"`, `vehicle_model="AMAROK"`, `market="AMA-BR"` — variando apenas `model_code` e `amayama_catalog_id` por spec entry.

Separadamente, define-se `display_key` — uma representação **legível para logs/depuração**, nunca usada para igualdade/lookup/desempate:

```
display_key = f"{source}:{market}:{model_code}:{amayama_catalog_id}"
  com escaping por componente: "\\" → "\\\\", ":" → "\\:"
  (evita colisão caso algum componente contenha ":" ou "\" literal)
```

**Campos explicitamente excluídos do `stable_key`** (conforme correção do PO): `production_start`, `production_end`, `source_url`. Justificativa: esses atributos podem legitimamente mudar ao longo do tempo (ex. uma data de fim de produção comprovada posteriormente, ou uma URL da fonte reorganizada) sem que isso represente uma *nova* identidade de catálogo — a identidade já está inteiramente determinada por `amayama_catalog_id` em conjunto com o escopo (`source`/`manufacturer`/`vehicle_model`/`market`/`model_code`), conforme Constitution §2/§3. Incluir campos mutáveis-sem-mudança-de-identidade no `stable_key` quebraria a garantia de que a mesma spec entry sempre produz a mesma chave.

**Rationale**: Usar um hash (em vez de uma string legível concatenada) sobre `canonical_json` elimina por construção qualquer risco de colisão por separador presente em um componente (ex. um `model_code` hipotético contendo `:`), sem exigir uma rotina de escaping para fins de *identidade* — o escaping só é necessário para o `display_key`, que existe apenas para leitura humana e nunca participa de comparação de igualdade/lookup. O padrão `domain_separator + canonical_json` já é o mesmo usado para os fingerprints de conteúdo (`contracts/normalization-fingerprint-contracts.md`), o que mantém consistência de mecanismo dentro do projeto — identidade e conteúdo usam a mesma técnica de hashing determinístico, apenas com domain separators e versões diferentes. `stable_key` continua servindo como critério de desempate determinístico na seleção de representante (FR-022, §12 abaixo) — um hash hexadecimal é uma string totalmente ordenável, então a comparação lexicográfica permanece válida como desempate, mesmo sem carregar significado legível.

O identificador primário de linha no banco (surrogate key, ex. `spec_entry_id` UUID) permanece separado do `stable_key`: o surrogate é usado para relações internas (FK); `stable_key` é usado para correlação determinística entre execuções (ex. reconhecer que duas capturas em runs diferentes referem-se à mesma spec entry) e como critério de desempate.

**Alternatives considered**: manter `stable_key` como string legível concatenada com escaping manual (rejeitado como formato *normativo* — o PO pediu explicitamente que, se uma string legível for usada, ela tenha escaping definido; optou-se por resolver isso de forma mais robusta via hash+display_key separado, eliminando a necessidade de uma rotina de escaping fazer parte do contrato de identidade); usar `stable_key` como chave primária diretamente (rejeitado: acopla o schema relacional ao formato escolhido; um surrogate id é mais barato de indexar/referenciar e permite evoluir a representação de `stable_key` sem migração de FKs).

---

## 11. `OemReference` (nó da hierarquia) vs. `oem_code` (campo de peça)

**Decision**: `OemReference` (o nó "OEM" ao final da hierarquia modelo→mercado→spec entry→categoria→grupo→schema→OEM da Constitution) é modelado como uma **projeção derivada** do conjunto de `oem_code` distintos presentes nas peças (`Part.oem_code`) de um dado `Schema` — não como uma entidade coletada de uma página própria.

**Rationale**: Nenhum seletor de página "OEM" separada foi pesquisado/fornecido (a pesquisa de seletores do ponto 20 só cobre até o nível de tabela de peças, cujo campo `OEM` é `.entriesTable__number`). Interpretar o nó "OEM" da hierarquia como o agregado dos `oem_code` de um schema é a leitura mais direta dos dados já especificados como obrigatórios de coletar (ponto 7 do PLAN, FR-013), sem inventar uma nova fonte de dados ou página. Esta é uma decisão de modelagem técnica, não uma mudança de requisito: nenhum dado novo é coletado; apenas se formaliza como os dados de `oem_code` já exigidos se relacionam com o nível hierárquico "OEM" citado pela Constitution.

**Alternatives considered**: tratar "OEM" como sinônimo do `manufacturer` (Volkswagen) — rejeitado, pois a Constitution já usa "OEM" em um nível mais granular que o `Model`/`Market`, mais próximo do sentido de "referência ao fabricante/código original da peça"; deixar `OemReference` como `[NEEDS CLARIFICATION]` — rejeitado porque não altera comportamento observável nem requisito: é puramente uma decisão de representação de dados já obrigatórios.

---

## 12. Critérios determinísticos de seleção de representante

**Decision**: cada critério da ordem já aprovada pela Constitution (§9) é medido como segue:

1. **Snapshot válido**: `snapshot.state == VALID` (specs com snapshot não-VALID são desclassificadas antes dos critérios seguintes).
2. **Maior cobertura de imagens**: contagem de imagens **próprias** (não herdadas via fallback) associadas a peças/à spec entry naquele snapshot — evita circularidade com a resolução de fallback, que depende apenas do cluster, não do representante.
3. **Catálogo mais atual**: `collected_at` mais recente entre os snapshots `VALID` candidatos (nenhum indicador de "versão de catálogo" mais forte foi fornecido pela fonte; se a Amayama expuser um indicador de atualização do catálogo, este critério deve ser revisado — registrado como item aberto de pesquisa, não bloqueante).
4. **Maior completude de metadados**: proporção de campos de identidade+peça declarados como preserváveis (FR-004, FR-013) que estão preenchidos (não nulos/vazios) naquele snapshot.
5. **Chave estável como desempate**: comparação lexicográfica determinística do `stable_key` (hash hexadecimal — ver §10; totalmente ordenável, portanto válido como desempate mesmo sem significado legível).

**Rationale**: Constitution §9 define a ordem, mas não a métrica; esta seção fecha a lacuna com métricas objetivas e reprodutíveis, sem alterar a ordem ou o significado dos critérios.

**Alternatives considered**: usar cobertura de imagem **incluindo** fallback (rejeitado: criaria dependência circular entre seleção de representante e resolução de fallback).

---

## 13. Detecção de captura inválida/challenge/tradução contaminada

**Decision**: validação por camada dedicada (`validation/`) que classifica toda captura recebida em exatamente um de cinco resultados: `ACCEPTED`, `CHALLENGE`, `TRANSLATION_CONTAMINATED`, `INVALID`, `INCOMPLETE` — nunca uma página vazia tratada como `ACCEPTED`.

**Rationale**: heurísticas de detecção (título/strings características de "Just a moment", presença de containers de challenge do Cloudflare, ausência total dos seletores estruturais esperados, atributos/markup característicos de tradução automática do navegador como `class` injetada pelo Google Translate no `<html>`) são um contrato de comportamento (o que deve ser detectado), não uma implementação — os detectores concretos são item de TASKS/implementação, mas o contrato de classificação (5 resultados mutuamente exclusivos) já fecha o desenho para evitar que qualquer um desses resultados seja tratado como conteúdo de catálogo válido (Constitution §5, FR-010).

**Alternatives considered**: um único booleano `is_valid` (rejeitado: perde a distinção exigida explicitamente pelo ponto 4 do PLAN entre challenge/tradução/inválida/incompleta, cada uma com tratamento e log distintos).

---

## 14. Observabilidade

**Decision**: logging estruturado (JSON lines) por evento de pipeline, correlacionado por `run_id`, sem nunca despejar o raw HTML completo no log.

**Rationale**: atende ao ponto 27 do PLAN (run id, spec, group, status, erros de parsing, challenge, detecção de tradução, snapshot gerado, versões, decisões de equivalência) sem duplicar dados sensíveis/grandes já preservados no armazenamento content-addressed — o log referencia o `content_hash`/caminho do raw, não o conteúdo.

**Alternatives considered**: logging não estruturado (texto livre) — rejeitado por dificultar auditoria automatizada e correlação por `run_id`/`spec_id`.

---

## 15. Idempotência de checkpoint/snapshot e atomicidade de finalização (correção técnica — ajuste final do PLAN)

**Problema identificado**: a formulação anterior deste PLAN afirmava que a idempotência de checkpoint/resume era garantida pelo content-addressing do raw (§8). Isso é insuficiente: content-addressing evita duplicação **física** do blob, mas não impede (a) duas linhas de `CheckpointEntry` para a mesma unidade lógica de progresso; (b) duas transições concorrentes/repetidas para `ACCEPTED`; (c) dois `SpecSnapshot` gerados por um retry da mesma coleta aceita; (d) perda de provenance quando duas observações distintas (`RawCapture`) compartilham o mesmo `content_hash`.

**Decision**: quatro mecanismos complementares, todos detalhados executavelmente em `data-model.md` §4 e §13, e no pseudo-algoritmo de `contracts/snapshot-contract.md`:

1. **Chave única de checkpoint**: `UNIQUE(run_id, spec_key, category_slug, group_id)` em `CheckpointEntry`, com toda escrita feita via upsert transacional (`BEGIN IMMEDIATE ... COMMIT`) sobre essa chave — nunca um `INSERT` incondicional.
2. **Distinção `RawBlob` vs. `RawCapture` (Observation)**: o conteúdo físico (content-addressed, deduplicável) é uma entidade (`RawBlob`); cada evento de coleta (`RawCapture`) tem identidade própria (`capture_id`, `run_id`, `collected_at`, proveniência), referenciando um `RawBlob` por `content_hash` sem nunca ser colapsado com outra `RawCapture` que aponte para o mesmo blob.
3. **`idempotency_key` em `SpecSnapshot`**: hash determinístico sobre `run_id + spec_key + accepted_checkpoint_fingerprint` (onde `accepted_checkpoint_fingerprint` é um multiset determinístico dos `(category_slug, group_id, raw_capture_id)` `ACCEPTED` daquela spec entry naquela run), com constraint `UNIQUE(idempotency_key)`. Um retry da mesma finalização recalcula o mesmo `idempotency_key` e não insere um novo snapshot; uma coleta legitimamente nova (novo `raw_capture_id`, mesmo que o conteúdo seja byte-idêntico) produz um `idempotency_key` diferente e um novo snapshot legítimo.
4. **Transação única de finalização**: validar completude → registrar snapshot (ou detectar retry idempotente) → superseder o snapshot anterior → atualizar `current_spec_state` → marcar a finalização — tudo dentro de uma única transação SQLite. Uma falha parcial faz rollback completo; nenhum estado intermediário inconsistente fica visível.

**Rationale**: os quatro mecanismos atacam exatamente os quatro problemas listados, sem introduzir um sistema de locking distribuído — SQLite com escritor único (suficiente para o escopo de operador único desta feature, já decidido em §8) fornece atomicidade de transação "de graça". Usar `raw_capture_id` (identidade da observação) em vez de `content_hash` (identidade do blob) no `accepted_checkpoint_fingerprint` é a peça-chave que preserva a distinção exigida entre "mesmo conteúdo" e "mesma coleta" — sem isso, duas observações honestamente distintas do mesmo HTML (ex.: revalidação periódica que apenas confirma que nada mudou) poderiam ser incorretamente tratadas como a mesma finalização.

**Alternatives considered**: depender de `content_hash` como parte do `idempotency_key` do snapshot (rejeitado: colapsaria duas observações/coletas distintas do mesmo conteúdo em um único snapshot, violando o requisito explícito de que "raw igual em momentos diferentes não significa automaticamente mesmo snapshot"); locking em nível de aplicação (mutex/semáforo) além da transação SQLite (rejeitado como complexidade desnecessária para o MVP — SQLite de escritor único já serializa escritas; um mecanismo adicional só se justificaria com acesso concorrente multi-processo, que é explicitamente um requisito futuro, não deste MVP); `INSERT OR IGNORE` sem chave única explícita (rejeitado: sem uma constraint de unicidade real, não há garantia formal contra duplicação — a chave única é o que torna a operação verificável, não apenas a escolha do verbo SQL).
