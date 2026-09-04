"""Environment-specific business objects backed by the canonical store."""

from __future__ import annotations

from .paths import normalize_slug
from .store import ControlStore


DOMAIN_COMMANDS = {
    "agentik": ("org", "portfolio", "product", "build", "release", "content", "growth", "community", "research"),
    "mission": ("deliverable", "deploy", "report"),
    "collective": ("deliverable", "deploy", "report"),
    "private": ("journal", "decision", "routine", "idea", "review"),
}

DESCRIPTIONS = {
    "org": "Manage Agentik organization status, goals, priorities and roadmap.",
    "portfolio": "Manage the Agentik portfolio.",
    "product": "Manage products, roadmaps, backlogs and features.",
    "build": "Track engineering builds and delivery work.",
    "release": "Track product release preparation and publication.",
    "content": "Manage content ideas, drafts, calendar and publication.",
    "growth": "Track growth opportunities, experiments and metrics.",
    "community": "Track community work, events and opportunities.",
    "research": "Create and track research work and reports.",
    "deliverable": "Create, review, approve and track client deliverables.",
    "deploy": "Track scoped client deployments and rollback requests.",
    "report": "Create and track client reports.",
    "journal": "Create and review private journal records.",
    "decision": "Create, analyze and review private decisions.",
    "routine": "Create, start, complete and review routines.",
    "idea": "Capture, develop and promote private ideas.",
    "review": "Create and track private reviews.",
}

_TRANSITIONS = {
    "start": "running", "pause": "paused", "resume": "running",
    "complete": "completed", "cancel": "cancelled", "archive": "archived",
    "approve": "approved", "reject": "rejected", "publish": "published",
    "review": "in-review", "promote": "promoted",
}


class DomainCommandService:
    def __init__(self, environment: str, store: ControlStore):
        self.environment = "mission" if environment == "collective" else environment
        self.store = store

    def dispatch(self, kind: str, argv: list[str]) -> str:
        action = argv[0].lower() if argv else "list"
        rest = argv[1:]
        if action in {"new", "idea", "experiment", "event", "draft", "prepare"}:
            if not rest:
                return f"Usage: /{kind} {action} <name>"
            return self._create(kind, " ".join(rest), action)
        if action in {"list", "status", "goals", "metrics", "priorities", "roadmap", "backlog", "calendar", "opportunities", "history", "today", "week", "month", "progress"}:
            return self._list(kind, rest[0] if rest else None)
        if action in _TRANSITIONS:
            if not rest:
                return f"Usage: /{kind} {action} <id-or-slug>"
            obj = self.store.get(self.environment, kind, rest[0])
            if not obj:
                return f"{kind.title()} not found: {rest[0]}"
            obj = self.store.transition(obj, _TRANSITIONS[action])
            return f"{kind.title()} {obj.id} → {obj.status}."
        if action in {"open", "info"}:
            if not rest:
                return f"Usage: /{kind} {action} <id-or-slug>"
            obj = self.store.get(self.environment, kind, rest[0])
            if not obj:
                return f"{kind.title()} not found: {rest[0]}"
            return f"{kind.upper()} · {obj.name}\nID: {obj.id}\nStatus: {obj.status}\nParent: {obj.parent_id or '—'}"
        return f"Unknown action `{action}` for /{kind}. Use new, list, status, open, start, pause, resume, complete or archive."

    def _create(self, kind: str, name: str, source_action: str) -> str:
        slug = normalize_slug(name)
        obj = self.store.create(
            environment=self.environment, kind=kind, slug=slug, name=name,
            status="planned", metadata={"created_via": source_action},
        )
        return f"{kind.title()} created: {obj.name} ({obj.id})"

    def _list(self, kind: str, target: str | None) -> str:
        if target:
            obj = self.store.get(self.environment, kind, target)
            if obj:
                return f"{kind.upper()} · {obj.name}\nID: {obj.id}\nStatus: {obj.status}"
        objects = self.store.list(self.environment, kind)
        if not objects:
            return f"No {kind} records in the current authorized scope."
        return "\n".join([f"{kind.upper()}S"] + [f"• {o.name} · {o.id} · {o.status}" for o in objects])
