# Contrato: Normalização v1 e Fingerprints

**Feature**: `001-amarok-ama-br-ingestion` — ver [../research.md](../research.md) §7 (serialização canônica) para o formato JSON usado no hashing.

## Normalização v1 — `normalizer_version = "amayama-normalizer-v1"`

Determinística, conservadora, versionada (Constitution §7). Regras:

| Campo/contexto | Regra |
|---|---|
| Todo texto | Unicode NFKC |
| Todo texto | Normalizar NBSP (` `) e variantes de quebra de linha para espaço/`\n` padrão; colapsar whitespace técnico redundante |
| Todo texto | `strip()` (trim) nas extremidades |
| `oem_code` | `strip()` + `upper()` + remoção de whitespace técnico interno (ex.: espaços não-significativos entre blocos de um código OEM), quando comprovadamente apenas formatação |
| Pontuação | Preservada, salvo regra comprovadamente apenas de formatação (nenhuma remoção arbitrária) |
| `schema_id` | `strip()` |
| `position_pnc` | `strip()` + `upper()` |
| `pr_codes` | cada código: `strip()` + `upper()`; a lista é ordenada (ordem lexicográfica) quando os PR codes chegam como lista estruturada da fonte. Esta normalização se aplica para fins de domínio/export/inspeção — `pr_codes` **não** entra no `part_fingerprint` (ver seção "Fingerprint de peça" abaixo). |

**Explicitamente NÃO aplicado na normalização usada para equivalência exata** (Constitution §7, FR-016): tradução, stemming, fuzzy matching, correção ortográfica, sinonímia, remoção arbitrária de acentos, heurística semântica.

**Regra de versionamento**: qualquer alteração em qualquer uma das regras acima exige um novo `normalizer_version` (ex.: `amayama-normalizer-v2`) e revalidação dos fingerprints dependentes (Constitution §7, §13) — nunca uma reinterpretação silenciosa do mesmo valor de versão.

## Serialização canônica

Ver `research.md` §7: `json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))` sobre a estrutura já normalizada (NFKC aplicado antes).

## Fingerprint de peça (`part_fingerprint`) — `fingerprint_version = "amayama-fingerprint-v1"`

Campos canônicos incluídos (conteúdo da peça — identidade da spec NUNCA entra aqui):

```
canonical_part = {
  "schema_id": <normalizado>,
  "pnc": <normalizado>,
  "oem": <normalizado ou null>,
  "description": <normalizado ou null>,
  "details": <normalizado ou null>,
  "period": <normalizado ou null>,
  "required": <quantity normalizado ou null>
}

part_fingerprint = SHA256("amayama:part:v1\0" + canonical_json(canonical_part))
```

**`pr_codes` está fora do `part_fingerprint` no `amayama-fingerprint-v1` — decisão fechada pelo PO.** `canonical_part` acima é exaustivo: nenhum campo além dos sete listados participa do hash de conteúdo da peça em v1. Regras associadas:

- `pr_codes` continua sendo preservado quando disponível — em `Part.pr_codes` (raw/domain, `data-model.md` §3) e na fronteira de export (`contracts/export-boundary-contract.md`) — apenas não entra no cálculo de `part_fingerprint`.
- Ausência legítima de `pr_codes` continua não sendo erro (FR-014), independentemente de participar ou não do fingerprint.
- Nenhuma TASK futura pode decidir silenciosamente adicionar `pr_codes` (ou qualquer outro campo fora da lista `canonical_part`) ao `part_fingerprint` de `amayama-fingerprint-v1`. Alterar o conjunto de campos canônicos exige uma nova versão explícita (ex. `amayama-fingerprint-v2`) e a revalidação correspondente dos fingerprints/clusters dependentes (Constitution §13, `contracts/equivalence-contracts.md`).

## Fingerprints hierárquicos (multiset em cada nível)

```
group_fingerprint(group) =
  SHA256("amayama:group:v1\0" + canonical_json({
    "group_id": group.group_id,
    "part_fingerprints_multiset": sorted(count(part_fingerprint) as pairs)
  }))
  # multiset: ordem dos parts não importa; duplicatas alteram o resultado (contagem preservada)

category_fingerprint(category) =
  SHA256("amayama:category:v1\0" + canonical_json({
    "category_slug": category.category_slug,
    "group_fingerprints_multiset": sorted(count(group_fingerprint) as pairs)
    # grupos vazios entram no multiset com seu próprio group_fingerprint (baseado em multiset vazio de parts)
  }))

spec_parts_hash(spec_entry) =
  SHA256("amayama:spec-parts:v1\0" + canonical_json({
    "category_fingerprints_multiset": sorted(count(category_fingerprint) as pairs)
  }))
```

**Invariante de multiset**: em todos os níveis, a comparação de coleções é por multiset — ordem não importa, duplicatas alteram o hash resultante (Constitution §8, ponto 11 do PLAN).

**Invariante de grupos vazios**: um `Group` sem `Schema`/`Part` ainda produz um `group_fingerprint` válido (baseado em multiset vazio), e participa do `category_fingerprint` normalmente — grupos vazios não são omitidos da estrutura (ponto 6 do PLAN).

## Fingerprints independentes (não misturar com `spec_parts_hash`)

```
schema_semantic_hash(spec_entry) =
  SHA256("amayama:schema-semantic:v1\0" + canonical_json({
    "schemas_multiset": sorted(count(schema_id normalizado) as pairs)
  }))
  # baseado na estrutura/identificação de schemas, não no conteúdo de parts

image_hash(spec_entry) =
  SHA256("amayama:image:v1\0" + canonical_json({
    "own_image_refs_multiset": sorted(count(image reference normalizada) as pairs)
  }))
  # somente imagens PRÓPRIAS (não herdadas via fallback) — ver contracts/image-contract.md

structure_hash(spec_entry) =
  SHA256("amayama:structure:v1\0" + canonical_json({
    "categories_multiset": sorted(count(category_slug) as pairs),
    "groups_multiset": sorted(count((category_slug, group_id)) as pairs),
    "schemas_multiset": sorted(count((group_id, schema_id)) as pairs)
  }))
  # forma estrutural bruta — usado por revalidação para localizar nível de divergência
  # sem recomputar todos os hashes de conteúdo (ver contracts/equivalence-contracts.md)
```

**Invariante central**: `image_hash` NUNCA entra em `spec_parts_hash` nem influencia `parts_relation` (Constitution §8, §10, FR-018, FR-030, SC-009).

**Rastreabilidade**: FR-015 a FR-018, FR-030, FR-031, User Story 3.
