"""assess_quality() — spec.md US2, plan.md.

Puro: opera sobre dados já carregados. Cada Finding explicita, na mensagem,
por que a condição é suspeita — nunca apenas um código sem contexto.
Zero peças NUNCA produz severidade acima de INFO (Constitution, caso 2HBC34).
"""

from __future__ import annotations

from amayama_scraper.analysis.types import Finding, QualityReport, ScopeIdentifier, Severity
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import SpecGroupManifest, is_manifest_authoritative
from amayama_scraper.fingerprints.types import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

_HASH_FIELDS = ("structure_hash", "spec_parts_hash", "schema_semantic_hash", "image_hash")


def _current_manifest(
    manifests: list[tuple[str, SpecGroupManifest]],
) -> tuple[str, SpecGroupManifest] | None:
    """O (run_id, manifest) vigente: o mais recente (list_for_spec já ordena
    DESC) com manifest_complete=True. Nenhum manifest completo -> None
    (spec.md DEC-004). run_id é preservado (Codex finding #2) para que grupos
    esperados só sejam comparados contra checkpoints ACCEPTED do MESMO run."""
    for run_id, manifest in manifests:
        if is_manifest_authoritative(manifest):
            return run_id, manifest
    return None


def assess_quality(
    scope: ScopeIdentifier,
    specs: list[SpecIdentity],
    latest_snapshot_by_spec: dict[str, SpecSnapshot],
    manifests_by_spec: dict[str, list[tuple[str, SpecGroupManifest]]],
    accepted_by_spec_and_run: dict[str, dict[str, frozenset[tuple[str, str]]]],
) -> QualityReport:
    findings: list[Finding] = []

    for spec in specs:
        key = spec.stable_key()
        display = spec.display_key()
        snapshot = latest_snapshot_by_spec.get(key)
        manifests = manifests_by_spec.get(key, [])
        accepted_by_run = accepted_by_spec_and_run.get(key, {})

        if snapshot is None:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="SPEC_WITHOUT_SNAPSHOT",
                    spec_stable_key=key,
                    message=(
                        f"{display}: nenhum spec_snapshot encontrado — spec descoberta "
                        "mas nunca coletada (ou coleta nunca finalizada com sucesso)."
                    ),
                )
            )
            continue

        if snapshot.state is SnapshotState.INVALID:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="SNAPSHOT_INVALID",
                    spec_stable_key=key,
                    message=f"{display}: snapshot mais recente está INVALID.",
                    details={"snapshot_id": snapshot.snapshot_id},
                )
            )
        elif snapshot.state is not SnapshotState.VALID:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="SNAPSHOT_NOT_VALID",
                    spec_stable_key=key,
                    message=(
                        f"{display}: snapshot mais recente está {snapshot.state.value}, não VALID."
                    ),
                    details={"snapshot_id": snapshot.snapshot_id, "state": snapshot.state.value},
                )
            )

        if not snapshot.collection_complete:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="COLLECTION_NOT_COMPLETE",
                    spec_stable_key=key,
                    message=f"{display}: snapshot mais recente tem collection_complete=0.",
                    details={"snapshot_id": snapshot.snapshot_id},
                )
            )

        unavailable_hashes = [
            field for field in _HASH_FIELDS if getattr(snapshot, field) == UNAVAILABLE_HASH
        ]
        if unavailable_hashes:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="SNAPSHOT_FINGERPRINT_UNAVAILABLE",
                    spec_stable_key=key,
                    message=(
                        f"{display}: fingerprint(s) indisponível(is) no snapshot mais recente "
                        f"({', '.join(unavailable_hashes)}) — nunca participa de "
                        "redundância/equivalência técnica."
                    ),
                    details={"unavailable_hashes": unavailable_hashes},
                )
            )

        counts = snapshot.counts
        categories = counts.get("categories", 0)
        groups = counts.get("groups", 0)
        schemas = counts.get("schemas", 0)
        parts = counts.get("parts", 0)

        if categories == 0 or groups == 0 or schemas == 0:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="SNAPSHOT_SUSPICIOUSLY_EMPTY_STRUCTURE",
                    spec_stable_key=key,
                    message=(
                        f"{display}: snapshot com categorias={categories}, grupos={groups}, "
                        f"schemas={schemas} — estrutura vazia é suspeita de captura quebrada "
                        "(diferente de zero peças com estrutura presente, "
                        "que é apenas informativo)."
                    ),
                    details={"categories": categories, "groups": groups, "schemas": schemas},
                )
            )

        if parts == 0:
            findings.append(
                Finding(
                    severity=Severity.INFO,
                    code="SPEC_WITH_ZERO_PARTS",
                    spec_stable_key=key,
                    message=(
                        f"{display}: 0 peças no snapshot mais recente. Não é necessariamente "
                        "um erro — pode ser um catálogo genuinamente vazio (ex.: 2HBC34)."
                    ),
                    details={"groups": groups, "schemas": schemas},
                )
            )

        current = _current_manifest(manifests)
        if current is None:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="MANIFEST_MISSING_OR_INCOMPLETE",
                    spec_stable_key=key,
                    message=(
                        f"{display}: nenhum spec_group_manifest com manifest_complete=True "
                        "encontrado — sem evidência do universo esperado de grupos."
                    ),
                    details={"manifests_seen": len(manifests)},
                )
            )
            continue

        run_id, current_manifest = current
        expected_keys = current_manifest.expected_group_keys()
        expected_group_count = len(expected_keys)
        if expected_group_count != groups:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="MANIFEST_SNAPSHOT_GROUP_COUNT_MISMATCH",
                    spec_stable_key=key,
                    message=(
                        f"{display}: manifest vigente (run {run_id}) lista "
                        f"{expected_group_count} grupo(s), mas o snapshot reporta {groups} — "
                        "divergência entre manifest e snapshot."
                    ),
                    details={"manifest_groups": expected_group_count, "snapshot_groups": groups},
                )
            )

        accepted_keys = accepted_by_run.get(run_id, frozenset())
        missing_accepted = expected_keys - accepted_keys
        if missing_accepted:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="MANIFEST_GROUPS_NEVER_ACCEPTED",
                    spec_stable_key=key,
                    message=(
                        f"{display}: {len(missing_accepted)} grupo(s) esperado(s) pelo manifest "
                        f"vigente nunca tiveram um checkpoint ACCEPTED no run {run_id} "
                        "(grupo aceito em outro run não conta como cobertura deste)."
                    ),
                    details={
                        "run_id": run_id,
                        "missing_group_keys": sorted(
                            f"{category}/{group}" for category, group in missing_accepted
                        ),
                    },
                )
            )

    return QualityReport(scope=scope, findings=tuple(findings))
