"""T014 — assess_quality(): corpus saudável, manifest divergente, snapshot incompleto,
spec zero-peças (INFO, nunca ERROR/WARNING), spec sem snapshot, grupo nunca ACCEPTED
apenas no run vigente (Codex finding #2), fingerprint indisponível (Codex finding #5)."""

from datetime import UTC, datetime

from amayama_scraper.analysis.quality import assess_quality
from amayama_scraper.analysis.types import ScopeIdentifier, Severity
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.persistence.repositories.snapshot_repo import UNAVAILABLE_HASH
from amayama_scraper.snapshots.snapshot import SnapshotState, SpecSnapshot

SCOPE = ScopeIdentifier(manufacturer="VOLKSWAGEN", vehicle_model="AMAROK", market="AMA-BR")
RUN_ID = "run-1"


def _identity(model_code: str) -> SpecIdentity:
    return SpecIdentity(
        source="AMAYAMA",
        manufacturer="VOLKSWAGEN",
        vehicle_model="AMAROK",
        market="AMA-BR",
        model_code=model_code,
        amayama_catalog_id="999",
        production_period_raw="2020-2021",
        source_url=f"https://amayama.example/{model_code}",
    )


def _snapshot(
    spec_ref: str,
    *,
    counts: dict[str, int],
    state: SnapshotState = SnapshotState.VALID,
    collection_complete: bool = True,
    structure_hash: str = "s" * 64,
    spec_parts_hash: str = "h" * 64,
    schema_semantic_hash: str = "c" * 64,
    image_hash: str = "i" * 64,
) -> SpecSnapshot:
    return SpecSnapshot(
        snapshot_id=f"snap-{spec_ref[:8]}",
        spec_identity_ref=spec_ref,
        idempotency_key=f"idem-{spec_ref[:8]}",
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="p1",
        normalizer_version="amayama-normalizer-v1",
        fingerprint_version="amayama-fingerprint-v1",
        collection_complete=collection_complete,
        structure_hash=structure_hash,
        spec_parts_hash=spec_parts_hash,
        schema_semantic_hash=schema_semantic_hash,
        image_hash=image_hash,
        state=state,
        counts=counts,
    )


def _manifest(spec_key: str, group_ids: list[str], *, complete: bool = True) -> SpecGroupManifest:
    return SpecGroupManifest(
        spec_key=spec_key,
        source_capture_id="cap-1",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="engine",
                groups=tuple(
                    ManifestGroupRef(group_id=g, source_url=f"https://x/{g}") for g in group_ids
                ),
            ),
        ),
        manifest_complete=complete,
    )


def _codes(report):
    return {finding.code for finding in report.findings}


def test_healthy_corpus_has_no_error_or_warning_findings():
    spec = _identity("H1")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 2, "schemas": 5, "parts": 50})
    manifest = _manifest(key, ["1", "2"])

    report = assess_quality(
        SCOPE,
        [spec],
        {key: snapshot},
        {key: [(RUN_ID, manifest)]},
        {key: {RUN_ID: frozenset({("engine", "1"), ("engine", "2")})}},
    )

    severities = {f.severity for f in report.findings}
    assert Severity.ERROR not in severities
    assert Severity.WARNING not in severities


def test_manifest_snapshot_group_count_mismatch_is_flagged():
    spec = _identity("H2")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 5, "schemas": 5, "parts": 50})
    manifest = _manifest(key, ["1", "2"])  # manifest says 2 groups, snapshot says 5

    report = assess_quality(SCOPE, [spec], {key: snapshot}, {key: [(RUN_ID, manifest)]}, {key: {}})

    mismatch = [f for f in report.findings if f.code == "MANIFEST_SNAPSHOT_GROUP_COUNT_MISMATCH"]
    assert len(mismatch) == 1
    assert mismatch[0].details["manifest_groups"] == 2
    assert mismatch[0].details["snapshot_groups"] == 5


def test_incomplete_or_non_valid_snapshot_is_flagged():
    spec = _identity("H3")
    key = spec.stable_key()
    snapshot = _snapshot(
        key,
        counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 1},
        state=SnapshotState.INCOMPLETE,
        collection_complete=False,
    )

    report = assess_quality(SCOPE, [spec], {key: snapshot}, {key: []}, {key: {}})

    codes = _codes(report)
    assert "SNAPSHOT_NOT_VALID" in codes
    assert "COLLECTION_NOT_COMPLETE" in codes


def test_zero_parts_is_info_only_never_error_or_warning():
    spec = _identity("2HBC34")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 0})
    manifest = _manifest(key, ["1"])

    report = assess_quality(
        SCOPE,
        [spec],
        {key: snapshot},
        {key: [(RUN_ID, manifest)]},
        {key: {RUN_ID: frozenset({("engine", "1")})}},
    )

    zero_parts_findings = [f for f in report.findings if f.code == "SPEC_WITH_ZERO_PARTS"]
    assert len(zero_parts_findings) == 1
    assert zero_parts_findings[0].severity is Severity.INFO


def test_spec_without_snapshot_is_error():
    spec = _identity("H4")
    key = spec.stable_key()

    report = assess_quality(SCOPE, [spec], {}, {key: []}, {key: {}})

    findings = [f for f in report.findings if f.spec_stable_key == key]
    assert len(findings) == 1
    assert findings[0].code == "SPEC_WITHOUT_SNAPSHOT"
    assert findings[0].severity is Severity.ERROR


def test_manifest_group_never_accepted_is_flagged_when_evidence_available():
    spec = _identity("H5")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 2, "schemas": 5, "parts": 50})
    manifest = _manifest(key, ["1", "2"])

    report = assess_quality(
        SCOPE,
        [spec],
        {key: snapshot},
        {key: [(RUN_ID, manifest)]},
        {key: {RUN_ID: frozenset({("engine", "1")})}},  # "2" never ACCEPTED in RUN_ID
    )

    finding = next(f for f in report.findings if f.code == "MANIFEST_GROUPS_NEVER_ACCEPTED")
    assert finding.details["missing_group_keys"] == ["engine/2"]
    assert finding.details["run_id"] == RUN_ID


def test_missing_manifest_is_flagged_separately_from_group_mismatch():
    spec = _identity("H6")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 2, "schemas": 5, "parts": 50})

    report = assess_quality(SCOPE, [spec], {key: snapshot}, {key: []}, {key: {}})

    codes = _codes(report)
    assert "MANIFEST_MISSING_OR_INCOMPLETE" in codes
    assert "MANIFEST_SNAPSHOT_GROUP_COUNT_MISMATCH" not in codes


def test_group_accepted_only_in_old_run_still_flagged_missing_in_current_run():
    """Codex finding #2 — reproduz o bug exato: um grupo esperado pelo manifest
    VIGENTE (run-new) foi ACCEPTED apenas num run ANTIGO (run-old). A união
    entre runs esconderia isso; o comportamento correto é comparar somente
    contra o run do manifest vigente."""
    spec = _identity("H7")
    key = spec.stable_key()
    snapshot = _snapshot(key, counts={"categories": 1, "groups": 2, "schemas": 5, "parts": 50})

    old_manifest = _manifest(key, ["1", "2"])
    new_manifest = SpecGroupManifest(
        spec_key=key,
        source_capture_id="cap-new",
        discovered_at=datetime(2026, 6, 1, tzinfo=UTC),  # mais recente -> vigente
        categories=old_manifest.categories,
        manifest_complete=True,
    )

    manifests_by_spec = {key: [("run-new", new_manifest), ("run-old", old_manifest)]}
    accepted_by_spec_and_run = {
        key: {
            "run-old": frozenset({("engine", "1"), ("engine", "2")}),  # both accepted, old run
            "run-new": frozenset({("engine", "1")}),  # only "1" accepted in the current run
        }
    }

    report = assess_quality(
        SCOPE, [spec], {key: snapshot}, manifests_by_spec, accepted_by_spec_and_run
    )

    finding = next(f for f in report.findings if f.code == "MANIFEST_GROUPS_NEVER_ACCEPTED")
    assert finding.details["run_id"] == "run-new"
    assert finding.details["missing_group_keys"] == ["engine/2"]


def test_unavailable_fingerprint_is_flagged_as_warning():
    """Codex finding #5 — hash NULL (representado por UNAVAILABLE_HASH pelo
    repositório) deve virar um achado explícito, nunca um crash."""
    spec = _identity("H8")
    key = spec.stable_key()
    snapshot = _snapshot(
        key,
        counts={"categories": 1, "groups": 1, "schemas": 1, "parts": 5},
        structure_hash=UNAVAILABLE_HASH,
    )
    manifest = _manifest(key, ["1"])

    report = assess_quality(
        SCOPE,
        [spec],
        {key: snapshot},
        {key: [(RUN_ID, manifest)]},
        {key: {RUN_ID: frozenset({("engine", "1")})}},
    )

    finding = next(f for f in report.findings if f.code == "SNAPSHOT_FINGERPRINT_UNAVAILABLE")
    assert finding.severity is Severity.WARNING
    assert finding.details["unavailable_hashes"] == ["structure_hash"]
