"""Record a rehearsal to disk so the web page can show a result instantly.

    python scripts/record_run.py
    python scripts/record_run.py --out rounding "Change money rounding ..."

The web page loads these cached runs, so a visitor sees a real finished
rehearsal immediately instead of an empty form, and so the demo never depends
on a live model call succeeding while someone is watching.

Without --out the run is written to data/flagship.json, the one shown on first
paint. With --out NAME it is written to data/NAME.json instead, which is how
the other presets get their recorded results without overwriting the flagship.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay.pipeline import rehearse_change_sync  # noqa: E402
from replay.report import report_to_dict  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "demo-repo" / "acmepay"
DATA = ROOT / "data"

REQUEST = "Change the standard transaction fee from 2.5% to 2%"


def main() -> int:
    args = sys.argv[1:]
    name = "flagship"
    if args[:1] == ["--out"]:
        if len(args) < 2 or not re.fullmatch(r"[a-z0-9-]+", args[1]):
            print("  --out needs a name made of lowercase letters, digits and hyphens")
            return 2
        name, args = args[1], args[2:]
    OUT = DATA / f"{name}.json"

    request = " ".join(args) or REQUEST
    print(f"  recording: {request}\n  into:      {OUT.relative_to(ROOT)}\n")

    def progress(stage: str, detail: str) -> None:
        print(f"  [{stage:<9}] {detail}", flush=True)

    report = rehearse_change_sync(REPO, request, progress)
    payload = report_to_dict(report)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    print(
        f"  {payload['stats']['scenarios']} scenarios, "
        f"{payload['stats']['executions']} executions, "
        f"{payload['stats']['surprises']} prediction failure(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
