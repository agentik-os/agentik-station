from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import LIVE_ROOTS


@dataclass(frozen=True)
class LayoutPaths:
    config: Path
    software: Path
    runtime: Path
    varlib: Path
    log: Path
    backups: Path
    run: Path
    systemd: Path
    bin: Path
    test_mode: bool = False

    @classmethod
    def live(cls) -> "LayoutPaths":
        return cls(**LIVE_ROOTS, test_mode=False)

    @classmethod
    def under(cls, prefix: Path) -> "LayoutPaths":
        prefix = Path(prefix).absolute()

        def p(value: Path) -> Path:
            return prefix / value.relative_to("/")

        mapped = {key: p(value) for key, value in LIVE_ROOTS.items()}
        return cls(**mapped, test_mode=True)

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return (
            self.config,
            self.software,
            self.runtime,
            self.varlib,
            self.log,
            self.backups,
            self.run,
            self.systemd,
            self.bin,
        )

    @property
    def releases(self) -> Path:
        return self.software / "releases"

    @property
    def staging(self) -> Path:
        return self.software / ".staging"

    @property
    def current(self) -> Path:
        return self.software / "current"

    @property
    def receipts(self) -> Path:
        return self.varlib / "receipts"

    @property
    def observed(self) -> Path:
        return self.varlib / "observed"

    @property
    def zones_state(self) -> Path:
        return self.varlib / "zones"
