"""asset_resolution_repo — persiste/recupera ResolvedImage (data-model.md §10).

Não listado como task de teste dedicada em tasks.md (T194/T195 não têm um
T-teste entre si) — cobertura mínima adicionada por consistência com a
exigência de testes da Constitution para toda regra estrutural.
"""

from amayama_scraper.assets.types import ResolvedImage
from amayama_scraper.persistence.db import connect
from amayama_scraper.persistence.migrations.runner import run_migrations
from amayama_scraper.persistence.repositories.asset_repo import (
    get_resolved_image,
    save_resolved_image,
)


def _conn():
    conn = connect(":memory:")
    run_migrations(conn)
    for stable_key in ("spec-1", "spec-2"):
        conn.execute(
            "INSERT INTO spec_registry (stable_key, source, manufacturer, vehicle_model, "
            "market, model_code, amayama_catalog_id, production_period_raw, source_url) "
            "VALUES (?, 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')",
            (stable_key,),
        )
    return conn


def test_own_image_round_trips():
    conn = _conn()
    image = ResolvedImage(
        spec_identity_ref="spec-1",
        origin_spec_ref="spec-1",
        image_url_or_ref="https://x/a.jpg",
        is_fallback=False,
    )
    save_resolved_image(conn, image)
    assert get_resolved_image(conn, "spec-1") == image


def test_fallback_image_preserves_origin_and_cluster_key():
    conn = _conn()
    image = ResolvedImage(
        spec_identity_ref="spec-2",
        origin_spec_ref="spec-1",
        image_url_or_ref="https://x/a.jpg",
        is_fallback=True,
        resolved_within_cluster_key="cluster-a",
    )
    save_resolved_image(conn, image)
    fetched = get_resolved_image(conn, "spec-2")
    assert fetched is not None
    assert fetched.is_fallback is True
    assert fetched.origin_spec_ref == "spec-1"
    assert fetched.resolved_within_cluster_key == "cluster-a"


def test_missing_returns_none():
    conn = _conn()
    assert get_resolved_image(conn, "nonexistent") is None
