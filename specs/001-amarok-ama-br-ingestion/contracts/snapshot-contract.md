# Contrato: Snapshot

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) §6 para os campos completos e a máquina de estados, e §13c para o algoritmo completo (fonte normativa) de reconstrução/idempotência/atomicidade resumido aqui.

## Geração de snapshot: reconstrução (leitura) + transação única de metadados (escrita)

**Correção (revisão cirúrgica, 2026-08-26)**: `finalize_spec_entry()` não recebe mais uma árvore agregada pronta como parâmetro — ela não pressupõe que nenhum `ParsedGroupDetail` tenha sobrevivido em memória entre processos. Toda a reconstrução acontece a partir do que está persistido (`manifest_repo.get_authoritative()`, `checkpoint_repo.list_accepted()`, `RawCaptureRepository.get()` + `RawBlobStore.read()` — contracts/ports-contract.md "Replay / Reconstrução determinística"), **antes** de qualquer escrita. Nenhum `SpecSnapshot` é criado antes de a árvore e os fingerprints existirem por completo.

```
finalize_spec_entry(spec_key, run_id) -> SpecSnapshot | None

  # Fase 1 — reconstrução e cálculo (leitura + computação pura, sem transação de escrita)

  1. manifest = manifest_repo.get_authoritative(spec_key, run_id)   # data-model.md §15
     SE manifest is None: RETORNA None (sem manifesto autoritativo, nada a finalizar —
        nunca gera snapshot, nunca infere completude a partir de checkpoints avulsos)

  2. accepted_entries = checkpoint_repo.list_accepted(run_id, spec_key)   # data-model.md §11
     collection_complete = True  se e somente se todo (category_slug, group_id) do
                             manifesto está coberto por accepted_entries
     collection_complete = False caso contrário

  3. PARA CADA CheckpointEntry em accepted_entries:
       raw_content = reconstruct_raw_content(entry.raw_capture_id, capture_repo, blob_store)
                     # contracts/ports-contract.md — get(capture_id) → RawCapture.content_hash
                     #                              → blob_store.read(content_hash) → bytes
       group_details[(entry.category_slug, entry.group_id)] =
         parse_group_detail(raw_content, entry.category_slug, entry.group_id)
     # reexecutar parse_group_detail() aqui é o que torna esta etapa independente de
     # qualquer estado em memória de execuções anteriores — inclusive após um restart

  4. assembled_tree = assemble_spec_tree(manifest, group_details)   # contracts/domain-contracts.md
     normalized_tree = apply_normalization(assembled_tree)          # amayama-normalizer-v1
     fingerprint_set = compute_fingerprint_set(normalized_tree)     # amayama-fingerprint-v1
        # structure_hash, spec_parts_hash, schema_semantic_hash, image_hash

  5. accepted_checkpoint_fingerprint = multiset determinístico de (category_slug, group_id,
     raw_capture_id) sobre accepted_entries — data-model.md §13b
     idempotency_key = SHA256("amayama:snapshot-idempotency:v1\0" +
                               canonical_json({run_id, spec_key, accepted_checkpoint_fingerprint}))
     state = VALID       se nenhum group_details[...] tem critical_error AND collection_complete == True
     state = INCOMPLETE  se collection_complete == False (sem critical_error nos grupos já ACCEPTED)
     # uma captura CHALLENGE/TRANSLATION_CONTAMINATED/INVALID/INCOMPLETE nunca marca o Group
     # correspondente como ACCEPTED (data-model.md §11) — portanto nunca contribui para
     # collection_complete == True por si só

  # Fase 2 — transação única de metadados (única parte que escreve no banco)

  BEGIN IMMEDIATE  # transação SQLite única — ver data-model.md §13c

    6. SE já existe SpecSnapshot com este idempotency_key:
         → retry idempotente da mesma finalização — NÃO inserir novo snapshot;
           usar o snapshot já existente para os passos 8-9
       SENÃO:
         → INSERT novo SpecSnapshot com o payload já completo dos passos 4-5
           (fingerprint_set, state, idempotency_key — nunca um snapshot parcial)
         → persistir fingerprint_set associado (fingerprint_repo)

    7. SE o passo 6 inseriu um snapshot novo E já existia um SpecSnapshot anterior VALID/STALE
       para a mesma spec_identity:
         → o snapshot anterior transita para SUPERSEDED
         (nunca sobrescrito — FR-029; e nunca disparado por um retry idempotente do passo 6)

    8. UPDATE current_spec_state para apontar ao snapshot_id resultante do passo 6
       (o novo, ou o já existente em caso de retry idempotente) — last-known-good

    9. Marcar a finalização desta spec entry como concluída nesta run

  COMMIT  # falha na Fase 2 faz rollback completo — nenhum estado intermediário fica visível.
          # falha na Fase 1 nunca chega a abrir a transação — nada a reverter; a finalização
          # é re-tentável mais tarde (Fase 1 é pura leitura + computação determinística)
```

## Regras de estado (resumo executável do que já está em `data-model.md`)

| De | Para | Gatilho |
|---|---|---|
| (nenhum) | `VALID` | Manifesto autoritativo existe, todos os grupos esperados `ACCEPTED`, nenhum `critical_error` |
| (nenhum) | `INCOMPLETE` | Manifesto autoritativo existe, mas nem todos os grupos esperados estão `ACCEPTED` ainda |
| (nenhum) | `INVALID` | Manifesto não-autoritativo (sem ele, `finalize_spec_entry()` não roda), ou `critical_error` em um grupo `ACCEPTED` |
| `VALID` | `STALE` | Revalidação detecta divergência de conteúdo na fonte, sem nova captura ainda aceita |
| `VALID`/`STALE` | `SUPERSEDED` | Nova captura da mesma spec entry gera um snapshot mais novo, aceito como `VALID`/`INCOMPLETE` |

**Garantias invioláveis**:
- `INCOMPLETE` e `INVALID` nunca participam de avaliação de equivalência (FR-028) — filtrados antes de qualquer chamada a `equivalence-contracts.md`.
- Falha de uma nova coleta (nova captura vira `INVALID`) NUNCA transiciona ou apaga o último `VALID` conhecido daquela spec entry — o "last-known-good" só é sucedido por outro `VALID`/`INCOMPLETE` (ponto 17 do PLAN).
- Snapshots aceitos (`VALID`, `INCOMPLETE`, `STALE`, `SUPERSEDED`) são todos imutáveis quanto ao seu conteúdo histórico — apenas o campo `state` é atualizado por transição (`VALID`→`STALE`→`SUPERSEDED`); os hashes/contagens registrados no momento da criação nunca mudam retroativamente.
- `collection_complete` é sempre derivado do **manifesto autoritativo** (data-model.md §15) cruzado com o checkpoint hierárquico (data-model.md §11) — nunca de um booleano solto na captura, e nunca inferido apenas a partir dos `CheckpointEntry` observados sem manifesto (research.md §17). Um `Group` cuja captura de origem foi `CHALLENGE`, `TRANSLATION_CONTAMINATED`, `INVALID` ou `INCOMPLETE` nunca contribui como `ACCEPTED`, portanto nunca permite `collection_complete == True` por si só.
- **Retry da mesma finalização nunca duplica snapshot**: `idempotency_key` (`UNIQUE`) garante que reexecutar `finalize_spec_entry` para o mesmo `(run_id, spec_key)` com o mesmo conjunto de `Group`s `ACCEPTED` é um no-op de inserção — a transação encontra o snapshot já existente e apenas confirma `current_spec_state` (data-model.md §13b).
- **Toda a finalização é atômica**: a Fase 2 (validar/registrar snapshot, superseder o anterior, atualizar `current_spec_state`) ocorre em uma única transação SQLite (`BEGIN IMMEDIATE ... COMMIT`) — uma falha no meio nunca deixa snapshot duplicado, `current_spec_state` apontando para um snapshot inexistente, ou checkpoint "concluído" sem snapshot consistente (data-model.md §13c).
- **Reconstrução independente de estado em memória**: a Fase 1 (manifesto → grupos aceitos → raw persistido → `parse_group_detail()` → árvore → fingerprints) usa exclusivamente leituras de persistência (`manifest_repo`, `checkpoint_repo`, `RawCaptureRepository`, `RawBlobStore`) — nunca uma referência a um objeto parseado que só existiria na memória do processo que fez a coleta original. Um restart do processo entre a aceitação dos grupos e a finalização não perde nada: a próxima chamada a `finalize_spec_entry()` reconstrói tudo do zero a partir do raw persistido (data-model.md §13c).
- **Nenhum `SpecSnapshot` incompleto é criado**: a Fase 2 só insere um `SpecSnapshot` depois que a árvore agregada, a normalização e o `fingerprint_set` completo já existem (calculados na Fase 1) — nunca um registro parcial que precisaria ser "completado" depois.

**Rastreabilidade**: FR-008, FR-009, FR-012, FR-026 a FR-031, SC-004, SC-008, User Story 6, User Story 7.
