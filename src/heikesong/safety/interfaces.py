"""Safety gate required before any physical motion command."""

from __future__ import annotations

from typing import Protocol


class SafetySupervisor(Protocol):
    def motion_allowed(self) -> bool: ...

    def stop_reason(self) -> str | None: ...
