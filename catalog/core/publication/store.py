"""One SQLite transaction owns graph, revision, provenance and mutation receipt."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .errors import PublicationError


class PublicationStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("Publication DB must be a durable file, not :memory:")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS publications (
                    source_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    turtle TEXT
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    principal_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status INTEGER NOT NULL,
                    receipt_json TEXT NOT NULL,
                    PRIMARY KEY (principal_id, source_id, operation, idempotency_key)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _receipt(connection, principal_id, source_id, operation, key, fingerprint):
        row = connection.execute(
            "SELECT fingerprint, status, receipt_json FROM receipts WHERE "
            "principal_id=? AND source_id=? AND operation=? AND idempotency_key=?",
            (principal_id, source_id, operation, key),
        ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise PublicationError(
                409, "idempotency_conflict", "This key was used with a different request"
            )
        return row["status"], json.loads(row["receipt_json"])

    def replay(self, principal_id, source_id, operation, key, fingerprint):
        with self._connection() as connection:
            return self._receipt(connection, principal_id, source_id, operation, key, fingerprint)

    def get(self, source_id: str) -> tuple[dict, str | None] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT state_json, turtle FROM publications WHERE source_id=?", (source_id,)
            ).fetchone()
        return (json.loads(row["state_json"]), row["turtle"]) if row else None

    def all(self) -> list[tuple[dict, str | None]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT state_json, turtle FROM publications ORDER BY source_id"
            ).fetchall()
        return [(json.loads(row["state_json"]), row["turtle"]) for row in rows]

    def mutate(
        self,
        *,
        principal_id: str,
        source_id: str,
        participant_id: str,
        catalog_iri: str,
        operation: str,
        key: str,
        fingerprint: str,
        expected_revision: str,
        publication: dict | None = None,
        turtle: str | None = None,
    ) -> tuple[int, dict]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._receipt(connection, principal_id, source_id, operation, key, fingerprint)
            if replay is not None:
                connection.commit()
                return replay
            row = connection.execute(
                "SELECT revision, state_json FROM publications WHERE source_id=?", (source_id,)
            ).fetchone()
            current = f"r{row['revision']}" if row else "none"
            if current != expected_revision:
                raise PublicationError(
                    412,
                    "revision_mismatch",
                    "Source revision has changed; harvest again against current state",
                )
            if operation == "withdraw" and row is None:
                raise PublicationError(
                    404, "source_unpublished", "Source has no publication to withdraw"
                )
            previous = json.loads(row["state_json"]) if row else {}
            revision_number = row["revision"] + 1 if row else 1
            revision = f"r{revision_number}"
            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            state = {
                "sourceId": source_id,
                "participantId": participant_id,
                "principalId": principal_id,
                "catalogIri": catalog_iri,
                "revision": revision,
                "withdrawn": operation == "withdraw",
                "updatedAt": timestamp,
                "profileIri": (publication or previous).get("profileIri"),
                "profileShapeHash": (publication or previous).get("profileShapeHash"),
                "datasetCount": publication["datasetCount"] if publication else 0,
                "harvest": publication["harvest"] if publication else previous.get("harvest"),
            }
            receipt = {"accepted": True, **state, "operation": operation, "publishedAt": timestamp}
            status = 201 if row is None else 200
            connection.execute(
                "INSERT INTO publications(source_id, revision, state_json, turtle) VALUES(?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET revision=excluded.revision, "
                "state_json=excluded.state_json, turtle=excluded.turtle",
                (source_id, revision_number, json.dumps(state), turtle),
            )
            connection.execute(
                "INSERT INTO receipts(principal_id, source_id, operation, idempotency_key, "
                "fingerprint, status, receipt_json) VALUES(?,?,?,?,?,?,?)",
                (principal_id, source_id, operation, key, fingerprint, status, json.dumps(receipt)),
            )
            connection.commit()
            return status, receipt
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
