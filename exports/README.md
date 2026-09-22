# Volkswagen BR Hubbi export artifacts

The final Volkswagen BR consolidation is preserved locally. These generated
artifacts are intentionally excluded from normal Git commits because the CSV,
conflict report, and image cache are large.

## Final artifacts

| Artifact | Local path | Approximate size |
| --- | --- | --- |
| Consolidated Hubbi CSV | `exports/hubbi_volkswagen_full.csv` | 130 MiB |
| Consolidation conflict report | `exports/hubbi_volkswagen_consolidation_conflicts.json` | 260 MiB |
| Representative final sample | `exports/hubbi_volkswagen_final_sample.csv` | 1.8 MiB |
| Final validation report | `exports/hubbi_volkswagen_validation_report.json` | 9 KiB |
| Local raw and marked image cache | `exports/images/`, `exports/images_marked/` | 10+ GiB |

## Consolidation summary

- Final unique parts: **41,567**.
- Unique applications: **2,357,419**.
- Image coverage reported by the final CSV validation: **98.72%**.

The source code, export scripts, tests, and this inventory are versioned in
Git. Store or transfer the large generated files separately when an off-machine
backup is required; they are not managed through Git LFS at this time.
