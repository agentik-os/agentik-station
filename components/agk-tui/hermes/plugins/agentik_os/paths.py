"""Canonical filesystem resolution for Agentik OS objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug or not _SLUG.fullmatch(slug):
        raise ValueError("name must contain letters or numbers")
    return slug


def _contained(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    candidate = candidate.resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise ValueError("resolved path escapes its authorized root")
    return candidate


@dataclass(frozen=True)
class PathResolver:
    environment: str
    home: Path

    @classmethod
    def current(cls, environment: str) -> "PathResolver":
        return cls(environment=environment, home=Path.home())

    def client(self, slug: str) -> Path:
        if self.environment not in {"mission", "collective"}:
            raise PermissionError("clients belong to the Mission environment")
        return _contained(
            self.home / "workspace" / "clients",
            self.home / "workspace" / "clients" / normalize_slug(slug),
        )

    def project(self, slug: str, *, client_slug: str | None = None) -> Path:
        slug = normalize_slug(slug)
        if self.environment in {"mission", "collective"}:
            if not client_slug:
                raise ValueError("open a client before creating a project")
            root = self.client(client_slug) / "projects"
        elif self.environment == "agentik":
            root = self.home / "workspace" / "projects"
        elif self.environment == "private":
            root = self.home / "workspace" / "projects"
        else:
            raise PermissionError("Operator does not own business projects")
        return _contained(root, root / slug)

    def mission(self, slug: str, *, project_path: Path) -> Path:
        root = _contained(project_path, project_path / "missions")
        return _contained(root, root / normalize_slug(slug))

    def resolve(self, object_type: str, *, slug: str | None = None,
                client_slug: str | None = None, project_path: Path | None = None,
                scope_path: Path | None = None) -> Path:
        """Resolve every canonical storage class without creating it.

        Callers must resolve ownership and scope before mutation. Returning a
        path never grants authority and never creates files or directories.
        """
        kind = object_type.strip().lower().replace("-", "_")
        if kind == "client":
            if not slug: raise ValueError("client resolution requires a slug")
            return self.client(slug)
        if kind == "project":
            if not slug: raise ValueError("project resolution requires a slug")
            return self.project(slug, client_slug=client_slug)
        if kind == "mission":
            if not slug or project_path is None: raise ValueError("mission resolution requires slug and project_path")
            return self.mission(slug, project_path=project_path)
        if kind == "hermes_state":
            return _contained(self.home, self.home / ".hermes")
        if kind == "workspace":
            return _contained(self.home, self.home / "workspace")
        if kind in {"knowledge", "artifact"}:
            workspace = self.resolve("workspace")
            root = _contained(workspace, scope_path) if scope_path else workspace
            directory = "knowledge" if kind == "knowledge" else "artifacts"
            return _contained(root, root / directory)
        if kind == "secrets":
            return _contained(self.home, self.home / ".secrets")
        if kind in {"runtime", "logs", "backups"}:
            root = Path("/var/agentik") / kind
            return _contained(root, root / self.environment)
        if kind == "os_registry":
            return Path("/opt/agentik/os-registry")
        if kind == "operator_admin":
            if self.environment != "operator": raise PermissionError("operator administration belongs to Operator")
            return _contained(self.home, self.home / "admin")
        raise ValueError(f"unknown Agentik path object type: {object_type}")


def create_client_layout(path: Path, *, object_id: str, name: str, slug: str) -> None:
    for child in (
        ".client", "projects", "knowledge", "missions", "artifacts",
        "deployments", "automation", "infrastructure", "tmp",
    ):
        (path / child).mkdir(parents=True, exist_ok=True)
    (path / "CLIENT.md").write_text(
        f"# {name}\n\nClient ID: `{object_id}`\nSlug: `{slug}`\n",
        encoding="utf-8",
    )


def create_project_layout(path: Path, *, object_id: str, name: str, slug: str) -> None:
    for child in (".agentik", "repo", "knowledge", "missions", "artifacts", "docs", "tmp"):
        (path / child).mkdir(parents=True, exist_ok=True)
    (path / "PROJECT.md").write_text(
        f"# {name}\n\nProject ID: `{object_id}`\nSlug: `{slug}`\n",
        encoding="utf-8",
    )


def create_mission_layout(path: Path, *, object_id: str, name: str) -> None:
    for child in ("tasks", "artifacts", "evidence", "reports"):
        (path / child).mkdir(parents=True, exist_ok=True)
    (path / "mission.yaml").write_text(
        f"schema_version: 1\nid: {object_id}\nname: {name!r}\nstatus: planned\n",
        encoding="utf-8",
    )
