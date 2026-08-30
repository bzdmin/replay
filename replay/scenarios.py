"""Scenario and change definitions.

A Scenario is one concrete, executable observation of system behaviour.
A Change is a set of edits applied to the repository before re-observing.

Both are plain data. Right now they are written by hand; from stage two
the Scenario Agent and the change parser produce them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scenario:
    """One executable observation of the system.

    A scenario is a falsifiable prediction, not just a function call. It
    declares in advance whether this observation *should* move under the
    proposed change, and which rule says so. Comparing that prediction against
    what actually happened is what turns a diff into a finding.
    """

    id: str
    name: str
    module: str
    function: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    expected_verdict: str | None = None  # "changed" | "unchanged" | None
    because: str = ""

    def to_spec(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "function": self.function,
            "kwargs": self.kwargs,
        }


@dataclass(frozen=True)
class Edit:
    """A single literal substitution inside one file.

    By default an edit must match exactly once. A `find` string that appears
    more than once is ambiguous -- the agent meant one of them, and we cannot
    know which -- so it is rejected rather than applied to all of them. Set
    `allow_multiple` only when replacing every occurrence is genuinely intended.
    """

    path: str
    find: str
    replace: str
    allow_multiple: bool = False


@dataclass(frozen=True)
class Change:
    """A proposed change: what the engineer asked for, and the edits it implies."""

    description: str
    edits: list[Edit]


@dataclass
class ScenarioResult:
    """What actually happened when a scenario was executed."""

    scenario_id: str
    ok: bool
    value: str | None
    error: str | None
    exit_code: int
    duration_ms: int

    @property
    def observed(self) -> str:
        return self.value if self.ok else f"<{self.error}>"
