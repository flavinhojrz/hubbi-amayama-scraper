# Quickstart — Ferramenta de Análise do Corpus

Somente leitura. Nunca cria nem altera `amayama.db`. Requer que o banco já exista.

```bash
# Resumo geral
uv run python -m amayama_scraper.cli.analyze summary \
  --manufacturer VOLKSWAGEN --vehicle-model AMAROK --market AMA-BR \
  --db-path amayama.db

# Qualidade da coleta (achados por severidade)
uv run python -m amayama_scraper.cli.analyze quality \
  --manufacturer VOLKSWAGEN --vehicle-model AMAROK --market AMA-BR --json

# Redundância via fingerprints
uv run python -m amayama_scraper.cli.analyze redundancy \
  --manufacturer VOLKSWAGEN --vehicle-model AMAROK --market AMA-BR

# Comparação detalhada entre duas specs (stable_key de spec_registry)
uv run python -m amayama_scraper.cli.analyze compare \
  --spec-a <stable_key_a> --spec-b <stable_key_b> --json
```

`--json` alterna para saída estruturada (determinística — mesma base sempre produz o mesmo JSON); sem a flag, a saída é texto legível. `--db-path` é opcional (default `amayama.db`).

## Como interpretar

- **`summary`**: `categorias/grupos/schemas/parts` são somas por spec (não deduplicadas — bate com os totais já auditados manualmente: 7.769 grupos / 27.909 schemas / 415.758 peças para Amarok/AMA-BR). As distribuições (min/max/mean/median) só consideram specs com pelo menos um snapshot — uma spec nunca coletada entraria como "0" e distorceria a distribuição, então ela some da distribuição (mas continua contando em `specs_discovered`/`specs_incomplete_or_problematic`).
- **`quality`**: cada achado tem `severity` (`ERROR`/`WARNING`/`INFO`) e explica na própria mensagem por que é suspeito. `SPEC_WITH_ZERO_PARTS` é sempre `INFO` — nunca tratar como erro automaticamente (caso confirmado: `2HBC34`, catálogo vazio legítimo). `ERROR` = spec nunca coletada ou snapshot `INVALID`. `WARNING` = tudo que é indício de coleta incompleta/divergente mas não necessariamente errado (manifest ausente, divergência de contagem de grupos, grupo esperado nunca `ACCEPTED`, estrutura zerada).
- **`redundancy`**: agrupa por `spec_parts_hash` usando a mesma `cluster_key()` normativa do projeto (Constitution §9) — só specs com snapshot `VALID`/`STALE` e `collection_complete=True` entram no cálculo (§11). É puramente informativo: nenhuma spec é fundida ou apagada. `potential_reduction_ratio` é `(specs_considerados - hashes_distintos) / specs_considerados`.
- **`compare`**: `equivalence` reaproveita `equivalence/evaluate.py` (mesma lógica usada na deduplicação real). `group_diff` vem de `spec_group_manifest` (grupos, não peças individuais). Diff de OEMs/peças fica sempre `parts_diff_available=false` — exigiria reprocessar HTML bruto, fora de escopo desta ferramenta (ver `spec.md`, "Fora de escopo").
