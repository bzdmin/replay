"""Run a full agent-driven rehearsal.

    python scripts/rehearse.py "Change the transaction fee from 2.5% to 2%"

Point it at your own code with --repo:

    python scripts/rehearse.py --repo path/to/your/project "Change the retry limit to 5"

Replay works where behaviour can be executed, intent is written down, and the
behaviour is reachable in a single call. Pricing, fees, billing and policy
logic fit well. Behaviour that needs setup first does not, yet.

Requires AWS credentials with Amazon Bedrock model access. See README.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay import models  # noqa: E402
from replay.differ import Verdict  # noqa: E402
from replay.pipeline import rehearse_change_sync  # noqa: E402

REPO = Path(__file__).resolve().parents[1] / "demo-repo" / "acmepay"

STAGE_LABEL = {
    "impact": "mapping impact",
    "scenario": "designing scenarios",
    "before": "running current behaviour",
    "after": "running proposed behaviour",
    "diff": "comparing",
    "verify": "challenging the result",
}

MARK = {
    Verdict.UNCHANGED: "  ",
    Verdict.CHANGED: "~ ",
    Verdict.BROKE: "! ",
    Verdict.FIXED: "+ ",
}

SEVERITY_ORDER = ["critical", "high", "medium", "low", "expected"]


def progress(stage: str, detail: str) -> None:
    print(f"  [{STAGE_LABEL.get(stage, stage):<26}] {detail}", flush=True)


def main(argv: list[str]) -> int:
    args = argv[1:]
    repo = REPO

    if "--repo" in args:
        i = args.index("--repo")
        try:
            repo = Path(args[i + 1]).expanduser().resolve()
        except IndexError:
            print("--repo needs a path")
            return 2
        del args[i : i + 2]
        if not repo.is_dir():
            print(f"not a directory: {repo}")
            return 2

    if not args:
        print(__doc__)
        return 2

    request = " ".join(args)
    print(f"\n  Proposed change: {request}")
    print(f"  Repository: {repo}")
    print(f"\n{models.describe()}\n")

    report = rehearse_change_sync(repo, request, progress)

    print("\n  BEHAVIOURAL DIFF\n")
    if report.divergences:
        width = min(58, max(len(d.scenario.name) for d in report.divergences))
        for d in report.divergences:
            flag = "!!" if d.outcome.surprising else "  "
            name = d.scenario.name[:width]
            print(
                f"{flag} {name.ljust(width)}  "
                f"{d.before.observed:>10} -> {d.after.observed:<10}  "
                f"predicted {(d.scenario.expected_verdict or 'n/a'):<9} "
                f"{d.outcome.value}"
            )

    if report.surprises:
        print("\n  PREDICTION FAILURES - these are the findings\n")
        for d in report.surprises:
            print(f"  {d.outcome.value.upper()}: {d.scenario.name}")
            print(
                f"      predicted {d.scenario.expected_verdict} because "
                f"{d.scenario.because}"
            )
            print(f"      observed  {d.before.observed} -> {d.after.observed}\n")

    for scenario, why in report.discarded:
        print(f"  (discarded) {scenario.id}: {why}")

    v = report.verification
    if v is not None:
        print(f"\n  VERIFIER - overall risk: {v.overall_risk.upper()}\n")
        print(f"  {v.summary}\n")
        ordered = sorted(
            v.challenges,
            key=lambda c: SEVERITY_ORDER.index(c.severity)
            if c.severity in SEVERITY_ORDER
            else 99,
        )
        for c in ordered:
            rule = f" [{c.rule_violated}]" if c.rule_violated else ""
            print(f"  {c.severity.upper()}{rule}: {c.claim}")
            for e in c.evidence:
                print(f"      evidence: {e}")
            print()

    print(f"  {report.executions} real executions across 2 sandboxes")
    print(f"  {report.usage.describe()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
