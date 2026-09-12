"""The deterministic proof, computed on request.

No agents, no model calls, no spend. Six hand written scenarios and one hand
written change, executed against two isolated copies of the demo repository,
before and after. This is the same sandbox and the same differ a full rehearsal
uses, with the agents removed.

That is what makes it cheap enough to recompute while someone is reading the
page, which is the point: the numbers on screen are not a screenshot of a run
that happened once, they are the result of executions that just happened.
"""

from __future__ import annotations

import time
from pathlib import Path

from .differ import diff
from .sandbox import rehearse
from .scenarios import Change, Edit, Scenario

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "demo-repo" / "acmepay"

AMOUNT = 100_000

SCENARIOS = [
    Scenario(
        id="standard_payment_fee",
        name="Fee on a standard card payment",
        module="services.payment_service",
        function="calculate_fee",
        kwargs={"amount": AMOUNT},
    ),
    Scenario(
        id="net_settlement",
        name="Net amount settled to the merchant",
        module="services.payment_service",
        function="net_settlement",
        kwargs={"amount": AMOUNT},
    ),
    Scenario(
        id="refund_fee",
        name="Fee retained when a payment is refunded",
        module="services.refund_service",
        function="calculate_refund_fee",
        kwargs={"amount": AMOUNT},
    ),
    Scenario(
        id="standard_merchant_billing",
        name="Transaction billed to a standard-plan merchant",
        module="services.billing_service",
        function="bill_transaction",
        kwargs={"amount": AMOUNT, "merchant_plan": "standard"},
    ),
    Scenario(
        id="legacy_merchant_billing",
        name="Transaction billed to a legacy-plan merchant",
        module="services.billing_service",
        function="bill_transaction",
        kwargs={"amount": AMOUNT, "merchant_plan": "legacy-2019"},
    ),
    Scenario(
        id="legacy_statement_rate",
        name="Rate printed on a legacy merchant statement",
        module="services.billing_service",
        function="statement_rate",
        kwargs={"merchant_plan": "legacy-2019"},
    ),
]

CHANGE = Change(
    description="Change the standard transaction fee from 2.5% to 2%",
    edits=[
        Edit(
            path="core/config.py",
            find='STANDARD_FEE_RATE = Decimal("0.025")',
            replace='STANDARD_FEE_RATE = Decimal("0.02")',
        )
    ],
)


def run() -> dict:
    """Execute every scenario twice, right now, and report what happened."""
    started = time.monotonic()
    before, after, applied = rehearse(REPO, CHANGE, SCENARIOS)
    divergences = diff(SCENARIOS, before, after)

    rows = [
        {
            "id": d.scenario.id,
            "name": d.scenario.name,
            "call": f"{d.scenario.module}.{d.scenario.function}",
            "before": d.before.observed,
            "after": d.after.observed,
            "verdict": d.verdict.value,
            "changed": d.diverged,
            "ms": d.before.duration_ms + d.after.duration_ms,
        }
        for d in divergences
    ]

    execution_ms = sum(
        r.duration_ms for r in list(before.values()) + list(after.values())
    )

    return {
        "change": CHANGE.description,
        "repo": REPO.name,
        "applied": [{"path": e.path, "occurrences": e.occurrences} for e in applied],
        "rows": rows,
        "scenarios": len(SCENARIOS),
        "executions": len(SCENARIOS) * 2,
        "changed": sum(1 for r in rows if r["changed"]),
        "execution_ms": execution_ms,
        "wall_ms": int((time.monotonic() - started) * 1000),
        "computed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }
