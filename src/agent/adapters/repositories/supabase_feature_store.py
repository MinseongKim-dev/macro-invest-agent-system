"""PostgreSQL-backed feature store repository for Supabase.

Implements FeatureStoreRepositoryContract using psycopg2 for PostgreSQL
access. Compatible with Supabase hosted PostgreSQL and any standard
PostgreSQL 14+ instance.

Setup:
    1. Set SUPABASE_DB_URL environment variable
    2. Call create_tables() once to set up the schema
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg2.extensions import connection as Psycopg2Connection

from src.core.contracts.feature_store_repository import FeatureStoreRepositoryContract
from src.core.logging.logger import get_logger
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature
from src.pipelines.ingestion.models import FeatureSnapshot

_log = get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    country         TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    features_count  INTEGER NOT NULL,
    features_json   JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_country_ingested
    ON feature_snapshots (country, ingested_at DESC);
"""


class SupabaseFeatureStore(FeatureStoreRepositoryContract):
    """PostgreSQL-backed feature store for Supabase.

    Args:
        db_url: PostgreSQL connection string.
            Format: postgresql://user:password@host:port/dbname
            If None, reads from SUPABASE_DB_URL environment variable.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self._db_url = db_url or os.environ.get("SUPABASE_DB_URL", "")
        if not self._db_url:
            raise RuntimeError(
                "SupabaseFeatureStore requires a database URL. "
                "Set the SUPABASE_DB_URL environment variable or pass db_url directly."
            )
        self._conn = None

    def _get_connection(self) -> Psycopg2Connection:
        """Get or create a database connection."""
        if self._conn is None or self._conn.closed:
            try:
                import psycopg2  # type: ignore[import-untyped]

                self._conn = psycopg2.connect(self._db_url)
                self._conn.autocommit = True
            except ImportError as exc:
                raise RuntimeError(
                    "psycopg2 is required for SupabaseFeatureStore. "
                    "Install with: pip install psycopg2-binary"
                ) from exc
        return self._conn

    def create_tables(self) -> None:
        """Create the feature_snapshots table if it doesn't exist."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        _log.info("supabase_tables_created")

    def _features_to_json(self, features: list[MacroFeature]) -> list[dict]:  # type: ignore[type-arg]
        return [
            {
                "indicator_type": f.indicator_type.value,
                "source": f.source.value,
                "value": f.value,
                "timestamp": f.timestamp.isoformat(),
                "frequency": f.frequency.value,
                "country": f.country,
                "metadata": f.metadata,
            }
            for f in features
        ]

    def _json_to_features(self, features_json: list[dict]) -> list[MacroFeature]:  # type: ignore[type-arg]
        features = []
        for d in features_json:
            try:
                features.append(
                    MacroFeature(
                        indicator_type=MacroIndicatorType(d["indicator_type"]),
                        source=MacroSourceType(d["source"]),
                        value=d["value"],
                        timestamp=datetime.fromisoformat(d["timestamp"]),
                        frequency=DataFrequency(d["frequency"]),
                        country=d.get("country", "US"),
                        metadata=d.get("metadata", {}),
                    )
                )
            except (KeyError, ValueError) as exc:
                _log.warning("feature_deserialize_error", error=str(exc))
                continue
        return features

    async def save_snapshot(self, snapshot: object) -> None:
        """Persist a FeatureSnapshot to Supabase PostgreSQL."""
        assert isinstance(snapshot, FeatureSnapshot)
        conn = self._get_connection()
        features_json = self._features_to_json(snapshot.features)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feature_snapshots
                    (snapshot_id, country, source_id, ingested_at, features_count, features_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (snapshot_id) DO UPDATE SET
                    features_json = EXCLUDED.features_json,
                    features_count = EXCLUDED.features_count,
                    ingested_at = EXCLUDED.ingested_at
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.country,
                    snapshot.source_id,
                    snapshot.ingested_at,
                    snapshot.features_count,
                    json.dumps(features_json),
                ),
            )
        _log.info(
            "snapshot_saved",
            snapshot_id=snapshot.snapshot_id,
            country=snapshot.country,
            features_count=snapshot.features_count,
        )

    async def get_latest_snapshot(self, country: str) -> FeatureSnapshot | None:
        """Retrieve the most recent snapshot for a country."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id, country, source_id, ingested_at,
                       features_count, features_json
                FROM feature_snapshots
                WHERE country = %s
                ORDER BY ingested_at DESC
                LIMIT 1
                """,
                (country,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            sid, ctry, src_id, ingested_at, feat_count, feat_json = row
            features = self._json_to_features(
                feat_json if isinstance(feat_json, list) else json.loads(feat_json)
            )
            return FeatureSnapshot(
                snapshot_id=sid,
                country=ctry,
                source_id=src_id,
                ingested_at=ingested_at,
                features=features,
            )

    async def list_snapshots(self, country: str, limit: int = 10) -> Sequence[FeatureSnapshot]:
        """List the most recent snapshots for a country."""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT snapshot_id, country, source_id, ingested_at,
                       features_count, features_json
                FROM feature_snapshots
                WHERE country = %s
                ORDER BY ingested_at DESC
                LIMIT %s
                """,
                (country, limit),
            )
            rows = cur.fetchall()

        snapshots = []
        for row in rows:
            sid, ctry, src_id, ingested_at, feat_count, feat_json = row
            features = self._json_to_features(
                feat_json if isinstance(feat_json, list) else json.loads(feat_json)
            )
            snapshots.append(
                FeatureSnapshot(
                    snapshot_id=sid,
                    country=ctry,
                    source_id=src_id,
                    ingested_at=ingested_at,
                    features=features,
                )
            )
        return snapshots

    def close(self) -> None:
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            _log.info("supabase_connection_closed")
