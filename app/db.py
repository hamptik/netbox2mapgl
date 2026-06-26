"""SQLite persistence layer for the NetBox cache.

Tables hold raw NetBox objects as JSON text keyed by the NetBox id. SQLite runs
in WAL mode with a busy timeout so the request handlers can read concurrently
while the refresher thread writes. This module is the only place that issues
SQL, which keeps the (intentionally small) set of table names in a single
whitelist instead of being interpolated from callers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from app.cache import CacheSnapshot

log = logging.getLogger(__name__)

#: Every cache "kind" maps to exactly one table. Acting as an allow-list keeps
#: table names out of string interpolation.
TABLES: dict[str, str] = {
    "devices": "nb_devices",
    "locations": "nb_locations",
    "cables": "nb_cables",
    "vms": "nb_vms",
    "traces": "nb_traces",
    "interfaces": "nb_interfaces",
}

#: A cache kind maps NetBox id -> raw JSON payload. Most payloads are objects
#: (``dict[str, Any]``) but traces are arrays (``list[Any]``), so the value
#: type stays ``Any`` to cover both uniformly.
CacheKind = dict[int, Any]


class Database:
    """Thin wrapper around sqlite3 connections for the cache tables."""

    def __init__(self, path: str) -> None:
        self._path = path

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = sqlite3.connect(self._path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def init_schema(self) -> None:
        """Create the cache tables if they do not yet exist."""
        log.info("Initializing DB schema at %s", self._path)
        with self._cursor() as cur:
            for table in TABLES.values():
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY,
                        data TEXT NOT NULL,
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                    """
                )
        log.info("DB schema ensured")

    def write_bulk(self, kind: str, rows: Iterable[tuple[int, Any]]) -> None:
        """Upsert a full set of rows for a cache kind.

        Rows absent from ``rows`` but present in the table are deleted, so after
        the call the table mirrors the provided dataset exactly.
        """
        table = TABLES.get(kind)
        if table is None:
            raise ValueError(f"Unknown cache kind: {kind!r}")

        materialized = list(rows)
        if not materialized:
            return

        with self._cursor() as cur:
            cur.execute(f"SELECT id FROM {table}")
            existing_ids = {row[0] for row in cur.fetchall()}
            new_ids = {row[0] for row in materialized}

            stale_ids = existing_ids - new_ids
            if stale_ids:
                placeholders = ",".join(["?"] * len(stale_ids))
                cur.execute(
                    f"DELETE FROM {table} WHERE id IN ({placeholders})",
                    list(stale_ids),
                )

            cur.executemany(
                f"""
                INSERT INTO {table} (id, data, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE
                SET data = excluded.data, updated_at = datetime('now')
                """,
                [(row_id, json.dumps(payload)) for row_id, payload in materialized],
            )
        log.debug("Wrote %d rows to %s", len(materialized), table)

    def load_all(self) -> dict[str, CacheKind]:
        """Load every cache kind from the database into in-memory dicts."""
        result: dict[str, CacheKind] = {kind: {} for kind in TABLES}
        with self._cursor() as cur:
            for kind, table in TABLES.items():
                cur.execute(f"SELECT id, data FROM {table}")
                for row in cur.fetchall():
                    result[kind][row[0]] = json.loads(row[1])

        log.info(
            "Loaded from DB: devices=%d locations=%d cables=%d vms=%d traces=%d interfaces=%d",
            len(result["devices"]),
            len(result["locations"]),
            len(result["cables"]),
            len(result["vms"]),
            len(result["traces"]),
            len(result["interfaces"]),
        )
        return result

    def load_snapshot(self) -> CacheSnapshot:
        """Load all data from the database as a :class:`CacheSnapshot`."""
        data = self.load_all()
        return CacheSnapshot(
            devices=data["devices"],
            locations=data["locations"],
            cables=data["cables"],
            vms=data["vms"],
            traces=data["traces"],
            interfaces=data["interfaces"],
        )

    def counts(self) -> dict[str, int]:
        """Return ``{kind: row_count}`` for all cache tables."""
        result: dict[str, int] = {}
        with self._cursor() as cur:
            for kind, table in TABLES.items():
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                result[kind] = cur.fetchone()[0]
        return result
