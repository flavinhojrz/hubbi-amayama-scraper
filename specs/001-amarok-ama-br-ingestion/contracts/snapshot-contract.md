# Contrato: Snapshot

**Feature**: `001-amarok-ama-br-ingestion` — ver [../data-model.md](../data-model.md) §6 para os campos completos e a máquina de estados, e §13 para o algoritmo completo de idempotência/atomicidade resumido aqui.

## Geração de snapshot (transação única de finalização)

```
finalize_spec_entry(parsed_spec_entry, spec_key, run_id) -> SpecSnapshot

  PRECONDIÇÃO: todos os Group descobertos para parsed_spec_entry têm um CheckpointEntry
               (ver data-model.md §11) em status ACCEPTED ou REJECTED — ou seja, a run
               não está mais aguardando tentativas pendentes/em progresso para esta spec entry.

  BEGIN IMMEDIATE  # transação SQLite única — ver data-model.md §13c

    1. collection_complete = True  se e somente se TODOS os CheckpointEntry desta spec_entry
                                     estão em status ACCEPTED (nenhum REJECTED, nenhum PENDING/IN_PROGRESS)
       collection_complete = False  caso contrário (existe ao menos um Group REJECTED e nenhuma
                                     nova tentativa pendente nesta run — coleta encerrada incompleta)

    2. accepted_checkpoint_fingerprint = multiset determinístico de (category_slug, group_id,
       raw_capture_id) sobre os CheckpointEntry ACCEPTED de (spec_key, run_id) — data-model.md §13b
       idempotency_key = SHA256("amayama:snapshot-idempotency:v1\0" +
                                 canonical_json({run_id, spec_key, accepted_checkpoint_fingerprint}))

    3. SE já existe SpecSnapshot com este idempotency_key:
         → retry idempotente da mesma finalização — NÃO inserir novo snapshot;
           usar o snapshot já existente para os passos 6-7
       SENÃO:
         → computar structure_hash, spec_parts_hash, schema_semantic_hash, image_hash
           (ver contracts/normalization-fingerprint-contracts.md) — apenas sobre os Group ACCEPTED
         → state = VALID  se parsed_spec_entry.critical_error is None AND collection_complete == True
           state = INCOMPLETE  se collection_complete == False (mas sem critical_error)
           # um critical_error de parsing sobre uma captura ACCEPTED é tratado como INVALID
           # (nunca gera snapshot VALID nem INCOMPLETE)
           # uma captura CHALLENGE/TRANSLATION_CONTAMINATED/INVALID/INCOMPLETE nunca marca o Group
           # correspondente como ACCEPTED (ver data-model.md §11) — portanto nunca contribui para
           # collection_complete == True por si só
         → INSERT novo SpecSnapshot (imutável a partir daqui; idempotency_key gravado)

    4. SE o passo 3 inseriu um snapshot novo E já existia um SpecSnapshot anterior VALID/STALE
       para a mesma spec_identity:
         → o snapshot anterior transita para SUPERSEDED
         (nunca sobrescrito — FR-029; e nunca disparado por um retry idempotente do passo 3)

    5. UPDATE current_spec_state para apontar ao snapshot_id resultante do passo 3
       (o novo, ou o já existente em caso de retry idempotente)

    6. Marcar a finalização desta spec entry como concluída nesta run

  COMMIT  # falha parcial faz rollback completo — nenhum estado intermediário fica visível
```

## Regras de estado (resumo executável do que já está em `data-model.md`)

| De | Para | Gatilho |
|---|---|---|
| (nenhum) | `VALID` | Captura `ACCEPTED`, sem `critical_error`, `collection_complete=True` |
| (nenhum) | `INCOMPLETE` | Captura `ACCEPTED`, sem `critical_error`, `collection_complete=False` |
| (nenhum) | `INVALID` | Captura não-`ACCEPTED`, ou `ACCEPTED` com `critical_error` |
| `VALID` | `STALE` | Revalidação detecta divergência de conteúdo na fonte, sem nova captura ainda aceita |
| `VALID`/`STALE` | `SUPERSEDED` | Nova captura da mesma spec entry gera um snapshot mais novo, aceito como `VALID`/`INCOMPLETE` |

**Garantias invioláveis**:
- `INCOMPLETE` e `INVALID` nunca participam de avaliação de equivalência (FR-028) — filtrados antes de qualquer chamada a `equivalence-contracts.md`.
- Falha de uma nova coleta (nova captura vira `INVALID`) NUNCA transiciona ou apaga o último `VALID` conhecido daquela spec entry — o "last-known-good" só é sucedido por outro `VALID`/`INCOMPLETE` (ponto 17 do PLAN).
- Snapshots aceitos (`VALID`, `INCOMPLETE`, `STALE`, `SUPERSEDED`) são todos imutáveis quanto ao seu conteúdo histórico — apenas o campo `state` é atualizado por transição (`VALID`→`STALE`→`SUPERSEDED`); os hashes/contagens registrados no momento da criação nunca mudam retroativamente.
- `collection_complete` é sempre derivado do checkpoint hierárquico (data-model.md §11), nunca de um booleano solto na captura — um `Group` cuja captura de origem foi `CHALLENGE`, `TRANSLATION_CONTAMINATED`, `INVALID` ou `INCOMPLETE` nunca contribui como `ACCEPTED`, portanto nunca permite `collection_complete == True` por si só (research.md §9).
- **Retry da mesma finalização nunca duplica snapshot**: `idempotency_key` (`UNIQUE`) garante que reexecutar `finalize_spec_entry` para o mesmo `(run_id, spec_key)` com o mesmo conjunto de `Group`s `ACCEPTED` é um no-op de inserção — a transação encontra o snapshot já existente e apenas confirma `current_spec_state` (data-model.md §13b).
- **Toda a finalização é atômica**: os passos de validar completude, registrar snapshot, superseder o anterior e atualizar `current_spec_state` ocorrem em uma única transação SQLite (`BEGIN IMMEDIATE ... COMMIT`) — uma falha no meio nunca deixa snapshot duplicado, `current_spec_state` apontando para um snapshot inexistente, ou checkpoint "concluído" sem snapshot consistente (data-model.md §13c).

**Rastreabilidade**: FR-008, FR-009, FR-012, FR-026 a FR-031, SC-004, SC-008, User Story 6, User Story 7.
