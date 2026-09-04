"""Transactional local repository for Agentik OS control objects."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


PREFIX = {
    "client": "CLI", "project": "PRJ", "mission": "MIS", "task": "TSK", "run": "RUN",
    "org": "ORG", "portfolio": "POR", "product": "PRO", "build": "BLD",
    "release": "REL", "content": "CON", "growth": "GRO", "community": "COM",
    "research": "RES", "deliverable": "DEL", "deploy": "DEP", "report": "REP",
    "journal": "JOU", "decision": "DEC", "routine": "ROU", "idea": "IDE",
    "review": "REV",
}


@dataclass(frozen=True)
class ControlObject:
    id: str
    environment: str
    kind: str
    slug: str
    name: str
    parent_id: str | None
    status: str
    path: str | None
    metadata: dict


class ControlStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    name TEXT NOT NULL,
                    parent_id TEXT REFERENCES objects(id),
                    status TEXT NOT NULL,
                    path TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(environment, kind, parent_id, slug)
                );
                CREATE INDEX IF NOT EXISTS idx_objects_scope
                    ON objects(environment, kind, parent_id, status);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_objects_unique_scope
                    ON objects(environment, kind, COALESCE(parent_id, ''), slug);
                CREATE TABLE IF NOT EXISTS contexts (
                    context_key TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    client_id TEXT,
                    project_id TEXT,
                    mission_id TEXT,
                    task_id TEXT,
                    run_id TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    environment TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(contexts)")}
            if "run_id" not in columns:
                db.execute("ALTER TABLE contexts ADD COLUMN run_id TEXT")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> ControlObject | None:
        if row is None:
            return None
        return ControlObject(
            id=row["id"], environment=row["environment"], kind=row["kind"],
            slug=row["slug"], name=row["name"], parent_id=row["parent_id"],
            status=row["status"], path=row["path"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def create(self, *, environment: str, kind: str, slug: str, name: str,
               parent_id: str | None = None, status: str = "active",
               path: str | None = None, metadata: dict | None = None) -> ControlObject:
        now = time.time()
        object_id = f"{PREFIX[kind]}-{uuid.uuid4().hex[:10].upper()}"
        with self.connect() as db:
            if parent_id is not None:
                parent = db.execute(
                    "SELECT environment FROM objects WHERE id=?", (parent_id,)
                ).fetchone()
                if parent is None:
                    raise ValueError(f"parent object does not exist: {parent_id}")
                if parent["environment"] != environment:
                    raise PermissionError("parent object belongs to another environment")
            db.execute(
                "INSERT INTO objects VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (object_id, environment, kind, slug, name, parent_id, status,
                 path, json.dumps(metadata or {}, sort_keys=True), now, now),
            )
            db.execute(
                "INSERT INTO events(environment,action,object_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                (environment, f"{kind}.created", object_id,
                 json.dumps({"slug": slug, "parent_id": parent_id}, sort_keys=True), now),
            )
        return self.get(environment, kind, object_id)

    def get(self, environment: str, kind: str, target: str,
            parent_id: str | None = None) -> ControlObject | None:
        parent_sql = ""
        args: list[object] = [environment, kind, target]
        # Canonical IDs are globally unambiguous inside an environment. Slugs
        # are only unambiguous inside their parent scope.
        if not target.startswith(f"{PREFIX[kind]}-") and parent_id is not None:
            parent_sql = " AND parent_id=?"
            args.append(parent_id)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM objects WHERE environment=? AND kind=? AND (id=? OR slug=?)"
                + parent_sql + " ORDER BY updated_at DESC LIMIT 1",
                [environment, kind, target, target, *args[3:]],
            ).fetchone()
        return self._row(row)

    def list(self, environment: str, kind: str, parent_id: str | None = None) -> list[ControlObject]:
        sql = "SELECT * FROM objects WHERE environment=? AND kind=?"
        args: list[object] = [environment, kind]
        if parent_id is not None:
            sql += " AND parent_id=?"
            args.append(parent_id)
        sql += " ORDER BY updated_at DESC, name"
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [self._row(row) for row in rows if row is not None]

    def transition(self, obj: ControlObject, status: str) -> ControlObject:
        now = time.time()
        with self.connect() as db:
            db.execute("UPDATE objects SET status=?, updated_at=? WHERE id=?", (status, now, obj.id))
            db.execute(
                "INSERT INTO events(environment,action,object_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                (obj.environment, f"{obj.kind}.{status}", obj.id, "{}", now),
            )
        return self.get(obj.environment, obj.kind, obj.id)

    def update_metadata(self, obj: ControlObject, updates: dict) -> ControlObject:
        """Merge non-secret control metadata and emit an auditable event."""
        metadata = dict(obj.metadata)
        metadata.update(updates)
        now = time.time()
        with self.connect() as db:
            db.execute(
                "UPDATE objects SET metadata_json=?, updated_at=? WHERE id=?",
                (json.dumps(metadata, sort_keys=True), now, obj.id),
            )
            db.execute(
                "INSERT INTO events(environment,action,object_id,payload_json,created_at) VALUES(?,?,?,?,?)",
                (obj.environment, f"{obj.kind}.metadata.updated", obj.id,
                 json.dumps({"keys": sorted(updates)}, sort_keys=True), now),
            )
        return self.get(obj.environment, obj.kind, obj.id)

    def context(self, key: str, environment: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM contexts WHERE context_key=?", (key,)).fetchone()
        if not row:
            return {"environment": environment, "client_id": None, "project_id": None,
                    "mission_id": None, "task_id": None, "run_id": None}
        return dict(row)

    def set_context(self, key: str, environment: str, **updates: str | None) -> dict:
        current = self.context(key, environment)
        current.update(updates)
        with self.connect() as db:
            db.execute("""
                INSERT INTO contexts(context_key,environment,client_id,project_id,mission_id,task_id,run_id,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(context_key) DO UPDATE SET
                environment=excluded.environment, client_id=excluded.client_id,
                project_id=excluded.project_id, mission_id=excluded.mission_id,
                task_id=excluded.task_id, run_id=excluded.run_id, updated_at=excluded.updated_at
            """, (key, environment, current.get("client_id"), current.get("project_id"),
                  current.get("mission_id"), current.get("task_id"), current.get("run_id"), time.time()))
        return self.context(key, environment)

    def clear_context(self, key: str, environment: str) -> dict:
        return self.set_context(key, environment, client_id=None, project_id=None,
                                mission_id=None, task_id=None, run_id=None)

    def lineage(self, obj: ControlObject) -> list[ControlObject]:
        """Return root→object lineage, rejecting broken or cross-env chains."""
        chain = [obj]
        seen = {obj.id}
        current = obj
        while current.parent_id:
            with self.connect() as db:
                row = db.execute("SELECT * FROM objects WHERE id=?", (current.parent_id,)).fetchone()
            parent = self._row(row)
            if parent is None:
                raise ValueError(f"broken object lineage at {current.parent_id}")
            if parent.environment != obj.environment:
                raise PermissionError("object lineage crosses an environment boundary")
            if parent.id in seen:
                raise ValueError("cyclic object lineage")
            seen.add(parent.id); chain.append(parent); current = parent
        return list(reversed(chain))
