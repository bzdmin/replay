"""Serialising a rehearsal.

Turns a RehearsalReport into plain JSON-safe data so it can be streamed to a
browser, cached to disk, or replayed later without re-running the agents.
"""

from __future__ import annotations

from typing import Any

from .pipeline import RehearsalReport


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
