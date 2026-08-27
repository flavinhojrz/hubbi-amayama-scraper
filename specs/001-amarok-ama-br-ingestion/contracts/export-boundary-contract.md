# Contrato: Export/Adapter Boundary

**Feature**: `001-amarok-ama-br-ingestion` — FR-033.

## Princípio

A saída desta feature é uma **representação de domínio interna**, não um schema de exportação do ecossistema Hubbi (fora de escopo — ver `spec.md` "Out of Scope"). O módulo `export/` expõe uma fronteira de leitura sobre `CurrentSpecState`/`EquivalenceClass`/`ResolvedImage` (ver `data-model.md`), sem que `domain/`, `equivalence/`, `fingerprints/` ou `snapshots/` conheçam a existência de qualquer schema externo.

## Forma do boundary (conceitual — sem implementação nesta feature)

```
ExportView:
  spec_identity: SpecIdentity completo (todos os campos de data-model.md §1)
  hierarchy: Category → Group → Schema → Part (estrutura completa preservada)
  cluster: { cluster_key, is_representative: bool, representative_spec_ref }
  resolved_image: ResolvedImage | None
  snapshot_reference: { snapshot_id, state, collected_at, parser_version, normalizer_version, fingerprint_version }
```

**Regras**:
- Nenhum dado é **perdido** na fronteira — a representação interna já preserva tudo que `spec.md` exige (identidade, hierarquia, proveniência); o `export/` apenas projeta/formata para consumo externo futuro.
- Nenhuma integração HTTP/API é criada nesta feature (fora de escopo — "Não criar API HTTP sem requisito", ponto 22/23 do PLAN).
- Uma futura feature de integração Hubbi implementaria um adapter concreto que traduz `ExportView` para o schema externo — sem modificar `domain/`, `equivalence/`, `fingerprints/` ou `snapshots/`.

**Rastreabilidade**: FR-033.
