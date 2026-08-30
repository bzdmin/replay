"""Scenario driver.

Copied into every sandbox and executed as a subprocess with the sandbox
root as the working directory. It imports the target module, calls one
function, and prints a single JSON line to stdout.

This file is deliberately dependency-free: it runs inside the target
repository's environment, not Replay's.
"""

import importlib
import json
import os
import sys
import traceback


def main() -> int:
    sys.path.insert(0, os.getcwd())
    spec = json.loads(sys.argv[1])

    try:
        module = importlib.import_module(spec["module"])
        func = getattr(module, spec["function"])
        value = func(**spec.get("kwargs", {}))
        payload = {"ok": True, "value": str(value), "type": type(value).__name__}
    except Exception as exc:  # noqa: BLE001 - the failure itself is the observation
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=3),
        }

    sys.stdout.write(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
