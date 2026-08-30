"""Record a rehearsal to disk so the web page can show a result instantly.

    python scripts/record_run.py

The web page loads this cached run on first paint, so a visitor sees a real
finished rehearsal immediately instead of an empty form -- and so the flagship
demo never depends on a live model call succeeding while someone is watching.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay.pipeline import rehearse_change_sync  # noqa: E402
from replay.report import report_to_dict  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "demo-repo" / "acmepay"
OUT = ROOT / "data" / "flagship.json"

REQUEST = "Change the standard transaction fee from 2.5% to 2%"


def main() -> int:
    request = " ".join(sys.argv[1:]) or REQUEST
    print(f"  recording: {request}\n")

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
