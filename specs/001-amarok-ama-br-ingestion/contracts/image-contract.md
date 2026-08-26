# Contrato: Imagens e Fallback

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) §10.

## Princípio central

Imagem é um domínio **independente** da equivalência de peças (Constitution §10, FR-018, FR-030). `image_hash` nunca entra em `spec_parts_hash`; uma mudança isolada de imagem nunca move uma spec para outro cluster de peças (SC-009).

## Resolução de imagem

```
resolve_image(spec_entry, cluster) -> ResolvedImage | None

  1. Se spec_entry possui imagem própria (own_image_refs não vazio) → ResolvedImage(is_fallback=False, origin_spec_ref=spec_entry, ...)
  2. Senão, se spec_entry pertence a um cluster cujo parts_relation == EXACT comprovado
     E algum outro membro do cluster possui imagem própria
     → ResolvedImage(is_fallback=True, origin_spec_ref=<membro de origem>, resolved_within_cluster_key=cluster.cluster_key, ...)
  3. Senão → None (spec entry sem imagem resolvível nesta coleta; não é erro)
```

**Pré-condição obrigatória para o passo 2**: o cluster já deve ter sido determinado por `equivalence-contracts.md` (parts_relation == EXACT, comparison_valid == True) **antes** de qualquer fallback ser considerado. Fallback nunca é usado como sinal de equivalência — é estritamente uma consequência de uma equivalência já comprovada por outra via (peças).

## Provenance obrigatória

Todo `ResolvedImage` DEVE registrar `origin_spec_ref` — a spec entry de onde a imagem realmente veio — mesmo quando `is_fallback=True`. Nunca é permitido atribuir uma imagem a uma spec sem registrar de onde ela veio (FR-024, FR-025).

## Representação

Ver `data-model.md` §10 para os campos de `ResolvedImage`. Três estados possíveis para uma dada spec entry, todos representáveis:

- **Imagem própria**: `is_fallback=False`.
- **Imagem herdada/fallback**: `is_fallback=True`, com `resolved_within_cluster_key` preenchido.
- **Sem imagem resolvida**: ausência de `ResolvedImage` para aquela spec entry nesta coleta (não é erro; é um estado legítimo, sujeito a melhorar em coletas futuras).

**Rastreabilidade**: FR-018, FR-023 a FR-025, FR-030, SC-007, SC-009, User Story 5.
