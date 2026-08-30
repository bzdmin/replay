"""The rehearsal pipeline.

Ties the three agents and the deterministic runner together into one pass:

    understand -> map -> design observations -> run before -> apply -> run after
    -> compare -> challenge -> report

Progress is reported through a callback so a CLI or a web UI can show the
rehearsal happening rather than waiting on a spinner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .agents import (
    ImpactAnalysis,
    ScenarioPlan,
    VerificationReport,
    impact_agent,
    parse_kwargs,
    scenario_agent,
    verifier_agent,
)
from .differ import Divergence, diff
from .sandbox import AppliedEdit, EditNotApplied, Sandbox
from .scenarios import Change, Edit, Scenario, ScenarioResult

Progress = Callable[[str, str], None]

# Errors that mean the scenario was never a valid observation, as opposed to
# the system genuinely behaving that way.
_RESOLUTION_ERRORS = (
    "ModuleNotFoundError",
    "ImportError",
    "AttributeError",
    "TypeError",
)


def _is_unresolvable(result: ScenarioResult) -> bool:
    return not result.ok and any(
        (result.error or "").startswith(e) for e in _RESOLUTION_ERRORS
    )


@dataclass
class RehearsalReport:
    request: str
    impact: ImpactAnalysis
    change: Change
    applied: list[AppliedEdit]
    scenarios: list[Scenario]
    discarded: list[tuple[Scenario, str]] = field(default_factory=list)
    before: dict[str, ScenarioResult] = field(default_factory=dict)
    after: dict[str, ScenarioResult] = field(default_factory=dict)
    divergences: list[Divergence] = field(default_factory=list)
    verification: VerificationReport | None = None

    @property
    def changed(self) -> list[Divergence]:
        return [d for d in self.divergences if d.diverged]

    @property
    def surprises(self) -> list[Divergence]:
        """Scenarios whose prediction was wrong. These are the findings."""
        return [d for d in self.divergences if d.outcome.surprising]

    @property
    def executions(self) -> int:
        return len(self.before) + len(self.after)


def _noop(stage: str, detail: str) -> None:
    return None


async def rehearse_change(
    repo: Path, request: str, progress: Progress = _noop
) -> RehearsalReport:
    """Run one full rehearsal of a proposed change."""
    repo = Path(repo).resolve()

    # 1. What does this change touch?
    #
    # Two phases, deliberately. Asking for structured output directly skips the
    # tool-use loop entirely and the model answers from imagination - it will
    # confidently invent module names. So the agent investigates first, with
    # tools, and only then serialises what it actually found.
    progress("impact", "reading the repository")
    agent = impact_agent(repo)
    await agent.invoke_async(
        f"The engineer has proposed this change:\n\n{request}\n\n"
        "Investigate the repository now, using your tools. List the files, read "
        "the ones that matter, search for every form in which the affected rule "
        "is encoded, and read the business rules.\n\n"
        "Do not answer from assumption. Every file path, module name and symbol "
        "you rely on must be one you have actually seen in a tool result."
    )
    impact: ImpactAnalysis = await agent.structured_output_async(
        ImpactAnalysis,
        "Now report what you found. Use only paths and symbols you saw in the "
        "repository. Each edit's `find` text must be copied verbatim from a file "
        "you read.",
    )
    progress(
        "impact",
        f"{len(impact.edits)} edit(s), {len(impact.affected_components)} component(s), "
        f"{len(impact.suspected_duplicates)} suspected duplicate(s)",
    )

    change = Change(
        description=request,
        edits=[Edit(path=e.path, find=e.find, replace=e.replace) for e in impact.edits],
    )

    # 2. What observations would expose a difference?
    progress("scenario", "designing observations")
    agent = scenario_agent(repo)
    await agent.invoke_async(
        f"Proposed change:\n{request}\n\n"
        f"Affected components:\n{chr(10).join(impact.affected_components) or '(none reported)'}\n\n"
        f"Suspected duplicate implementations:\n"
        f"{chr(10).join(impact.suspected_duplicates) or '(none reported)'}\n\n"
        "Before designing anything, read the repository with your tools. For "
        "every function you intend to call, open the file and confirm the module "
        "path, the function name and its parameter names. A scenario naming a "
        "module that does not exist is worse than no scenario at all.\n\n"
        "Read the documentation before predicting. For each suspected duplicate "
        "above, find the rule that governs it and decide whether that rule is "
        "supposed to follow the change. If it is, predict 'changed' even if you "
        "can see the edit will not reach it - that gap is exactly what this "
        "rehearsal is meant to expose. Predict 'unchanged' only where a separate "
        "named rule holds it fixed, and quote that rule."
    )
    plan: ScenarioPlan = await agent.structured_output_async(
        ScenarioPlan,
        "Now report the scenarios, using only modules and functions whose "
        "definitions you have actually read. Module paths are relative to the "
        "repository root, e.g. 'services.payment_service'.",
    )

    scenarios = [
        Scenario(
            id=s.id,
            name=s.name,
            module=s.module,
            function=s.function,
            kwargs=parse_kwargs(s.kwargs_json),
            expected_verdict=s.expected_verdict,
            because=s.because,
        )
        for s in plan.scenarios
    ]
    progress("scenario", f"{len(scenarios)} scenario(s) proposed")

    # 3. Observe the current system. A scenario that cannot even resolve is
    #    discarded loudly rather than reported as behaviour.
    progress("before", f"executing {len(scenarios)} scenario(s) against current code")
    with Sandbox(repo, "before") as box:
        before_all = box.run_all(scenarios)

    valid = [s for s in scenarios if not _is_unresolvable(before_all[s.id])]
    discarded = [
        (s, before_all[s.id].error or "unresolvable")
        for s in scenarios
        if _is_unresolvable(before_all[s.id])
    ]
    if discarded:
        progress("before", f"discarded {len(discarded)} unresolvable scenario(s)")
    before = {s.id: before_all[s.id] for s in valid}

    # 4. Apply the change and observe again.
    progress("after", "applying the change in an isolated sandbox")
    with Sandbox(repo, "after") as box:
        try:
            applied = box.apply(change)
        except EditNotApplied as exc:
            progress("after", f"change could not be applied: {exc}")
            raise
        progress("after", f"executing {len(valid)} scenario(s) against proposed code")
        after = box.run_all(valid)

    # 5. Compare.
    divergences = diff(valid, before, after)
    changed = [d for d in divergences if d.diverged]
    surprises = [d for d in divergences if d.outcome.surprising]
    progress("diff", f"{len(changed)} of {len(divergences)} scenario(s) changed behaviour")
    if surprises:
        progress(
            "diff",
            f"{len(surprises)} scenario(s) contradicted their prediction: "
            + ", ".join(f"{d.scenario.id} ({d.outcome.value})" for d in surprises),
        )

    report = RehearsalReport(
        request=request,
        impact=impact,
        change=change,
        applied=applied,
        scenarios=valid,
        discarded=discarded,
        before=before,
        after=after,
        divergences=divergences,
    )

    # 6. Challenge the result.
    progress("verify", "reading the code and rules to challenge the result")
    agent = verifier_agent(repo)
    await agent.invoke_async(_verification_brief(report))
    progress("verify", "writing up the findings with evidence")
    report.verification = await agent.structured_output_async(
        VerificationReport,
        "Now report your findings. Every claim needs evidence you actually "
        "read - a file:line reference or a business rule id.",
    )
    progress(
        "verify",
        f"risk={report.verification.overall_risk}, "
        f"{len(report.verification.challenges)} finding(s)",
    )
    return report


def _verification_brief(report: RehearsalReport) -> str:
    """The evidence pack handed to the verifier."""
    lines = [
        f"Proposed change: {report.request}",
        "",
        "IMPORTANT, about your tools. They read the repository as it is BEFORE the "
        "change. That is deliberate: your job is to explain why behaviour diverged, "
        "and the cause almost always lives in the original code. It also means you "
        "will see the old values still in place. Do NOT conclude from that that the "
        "edit failed to apply. The edits below were applied to an isolated copy, and "
        "the observed results underneath came from executing that modified copy.",
        "",
        "Edits actually applied:",
    ]
    lines += [f"  {e.path} ({e.occurrences} occurrence(s))" for e in report.applied]
    lines += [
        "",
        "Components the Impact Agent flagged as possibly holding a duplicate "
        "implementation of the same rule:",
    ]
    lines += [f"  {d}" for d in report.impact.suspected_duplicates] or ["  (none)"]
    if report.surprises:
        lines += [
            "",
            "SCENARIOS THAT CONTRADICTED THEIR OWN PREDICTION. Each of these was "
            "predicted in advance, with a stated reason, and the prediction was "
            "wrong. Start here:",
        ]
        for d in report.surprises:
            lines.append(
                f"  [{d.outcome.value}] {d.scenario.id}: {d.scenario.name}\n"
                f"              predicted {d.scenario.expected_verdict} "
                f"because: {d.scenario.because}\n"
                f"              observed  {d.before.observed}  ->  {d.after.observed}"
            )

    lines += ["", "All observed behaviour, before and after, from real executions:"]
    for d in report.divergences:
        lines.append(
            f"  [{d.verdict.value:>9}] {d.scenario.id}: {d.scenario.name}\n"
            f"              {d.before.observed}  ->  {d.after.observed}"
            f"   (predicted {d.scenario.expected_verdict or 'n/a'})\n"
            f"              (called {d.scenario.module}.{d.scenario.function})"
        )
    if report.discarded:
        lines += ["", "Scenarios discarded as unresolvable (not evidence of anything):"]
        lines += [f"  {s.id}: {why}" for s, why in report.discarded]

    lines += [
        "",
        "Now try to prove this wrong. Use the tools to read the code and the "
        "business rules. Pay particular attention to any scenario that did NOT "
        "change when the rule it implements should have moved.",
    ]
    return "\n".join(lines)


def rehearse_change_sync(
    repo: Path, request: str, progress: Progress = _noop
) -> RehearsalReport:
    """Blocking wrapper around :func:`rehearse_change`."""
    return asyncio.run(rehearse_change(repo, request, progress))
