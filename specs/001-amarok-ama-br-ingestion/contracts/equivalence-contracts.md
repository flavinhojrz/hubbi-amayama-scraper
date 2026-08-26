# Contrato: Equivalência e Clusters

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) §8–9.

## Scope da equivalência (fixo nesta feature)

```
scope = "AMAYAMA:VOLKSWAGEN:AMAROK:AMA-BR"
```

Conteúdo fora deste scope nunca é comparado como pertencente à mesma classe nesta feature (ponto 13 do PLAN). Uma feature futura que amplie o escopo (outro modelo/mercado/fabricante) usa um `scope` diferente — nenhuma lógica de equivalência desta feature assume implicitamente um scope diferente do acima.

## Condições de validade da comparação (`comparison_valid`)

`comparison_valid = True` se e somente se **todas** as condições abaixo são verdadeiras para os dois lados da comparação:

1. Mesma `source`/`scope` (ver acima).
2. `normalizer_version` idêntico nos dois lados.
3. `fingerprint_version` idêntico nos dois lados.
4. Ambos os `SpecSnapshot` têm `collection_complete = True`.
5. Nenhum dos dois lados tem `critical_error` de parsing.
6. Nenhum dos dois lados foi originado de uma captura `CHALLENGE` ou `TRANSLATION_CONTAMINATED`.
7. Ambos os `SpecSnapshot` estão em estado `VALID` (nunca `INCOMPLETE`/`INVALID`; `STALE` é aceitável apenas se a revalidação ainda não tiver produzido um snapshot mais novo — ver `research.md` sobre a máquina de estados).

Quando `normalizer_version` OU `fingerprint_version` diferem entre os lados (condições 2/3 falham), o resultado é:

```
comparison_valid = False
parts_relation = UNKNOWN     # NUNCA "DIFFERENT" — version mismatch dispara recompute, não uma conclusão de diferença
```

Quando qualquer uma das demais condições falha (1, 4-7):

```
comparison_valid = False
parts_relation = UNKNOWN
```

## Relações

```
parts_relation:  EXACT | DIFFERENT | UNKNOWN
schema_relation: EXACT | DIFFERENT | UNKNOWN
image_relation:  EXACT | COMPLEMENTARY | DIFFERENT | NONE | UNKNOWN
```

- `parts_relation = EXACT` ⇔ `comparison_valid = True` AND `spec_parts_hash` idêntico nos dois lados.
- `parts_relation = DIFFERENT` ⇔ `comparison_valid = True` AND `spec_parts_hash` diferente.
- `schema_relation` segue a mesma lógica sobre `schema_semantic_hash`, independentemente de `parts_relation`.
- `image_relation`:
  - `EXACT`: `image_hash` idêntico nos dois lados (mesmo conjunto de imagens próprias).
  - `COMPLEMENTARY`: um lado tem imagens próprias que o outro não tem, dentro do mesmo cluster de peças comprovado — candidato a fallback (ver `contracts/image-contract.md`).
  - `DIFFERENT`: ambos têm imagens próprias, mas divergentes, sem relação clara de complementaridade.
  - `NONE`: nenhum dos dois lados tem imagem própria.
  - `UNKNOWN`: `comparison_valid = False`.

## Regra de deduplicação (Constitution §8, FR-019)

```
pode_deduplicar(spec_a, spec_b) := comparison_valid AND parts_relation == EXACT
```

Heurísticas (ex.: similaridade de texto, candidatos por prefixo de `model_code`) podem gerar **candidatos** a comparar, mas nunca são usadas como prova de equivalência (FR-020) — apenas `pode_deduplicar` acima, calculado sobre hashes determinísticos, autoriza deduplicação.

## Cluster (classe de equivalência)

```
cluster_key = SHA256_hex_or_composite(scope + "\0" + normalizer_version + "\0" + fingerprint_version + "\0" + spec_parts_hash)
```

Duas spec entries pertencem ao mesmo cluster se e somente se produzem o mesmo `cluster_key` — que, por construção, exige `parts_relation == EXACT` entre elas (mesmo `spec_parts_hash`, mesmas versões, mesmo scope).

Uma estrutura auxiliar (ex. DSU/Union-Find), se implementada futuramente para performance de agrupamento incremental, é sempre recomputável a partir de `cluster_key` — nunca é a fonte normativa (ponto 14 do PLAN).

**Identidade preservada**: pertencer a um cluster nunca redefine ou apaga `SpecIdentity`; toda spec permanece consultável como aplicação/origem válida, representante ou não (FR-021).

## Revalidação incremental (Constitution §11, FR-032)

1. Recalcular `structure_hash` primeiro (mais barato: não depende do conteúdo completo de cada peça).
2. Se `structure_hash` for idêntico ao snapshot anterior, a estrutura (categorias/grupos/schemas presentes) não mudou — comparar em seguida `spec_parts_hash`/`schema_semantic_hash`/`image_hash` diretamente (ainda mais barato que recomputar tudo do zero).
3. Se `structure_hash` divergir, localizar o nível divergente percorrendo os multisets de `category_fingerprint`/`group_fingerprint` (comparação hierárquica) para reportar exatamente onde a mudança ocorreu, sem necessariamente precisar reprocessar categorias/grupos cujo fingerprint permaneceu idêntico.
4. **Nunca afirmar** que um `Group` específico não mudou sem que ao menos seu `group_fingerprint` tenha sido recomputado a partir de uma captura real da fonte — não há "validator" de terceira parte fornecido pela Amayama que permita inferir isso sem revisitar a página (ponto 18 do PLAN).

Freshness (quando um snapshot `VALID` deve ser considerado candidato à revalidação e passar a `STALE`) é política/configuração, não uma constante rígida — parametrizável por classe de spec (ex.: specs de produção encerrada vs. em produção, conforme Constitution §11), com o valor concreto definido em TASKS/implementação (decisão operacional, não semântica).

**Rastreabilidade**: FR-019 a FR-022, FR-028, FR-031, FR-032, User Story 4, User Story 6.
