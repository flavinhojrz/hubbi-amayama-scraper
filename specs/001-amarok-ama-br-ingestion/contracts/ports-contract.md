# Contrato: Ports de Persistência (Dependency Inversion)

**Feature**: `001-amarok-ama-br-ingestion` — ver [../research.md](../research.md) §18 para a decisão e justificativa completas.

## Motivação

`accept_capture()` (contracts/input-contracts.md) precisa preservar `RawBlob`/`RawCapture` de forma imutável antes de qualquer validação (Constitution §4), mas a implementação concreta de armazenamento (SQLite + filesystem content-addressed) só é construída quando a persistência é implementada. Sem uma fronteira explícita, isso criaria uma dependência oculta do núcleo de ingestão sobre a implementação concreta de persistência, quebrando a testabilidade 100% offline exigida pela Constitution §12.

Este contrato define os *ports* (interfaces) que resolvem isso via inversão de dependência: o núcleo depende de uma abstração que ele mesmo define; a implementação concreta depende dessa abstração, nunca o contrário.

## Ports

```
RawBlobStore (protocol):
  get_or_create(content_hash: str, raw_content: bytes) -> RawBlob
    # Se um RawBlob já existe para content_hash, retorna o existente sem gravar nada novo.
    # Caso contrário, grava o conteúdo e retorna um novo RawBlob (first_seen_at = agora).
  read(content_hash: str) -> bytes
    # Lê o conteúdo bruto de um RawBlob já existente.

RawCaptureRepository (protocol):
  save(capture: RawCapture) -> None
    # Sempre insere uma nova observação — nunca faz upsert/merge por content_hash.
  get(capture_id: str) -> RawCapture | None
```

**Regras**:
- Nenhum dos dois ports conhece SQLite, filesystem concreto, ou qualquer detalhe de armazenamento. São definidos usando `typing.Protocol` (ou `abc.ABC`) da stdlib — sem dependência externa.
- `accept_capture(input: RawCaptureInput, blob_store: RawBlobStore, capture_repo: RawCaptureRepository) -> RawCapture` recebe os ports por injeção de dependência (parâmetro de função/construtor), nunca os instancia internamente.
- Testes do núcleo de ingestão usam implementações *fake* em memória (`InMemoryRawBlobStore`, `InMemoryRawCaptureRepository`) — sem SQLite, sem filesystem real, mantendo a Phase 3 (`tasks.md`) testável 100% offline e independente da Phase 10.

## Replay / Reconstrução determinística (fecha o gap de checkpoint/resume após restart)

Os mesmos dois métodos de leitura já definidos acima (`RawCaptureRepository.get()` e `RawBlobStore.read()`) são **suficientes** para reconstruir o conteúdo bruto de qualquer `Group` já `ACCEPTED`, mesmo que nenhum objeto parseado tenha sobrevivido em memória entre processos — sem introduzir nenhum storage paralelo:

```
reconstruct_raw_content(capture_id: str, capture_repo: RawCaptureRepository, blob_store: RawBlobStore) -> bytes
  raw_capture = capture_repo.get(capture_id)          # RawCapture — inclui content_hash
  raw_content = blob_store.read(raw_capture.content_hash)   # bytes — o HTML bruto original
  return raw_content
```

`CheckpointEntry.raw_capture_id` (data-model.md §11) é a chave que liga um `Group` `ACCEPTED` ao seu `capture_id` — e portanto, via a cadeia acima, ao seu `raw_content` original. Isso é o que permite que `finalize_spec_entry()` (contracts/snapshot-contract.md) reconstrua todos os `ParsedGroupDetail` de uma spec entry **exclusivamente a partir do que está persistido**, reexecutando `parse_group_detail()` sobre o raw recuperado — sem depender de nenhuma representação parseada ter sobrevivido em memória entre processos (ex.: após um restart).

**Nenhum método novo foi adicionado aos ports** — `get()` e `read()` já definidos acima já eram suficientes; o gap identificado na revisão era de documentação/wiring (nada explicitava esse caminho de leitura), não de capability ausente nos ports em si.

## Adapters concretos (implementados na Phase 10 de `tasks.md`, não nesta fase)

- `FilesystemRawBlobStore` — satisfaz `RawBlobStore` usando o armazenamento content-addressed em disco (research.md §8).
- `SqliteRawCaptureRepository` — satisfaz `RawCaptureRepository` usando SQLite (research.md §8, DEC-002).

Nenhum destes adapters é conhecido pelo núcleo de ingestão — a composição (qual adapter concreto é injetado) acontece na camada de orquestração/composição raiz, fora do escopo de `validation/`, `parsing/`, `domain/`, `normalization/`, `fingerprints/`, `equivalence/`, `assets/`, `snapshots/`.

**Rastreabilidade**: FR-008, FR-009, FR-034; Constitution §6 (separação de responsabilidades), §12 (testabilidade offline).
