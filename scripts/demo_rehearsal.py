"""Stage-one proof: the rehearsal actually runs.

No agents involved. The scenarios and the change are hand-written here so
that we can prove the sandbox genuinely executes the target system before
and after a change and reports real observed behaviour.

    python scripts/demo_rehearsal.py

From stage two, the Scenario Agent writes the scenarios and the change
parser writes the edits. Everything below this line stays the same.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay.differ import Verdict, diff  # noqa: E402
from replay.proof import CHANGE, REPO, SCENARIOS  # noqa: E402
from replay.sandbox import rehearse  # noqa: E402

# The scenarios and the change live in replay/proof.py, because the web page
# recomputes this same proof on request. One copy, so the two can never drift.

MARK = {
    Verdict.UNCHANGED: "  ",
    Verdict.CHANGED: "~ ",
    Verdict.BROKE: "! ",
    Verdict.FIXED: "+ ",
}


def main() -> int:
    print(f"\n  Proposed change: {CHANGE.description}")
    print(f"  Target repository: {REPO.name}")
    print(f"  Scenarios: {len(SCENARIOS)}\n")

    before, after, applied = rehearse(REPO, CHANGE, SCENARIOS)

    for edit in applied:
        print(f"  applied: {edit.path} ({edit.occurrences} occurrence(s))")

    divergences = diff(SCENARIOS, before, after)

    width = max(len(d.scenario.name) for d in divergences)
    print(f"\n  {'SCENARIO'.ljust(width)}   {'BEFORE':>12}   {'AFTER':>12}   VERDICT")
    print(f"  {'-' * width}   {'-' * 12}   {'-' * 12}   {'-' * 9}")
    for d in divergences:
        print(
            f"{MARK[d.verdict]}{d.scenario.name.ljust(width)}   "
            f"{d.before.observed:>12}   {d.after.observed:>12}   {d.verdict.value}"
        )

    changed = [d for d in divergences if d.diverged]
    unchanged = [d for d in divergences if not d.diverged]

    print(
        f"\n  {len(changed)} of {len(divergences)} scenarios changed behaviour; "
        f"{len(unchanged)} did not.\n"
    )

    total_ms = sum(r.duration_ms for r in list(before.values()) + list(after.values()))
    print(f"  {len(SCENARIOS) * 2} real executions in {total_ms} ms\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
