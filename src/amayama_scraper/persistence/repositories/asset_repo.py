"""asset_resolution_repo — data-model.md §10 (ResolvedImage)."""

from __future__ import annotations

import sqlite3

from amayama_scraper.assets.types import ResolvedImage


def save_resolved_image(conn: sqlite3.Connection, image: ResolvedImage) -> None:
    conn.execute(
        """
        INSERT INTO asset_resolution (
            spec_identity_ref, origin_spec_ref, image_url_or_ref, is_fallback,
            resolved_within_cluster_key
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (spec_identity_ref) DO UPDATE SET
            origin_spec_ref = excluded.origin_spec_ref,
            image_url_or_ref = excluded.image_url_or_ref,
            is_fallback = excluded.is_fallback,
            resolved_within_cluster_key = excluded.resolved_within_cluster_key
        """,
        (
            image.spec_identity_ref,
            image.origin_spec_ref,
            image.image_url_or_ref,
            int(image.is_fallback),
            image.resolved_within_cluster_key,
        ),
    )


def get_resolved_image(conn: sqlite3.Connection, spec_identity_ref: str) -> ResolvedImage | None:
    row = conn.execute(
        "SELECT * FROM asset_resolution WHERE spec_identity_ref = ?", (spec_identity_ref,)
    ).fetchone()
    if row is None:
        return None
    return ResolvedImage(
        spec_identity_ref=row["spec_identity_ref"],
        origin_spec_ref=row["origin_spec_ref"],
        image_url_or_ref=row["image_url_or_ref"],
        is_fallback=bool(row["is_fallback"]),
        resolved_within_cluster_key=row["resolved_within_cluster_key"],
    )
