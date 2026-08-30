"""The Replay agents.

Three agents that genuinely need a model, and nothing that pretends to.

  Impact Agent    - reads the repository and works out what the change touches
  Scenario Agent  - designs the observations that would expose a difference
  Verifier Agent  - tries to prove the rehearsal's conclusion wrong

The Replay Runner is deliberately *not* an agent. Executing a scenario and
comparing two outputs is deterministic work; wrapping it in a model would add
cost, latency and a failure mode while removing the guarantee that makes the
whole product credible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent

from .models import model_for
from .tools import build_repo_tools

# Structured outputs


class ProposedEdit(BaseModel):
    """One literal substitution implementing the requested change."""

    path: str = Field(description="Repository-relative path to edit")
    find: str = Field(description="Exact text to replace; must appear verbatim")
    replace: str = Field(description="Replacement text")
    rationale: str = Field(description="Why this edit implements the request")


class ImpactAnalysis(BaseModel):
    edits: list[ProposedEdit] = Field(
        description="The minimal edits that implement exactly what was asked"
    )
    affected_components: list[str] = Field(
        description="Files or modules whose behaviour may change"
    )
    suspected_duplicates: list[str] = Field(
        description=(
            "Places that appear to encode the same rule in a different form and "
            "would NOT be updated by these edits"
        )
    )
    notes: str


class ProposedScenario(BaseModel):
    id: str = Field(description="Short snake_case identifier")
    name: str = Field(description="Human-readable description of what is observed")
    module: str = Field(description="Importable module path, e.g. services.payment_service")
    function: str = Field(description="Function to call in that module")
    kwargs_json: str = Field(
        default="{}", description="JSON object of keyword arguments, e.g. {\"amount\": 100000}"
    )
    expected_verdict: Literal["changed", "unchanged"] = Field(
        description=(
            "Your prediction: should this observation move under the proposed "
            "change, or must it stay exactly the same? Predict what SHOULD "
            "happen per the rules, not what you think the code will do."
        )
    )
    because: str = Field(
        description="The rule or reason behind that prediction, e.g. 'BR-207 fixes this rate'"
    )
    rationale: str = Field(description="What difference this scenario would expose")


class ScenarioPlan(BaseModel):
    scenarios: list[ProposedScenario]


class Challenge(BaseModel):
    scenario_id: str | None = Field(
        default=None, description="Scenario this concerns, if any"
    )
    severity: Literal["critical", "high", "medium", "low", "expected"]
    claim: str = Field(description="What is wrong, or why this difference is acceptable")
    rule_violated: str | None = Field(
        default=None, description="Business rule id if one is contradicted, e.g. BR-207"
    )
    evidence: list[str] = Field(
        description="Concrete file:line references or rule ids supporting the claim"
    )


class VerificationReport(BaseModel):
    overall_risk: Literal["high", "medium", "low"]
    summary: str = Field(description="Two or three sentences an engineer can act on")
    challenges: list[Challenge]


# Agents

_IMPACT_PROMPT = """\
You are the Impact Agent in a change-rehearsal system.

Understand this first, because it inverts the instinct you would normally have:
you are not here to make a good change. You are here to reproduce *the change
the engineer actually described*, faithfully, including its shortcomings.

The whole product exists to show an engineer the consequences of the edit they
were about to make. If you quietly repair those consequences while writing the
edits, the rehearsal has nothing left to reveal and the engineer learns nothing.

So your job has two strictly separated halves.

**The edits.** The smallest set of literal substitutions that a competent
engineer would make if they took the request at face value and stopped there.
Usually this is one edit to one canonical definition. Do not update a second
copy of the value. Do not update documentation. Do not decouple a shared
constant. Do not fix anything, even when you can see it is broken - especially
then. Each `find` string must be copied verbatim from a file you have read, and
must be long enough to match exactly one place in that file; a `find` that
matches two lines will be rejected.

**The findings.** Everything you would have wanted to fix goes here instead, as
suspected_duplicates. A value can be duplicated in another unit (a percentage in
one file, basis points in another), hidden behind a different name, or sitting
inside a legacy component that was ported rather than refactored. It can also be
shared by a rule that is contractually required *not* to move with it. A plain
search for the literal you were given will miss all of these. Search for the
concept. Read the documentation. Follow the call paths.

Missing one of those is the failure this entire system exists to prevent. Fixing
one of them yourself is the second failure, and it is quieter.
"""

_SCENARIO_PROMPT = """\
You are the Scenario Agent in a change-rehearsal system.

You are not writing tests. You are stating falsifiable predictions.

Each scenario is one function call, executed for real twice - once against the
current code, once against the proposed code - and the two return values
compared. You never say what the value should BE. You only predict whether it
should MOVE. That distinction is what makes this system trustworthy: the
current code is the oracle, so you are never asked to invent an expected value,
and you must never try to.

For every scenario, commit to `expected_verdict`:

  "changed"    this observation SHOULD move, because the rule being changed
               genuinely governs it
  "unchanged"  this observation MUST stay identical, because no rule the
               engineer is changing governs it - or because a separate rule
               explicitly fixes it

Predict from the RULES, never from the CODE. This is the single hardest thing
about your job and the place you are most likely to fail.

Ask yourself: "if this rule changes, is this behaviour supposed to follow?"

Do NOT ask: "will the engineer's edit actually reach this code?" That second
question is what the rehearsal is for. If you answer it in your prediction, you
have predicted the bug instead of the requirement, and when reality agrees with
you nothing has been learned.

The trap, concretely. You will be handed a list of suspected duplicates -
places that implement the same rule in another form, often holding their own
private copy of the value. It is tempting to reason: "this component has its
own separate constant, so the edit won't touch it, so I predict unchanged."
That reasoning is wrong. It describes the mechanism, not the requirement.

If the rule governs that component, then when the rule changes that component's
behaviour is *supposed* to change, and you must predict "changed" - even
though, and precisely because, you suspect it will not. When it then fails to
move, you have caught a component the change never reached. That is the finding.

Predict "unchanged" for a duplicate only when a *separate, named rule* fixes it
in place. Read the documentation and quote the rule in `because`. "It has its
own constant" is not a rule. "BR-207 fixes this rate by contract" is a rule.

The four possible results, and what each means:

  predicted changed,   observed changed     the change works as intended
  predicted unchanged, observed unchanged   the blast radius really is bounded
  predicted changed,   observed unchanged   the change failed to reach a place
                                            that implements the same rule
  predicted unchanged, observed changed     the change leaked somewhere it was
                                            contractually forbidden to go

The last two are the entire reason this product exists. Design deliberately to
provoke them.

Coverage is the wrong objective. Do not try to exercise every line, or every
component. Instead: for each distinct place the affected rule is encoded -
the canonical definition AND every suspected duplicate you were handed -
write the narrowest call that isolates that one encoding. A call that fans out
through several components cannot tell you which one diverged.

Then add the scenarios that pin the boundary: things governed by a *neighbouring*
rule that must NOT move. Those are where leaks are caught.

Every module and function must genuinely exist. Read the file and confirm the
name and parameters before proposing a call. A scenario that raises ImportError
tells the engineer nothing.

Prefer 6-12 sharp scenarios over twenty vague ones.
"""

_VERIFIER_PROMPT = """\
You are the Verifier Agent in a change-rehearsal system.

Everything before you has already run. You are being handed real observed
behaviour from real executions, before and after a proposed change. Your job is
not to summarise it. Your job is to try to prove it wrong.

Work against the conclusion, not toward it:

  - A scenario that changed may be a contract violation, not an intended
    update. Check the business rules before you accept any difference.
  - A scenario that did NOT change may be the most serious finding in the set.
    It can mean the change failed to reach a code path that also implements
    the rule, which leaves the system internally inconsistent.
  - A scenario nobody wrote is not evidence of safety.

Cite evidence for every claim: a file:line reference, or a business rule id you
actually read. A claim without evidence is worse than no claim, because it
looks like a finding.

Mark a difference `expected` only when you have checked the rules and found
nothing that forbids it.
"""


def impact_agent(repo: Path) -> Agent:
    return Agent(
        name="impact",
        description="Traces what a proposed change can reach",
        model=model_for("impact"),
        system_prompt=_IMPACT_PROMPT,
        tools=build_repo_tools(repo),
        # Suppress Strands' default stdout handler; the pipeline reports
        # progress through its own callback instead.
        callback_handler=None,
    )


def scenario_agent(repo: Path) -> Agent:
    return Agent(
        name="scenario",
        description="Designs executable behavioural observations",
        model=model_for("scenario"),
        system_prompt=_SCENARIO_PROMPT,
        tools=build_repo_tools(repo),
        # Suppress Strands' default stdout handler; the pipeline reports
        # progress through its own callback instead.
        callback_handler=None,
    )


def verifier_agent(repo: Path) -> Agent:
    return Agent(
        name="verifier",
        description="Adversarial reviewer of a completed rehearsal",
        model=model_for("verifier", max_tokens=12000),
        system_prompt=_VERIFIER_PROMPT,
        tools=build_repo_tools(repo),
        # Suppress Strands' default stdout handler; the pipeline reports
        # progress through its own callback instead.
        callback_handler=None,
    )


def parse_kwargs(raw: str) -> dict:
    """Parse a scenario's kwargs_json, tolerating an empty or malformed value."""
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
