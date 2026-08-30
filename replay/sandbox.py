"""The Replay sandbox.

Materialises an isolated copy of the target repository, optionally applies
a proposed change to it, and executes scenarios inside it as real
subprocesses.

Nothing here asks a model what would happen. The sandbox runs the code and
reports what did happen.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .scenarios import Change, Scenario, ScenarioResult

DRIVER = Path(__file__).parent / "_driver.py"
DEFAULT_TIMEOUT_S = 30

# Directories that must never be copied into a sandbox.
_IGNORED = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".git", ".venv", "node_modules", ".pytest_cache"
)


class EditNotApplied(RuntimeError):
    """Raised when a proposed edit does not match the file it targets."""


class AmbiguousEdit(EditNotApplied):
    """Raised when an edit's `find` text matches more than once.

    Applying it would rewrite every occurrence, which is almost never what was
    meant. In a file where the same literal encodes two different rules, the
    quiet version of this is a corrupted rule and a green report.
    """


@dataclass
class AppliedEdit:
    path: str
    occurrences: int


class Sandbox:
    """An isolated, disposable copy of the target repository."""

    def __init__(self, source: Path, label: str) -> None:
        self.source = Path(source).resolve()
        self.label = label
        self._tmp: tempfile.TemporaryDirectory | None = None
        self.root: Path | None = None

    def __enter__(self) -> "Sandbox":
        self._tmp = tempfile.TemporaryDirectory(prefix=f"replay-{self.label}-")
        self.root = Path(self._tmp.name) / self.source.name
        shutil.copytree(self.source, self.root, ignore=_IGNORED)
        shutil.copy2(DRIVER, self.root / "_replay_driver.py")
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()

    def apply(self, change: Change) -> list[AppliedEdit]:
        """Apply a proposed change. A non-matching edit is an error, not a warning."""
        if self.root is None:
            raise RuntimeError("sandbox is not open")

        applied: list[AppliedEdit] = []
        for edit in change.edits:
            target = self.root / edit.path
            if not target.exists():
                raise EditNotApplied(f"{edit.path} does not exist in the repository")

            original = target.read_text(encoding="utf-8")
            count = original.count(edit.find)
            if count == 0:
                raise EditNotApplied(
                    f"{edit.path}: no occurrence of {edit.find!r} to replace"
                )
            if count > 1 and not edit.allow_multiple:
                lines = [
                    i
                    for i, line in enumerate(original.splitlines(), start=1)
                    if edit.find in line
                ]
                raise AmbiguousEdit(
                    f"{edit.path}: {edit.find!r} appears {count} times "
                    f"(lines {lines}). Widen the find text so it matches exactly "
                    f"one location, or set allow_multiple if every occurrence "
                    f"really should change."
                )

            target.write_text(original.replace(edit.find, edit.replace), encoding="utf-8")
            applied.append(AppliedEdit(path=edit.path, occurrences=count))
        return applied

    def run(self, scenario: Scenario, timeout: int = DEFAULT_TIMEOUT_S) -> ScenarioResult:
        """Execute one scenario inside this sandbox and capture what happened."""
        if self.root is None:
            raise RuntimeError("sandbox is not open")

        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "_replay_driver.py", json.dumps(scenario.to_spec())],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ScenarioResult(
                scenario_id=scenario.id,
                ok=False,
                value=None,
                error=f"timed out after {timeout}s",
                exit_code=-1,
                duration_ms=elapsed,
            )

        elapsed = int((time.perf_counter() - started) * 1000)

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return ScenarioResult(
                scenario_id=scenario.id,
                ok=False,
                value=None,
                error=(proc.stderr or proc.stdout or "no output").strip()[:400],
                exit_code=proc.returncode,
                duration_ms=elapsed,
            )

        return ScenarioResult(
            scenario_id=scenario.id,
            ok=bool(payload.get("ok")),
            value=payload.get("value"),
            error=payload.get("error"),
            exit_code=proc.returncode,
            duration_ms=elapsed,
        )

    def run_all(self, scenarios: list[Scenario]) -> dict[str, ScenarioResult]:
        return {s.id: self.run(s) for s in scenarios}


def rehearse(
    repo: Path, change: Change, scenarios: list[Scenario]
) -> tuple[dict[str, ScenarioResult], dict[str, ScenarioResult], list[AppliedEdit]]:
    """Run every scenario before and after the change. This is the whole point.

    Returns (before, after, applied_edits).
    """
    with Sandbox(repo, "before") as before_box:
        before = before_box.run_all(scenarios)

    with Sandbox(repo, "after") as after_box:
        applied = after_box.apply(change)
        after = after_box.run_all(scenarios)

    return before, after, applied
