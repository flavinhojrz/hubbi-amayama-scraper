"""T215 — finalize_spec_entry() recusa executar (não gera snapshot) sem manifesto
autoritativo (contracts/snapshot-contract.md PRECONDIÇÃO 1; data-model.md §15/§17)."""

from amayama_scraper.snapshots.finalize import plan_finalization


class _NoManifestRepo:
    def get_authoritative(self, spec_key: str, run_id: str):
        return None


class _UnusedCheckpointRepo:
    def list_accepted(self, run_id: str, spec_key: str):
        raise AssertionError("should never be called when no authoritative manifest exists")


class _UnusedCaptureRepo:
    def save(self, capture):
        raise AssertionError

    def get(self, capture_id: str):
        raise AssertionError


class _UnusedBlobStore:
    def get_or_create(self, content_hash: str, raw_content: bytes):
        raise AssertionError

    def read(self, content_hash: str):
        raise AssertionError


def test_plan_finalization_returns_none_without_authoritative_manifest():
    plan = plan_finalization(
        spec_key="spec-1",
        run_id="run-1",
        spec_identity_ref="spec-1",
        manifest_repo=_NoManifestRepo(),
        checkpoint_repo=_UnusedCheckpointRepo(),
        capture_repo=_UnusedCaptureRepo(),
        blob_store=_UnusedBlobStore(),
    )
    assert plan is None
