"""Serialising a rehearsal.

Turns a RehearsalReport into plain JSON-safe data so it can be streamed to a
browser, cached to disk, or replayed later without re-running the agents.
"""

from __future__ import annotations

from typing import Any

from .pipeline import RehearsalReport

# Models reach for em and en dashes constantly. Normalise them to a plain
# hyphen on the way out so the page reads consistently, whatever the agents
# happened to write this run.
# Written as escapes on purpose. Spelled literally, a find-and-replace over the
# repository strips the characters out of the table that replaces them, and the
# filter silently becomes a no-op.
_DASHES = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "−": "-",  # minus sign
}


def clean(text: Any) -> Any:
    """Normalise dash characters in any string passing through to the page."""
    if not isinstance(text, str):
        return text
    for bad, good in _DASHES.items():
        text = text.replace(bad, good)
    return text


def clean_deep(value: Any) -> Any:
    """Apply :func:`clean` to every string in a nested structure."""
    if isinstance(value, dict):
        return {k: clean_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_deep(v) for v in value]
    return clean(value)


def divergence_to_dict(d: Any) -> dict[str, Any]:
    return {
        "id": d.scenario.id,
        "name": d.scenario.name,
        "call": f"{d.scenario.module}.{d.scenario.function}",
        "kwargs": d.scenario.kwargs,
        "predicted": d.scenario.expected_verdict,
        "because": d.scenario.because,
        "before": d.before.observed,
        "after": d.after.observed,
        "verdict": d.verdict.value,
        "outcome": d.outcome.value,
        "surprising": d.outcome.surprising,
        "duration_ms": d.before.duration_ms + d.after.duration_ms,
    }


def report_to_dict(report: RehearsalReport) -> dict[str, Any]:
    """Flatten a completed rehearsal into JSON-safe data."""
    return clean_deep(_report_to_dict(report))


def _report_to_dict(report: RehearsalReport) -> dict[str, Any]:
    verification = report.verification
    return {
        "request": report.request,
        "impact": {
            "edits": [
                {
                    "path": e.path,
                    "find": e.find,
                    "replace": e.replace,
                    "rationale": e.rationale,
                }
                for e in report.impact.edits
            ],
            "affected_components": report.impact.affected_components,
            "suspected_duplicates": report.impact.suspected_duplicates,
            "notes": report.impact.notes,
        },
        "applied": [
            {"path": a.path, "occurrences": a.occurrences} for a in report.applied
        ],
        "divergences": [divergence_to_dict(d) for d in report.divergences],
        "surprises": [divergence_to_dict(d) for d in report.surprises],
        "discarded": [
            {"id": s.id, "name": s.name, "reason": why} for s, why in report.discarded
        ],
        "verification": (
            {
                "overall_risk": verification.overall_risk,
                "summary": verification.summary,
                "challenges": [
                    {
                        "scenario_id": c.scenario_id,
                        "severity": c.severity,
                        "claim": c.claim,
                        "rule_violated": c.rule_violated,
                        "evidence": c.evidence,
                    }
                    for c in verification.challenges
                ],
            }
            if verification is not None
            else None
        ),
        "stats": {
            "scenarios": len(report.scenarios),
            "executions": report.executions,
            "changed": len(report.changed),
            "surprises": len(report.surprises),
        },
    }
