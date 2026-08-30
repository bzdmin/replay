"""Strands tools for investigating a target repository.

These are the agents' hands. Every one of them reads real files from the
target repository — none of them ask a model what a file probably contains.

They are built by a factory bound to a repository root so the same tool set
can be pointed at any checkout, and so each function stays directly callable
in tests without a model in the loop.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from strands import tool

MAX_MATCHES = 60
MAX_FILE_BYTES = 40_000
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml"}


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def build_repo_tools(repo: Path) -> list[Any]:
    """Build the repository tool set bound to `repo`."""
    repo = Path(repo).resolve()

    def _rel(path: Path) -> str:
        return path.relative_to(repo).as_posix()

    def _resolve(path: str) -> Path:
        target = (repo / path).resolve()
        if not target.is_relative_to(repo):
            raise ValueError(f"path escapes the repository: {path}")
        return target

    @tool
    def search_repository(pattern: str) -> str:
        """Search the repository for a regular expression.

        Use this to find where a value, constant, or symbol is used. Remember
        that the same rule can be encoded in more than one form -- a rate may
        appear as a decimal in one file and as basis points in another, so
        search for the concept, not only the literal you were given.

        Args:
            pattern: A Python regular expression, case-insensitive.

        Returns:
            Matching lines as "path:line: text", or a note that nothing matched.
        """
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"invalid regular expression: {exc}"

        hits: list[str] = []
        for path in _iter_files(repo):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{_rel(path)}:{lineno}: {line.strip()}")
                    if len(hits) >= MAX_MATCHES:
                        hits.append(f"... truncated at {MAX_MATCHES} matches")
                        return "\n".join(hits)

        return "\n".join(hits) if hits else f"no matches for {pattern!r}"

    @tool
    def read_file(path: str) -> str:
        """Read one file from the repository, with line numbers.

        Args:
            path: Repository-relative path, e.g. "services/payment_service.py".
        """
        try:
            target = _resolve(path)
        except ValueError as exc:
            return str(exc)
        if not target.is_file():
            return f"{path} does not exist"

        text = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(text.encode("utf-8")) > MAX_FILE_BYTES
        if truncated:
            text = text[:MAX_FILE_BYTES]

        numbered = "\n".join(
            f"{i:>4} | {line}" for i, line in enumerate(text.splitlines(), start=1)
        )
        if truncated:
            numbered += "\n     | ... file truncated"
        return numbered

    @tool
    def list_repository(subdirectory: str = "") -> str:
        """List source and documentation files in the repository.

        Args:
            subdirectory: Optional path to list, e.g. "services". Omit for all.
        """
        prefix = subdirectory.strip("/")
        paths = [
            _rel(p) for p in _iter_files(repo) if not prefix or _rel(p).startswith(prefix)
        ]
        if not paths:
            return f"nothing under {subdirectory!r}" if prefix else "repository is empty"
        return "\n".join(paths)

    @tool
    def search_tests(symbol: str) -> str:
        """Find tests that exercise a symbol.

        Args:
            symbol: A function, constant, or module name.
        """
        regex = re.compile(re.escape(symbol), re.IGNORECASE)
        hits: list[str] = []
        for path in _iter_files(repo):
            if "test" not in _rel(path).lower():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{_rel(path)}:{lineno}: {line.strip()}")

        return "\n".join(hits[:MAX_MATCHES]) if hits else f"no tests mention {symbol!r}"

    @tool
    def read_documentation(query: str) -> str:
        """Search documentation and business rules for a term.

        Business rules are the difference between a change that is merely
        different and a change that is wrong. Always check them before
        concluding that a behavioural difference is acceptable.

        Args:
            query: A term, rule id, or concept, e.g. "refund" or "BR-207".
        """
        regex = re.compile(re.escape(query), re.IGNORECASE)
        sections: list[str] = []
        for path in _iter_files(repo):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not regex.search(text):
                continue

            lines = text.splitlines()
            for lineno, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, lineno - 4)
                    end = min(len(lines), lineno + 8)
                    body = "\n".join(lines[start:end])
                    sections.append(f"--- {_rel(path)}:{start + 1} ---\n{body}")
                    break

        return "\n\n".join(sections[:6]) if sections else f"no documentation mentions {query!r}"

    return [search_repository, read_file, list_repository, search_tests, read_documentation]
