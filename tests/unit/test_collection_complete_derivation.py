"""T221 — collection_complete: True sse manifesto autoritativo existe e todo
(category_slug, group_id) nele listado está ACCEPTED; False sem manifesto
autoritativo, mesmo com CheckpointEntry ACCEPTED avulsos (contracts/snapshot-contract.md;
data-model.md §17)."""

from datetime import UTC, datetime

from amayama_scraper.checkpoint.checkpoint_entry import CheckpointEntry, CheckpointStatus
from amayama_scraper.domain.manifest import ManifestCategory, ManifestGroupRef, SpecGroupManifest
from amayama_scraper.snapshots.snapshot import compute_collection_complete


def _manifest(**overrides: object) -> SpecGroupManifest:
    defaults: dict[str, object] = dict(
        spec_key="spec-1",
        source_capture_id="cap-1",
        discovered_at=datetime(2026, 8, 26, tzinfo=UTC),
        categories=(
            ManifestCategory(
                category_slug="engine",
                groups=(
                    ManifestGroupRef(group_id="1", source_url="https://x/1"),
                    ManifestGroupRef(group_id="2", source_url="https://x/2"),
                ),
            ),
        ),
        manifest_complete=True,
    )
    defaults.update(overrides)
    return SpecGroupManifest(**defaults)  # type: ignore[arg-type]


def _accepted(group_id: str) -> CheckpointEntry:
    return CheckpointEntry(
        run_id="r",
        spec_key="spec-1",
        category_slug="engine",
        group_id=group_id,
        status=CheckpointStatus.ACCEPTED,
        raw_capture_id="cap",
        completed_at=datetime.now(UTC),
    )


def test_true_when_manifest_authoritative_and_all_groups_accepted():
    assert compute_collection_complete(_manifest(), [_accepted("1"), _accepted("2")]) is True


def test_false_when_some_expected_group_not_yet_accepted():
    assert compute_collection_complete(_manifest(), [_accepted("1")]) is False


def test_false_without_manifest_even_with_all_relevant_checkpoints_accepted():
    assert compute_collection_complete(None, [_accepted("1"), _accepted("2")]) is False


def test_false_when_manifest_is_not_complete_even_with_matching_accepted_entries():
    assert (
        compute_collection_complete(
            _manifest(manifest_complete=False), [_accepted("1"), _accepted("2")]
        )
        is False
    )
