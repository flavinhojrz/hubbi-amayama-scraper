# Audi scraper handoff

## Provenance

- GitHub branch: `review/worker-pool`
- GitHub source commit SHA: `63ca1599`
- Google Drive handoff folder: https://drive.google.com/drive/folders/10sMOhZl1d3OHwi_euGuZ2u0dTo2zlu_v
- Collection database: `audi_mass.db`
- Database size: `369020928` bytes
- Database SHA256: `d97c651b73ff85be5a98bd6ef5324f98b62ab5ed0b18c200ab0d84aa7eff00fc`
- Drive database artifact: `audi_mass_db.zip` (71,515,341 bytes), SHA256 `ae25743f062b27ccd2837ffd6be6cf5c12ebc8252e0d57ad43a0309d8f6df101`
- Raw artifact: `audi_mass_raw.zip`, split into `audi_mass_raw.zip.part-001` through `part-020` because Drive's per-file limit is 100 MB
- Raw ZIP size: `1,726,950,221` bytes; SHA256 `0365597f3d565212ff747775bbbe3d6250d1368552ae755e95c22158fe171a1e`

## State at handoff

- Total Audi scopes: 21
- Completed scopes: 13
- Pending scopes: 8
- Valid/processed specs: 1,623
- ACCEPTED checkpoints: 183,661
- REJECTED checkpoints without a matching ACCEPTED: 124
- Collection is paused because Amayama returned `/ban.html` on all four CDPs.

Completed scopes:

`A3/AA3-BR`, `A5-S5-CABRIOLET/A5CA-BR`, `A6-ALLROAD/A6AR-BR`,
`A7-SPORTBACK/A7-BR`, `Q3/AQ3-BR`, `Q7/AQ7-BR`, `R8-SPYDER/R8-BR`,
`RS3-SPORTBACK/RS3-BR`, `RS4-AVANT-QUATTRO/RS4-BR`,
`RS6-PLUS-AVANT-QUATTRO/RS6-BR`, `RS7-SPORTBACK/RS7-BR`,
`RSQ3/RSQ3-BR`, `TTRS-COUPE-ROADSTER/TTRS-BR`.

Pending scopes:

`A1/A1-BR`, `A3-CABRIOLET/A3CA-BR`, `A3-SPORTBACK/A3-BR`,
`A4-AVANT/A4-BR`, `A5-S5-COUPE-SPORTBACK/A5CO-BR`,
`A6-S6-AVANT-QUATTRO/A6Q-BR`, `A8-S8-QUATTRO/A8Q-BR`,
`TT-COUPE-ROADSTER/ATT-BR`.

Historical known retry units:

- A5/S5 Cabriolet → `electrics/953` (resolved in a later resume pass)
- Q7 → `electrics/945` (resolved in a later resume pass)

Scopes interrupted by `invalid session id` included A3 Sportback and A4 Avant.
Accepted checkpoints from those runs are preserved.

## Resume procedure

Do not use `--new-run`. After Amayama access is restored, open four operator-controlled
Chromes on ports 9222–9225, resolve CAPTCHA manually, and run:

```powershell
.\.venv\Scripts\python.exe tools\queue_runner.py `
  --list audi_br_execution_queue.txt `
  --manufacturer AUDI `
  --db-path audi_mass.db `
  --raw-root audi_mass_raw `
  --slots 4 `
  --base-port 9222 `
  --poll-interval 5 `
  --check-interval 5 `
  --resume-existing
```

This maps each incomplete scope to its existing `collection_run.run_id` and uses
`--resume --retry-rejected`, preserving accepted checkpoints. Do not transfer cookies,
Chrome profiles, CDP sessions, or secrets to the new PC.

To reconstruct raw captures on the new PC, concatenate the 20 parts in lexical order
into `audi_mass_raw.zip`, verify its SHA256 above, and extract it beside `audi_mass.db`.
