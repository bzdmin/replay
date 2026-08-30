"""Behavioural diff.

Compares what the system did before a change against what it did after,
scenario by scenario. Every divergence here is backed by two real
executions, not by a model's opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .scenarios import Scenario, ScenarioResult


class Verdict(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    BROKE = "broke"
    FIXED = "fixed"


class Outcome(str, Enum):
    """Predicted behaviour versus observed behaviour.

    Borrowed from mutation testing: a proposed change is a deliberate mutant,
    and a scenario is worth running only insofar as it can distinguish the
    original from the mutant. The interesting cells are the two where the
    prediction was wrong.
    """

    CONFIRMED_EFFECT = "confirmed effect"
    CONTAINED = "contained"
    OVER_PROPAGATION = "over-propagation"
    UNDER_PROPAGATION = "under-propagation"
    UNPREDICTED = "unpredicted"

    @property
    def surprising(self) -> bool:
        return self in (Outcome.OVER_PROPAGATION, Outcome.UNDER_PROPAGATION)


@dataclass
class Divergence:
    scenario: Scenario
    before: ScenarioResult
    after: ScenarioResult
    verdict: Verdict

    @property
    def diverged(self) -> bool:
        return self.verdict is not Verdict.UNCHANGED

    @property
    def outcome(self) -> Outcome:
        predicted = (self.scenario.expected_verdict or "").lower()
        if predicted not in ("changed", "unchanged"):
            return Outcome.UNPREDICTED
        predicted_change = predicted == "changed"
        if predicted_change and self.diverged:
            return Outcome.CONFIRMED_EFFECT
        if not predicted_change and not self.diverged:
            return Outcome.CONTAINED
        if predicted_change and not self.diverged:
            return Outcome.UNDER_PROPAGATION
        return Outcome.OVER_PROPAGATION

    def summary(self) -> str:
        return f"{self.before.observed} -> {self.after.observed}"


def _verdict(before: ScenarioResult, after: ScenarioResult) -> Verdict:
    if before.ok and not after.ok:
        return Verdict.BROKE
    if not before.ok and after.ok:
        return Verdict.FIXED
    if before.observed != after.observed:
        return Verdict.CHANGED
    return Verdict.UNCHANGED


def diff(
    scenarios: list[Scenario],
    before: dict[str, ScenarioResult],
    after: dict[str, ScenarioResult],
) -> list[Divergence]:
    """Pair up before/after results and classify each one."""
    divergences: list[Divergence] = []
    for scenario in scenarios:
        b = before[scenario.id]
        a = after[scenario.id]
        divergences.append(
            Divergence(scenario=scenario, before=b, after=a, verdict=_verdict(b, a))
        )
    return divergences
