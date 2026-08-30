"""Replay on the web.

One page. A visitor sees a finished rehearsal immediately, and can run their
own change against the demo repository and watch the agents work.

The page is deliberately cheap to look at and deliberately expensive to use, so
the guards below matter: a live rehearsal costs real Bedrock spend, and the URL
is public.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .pipeline import rehearse_change
from .report import report_to_dict

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "demo-repo" / "acmepay"
PAGE = Path(__file__).parent / "page.html"
FLAGSHIP = ROOT / "data" / "flagship.json"

# spend guards
# A rehearsal is a handful of agent turns over a real repository. Cheap once,
# ruinous if a crawler finds the endpoint.
MAX_CONCURRENT = 1
PER_IP_COOLDOWN_S = 120
GLOBAL_HOURLY_LIMIT = 25
MAX_REQUEST_CHARS = 300

# The verifier reads code for minutes without emitting progress. With no bytes
# on the wire, hosting proxies reset the connection and the browser never sees
# the result. An SSE comment every few seconds keeps it open and is ignored by
# the EventSource client.
HEARTBEAT_S = 10

_running = asyncio.Semaphore(MAX_CONCURRENT)
_last_seen: dict[str, float] = {}
_recent: deque[float] = deque(maxlen=GLOBAL_HOURLY_LIMIT)

app = FastAPI(title="Replay", docs_url=None, redoc_url=None)


def _rate_limited(ip: str) -> str | None:
    """Return a human-readable refusal, or None if the request may proceed."""
    now = time.time()

    while _recent and now - _recent[0] > 3600:
        _recent.popleft()
    if len(_recent) >= GLOBAL_HOURLY_LIMIT:
        return (
            "Replay has hit its hourly limit for live rehearsals. The recorded "
            "run below is a real rehearsal and shows exactly what a live one does."
        )

    last = _last_seen.get(ip)
    if last is not None and now - last < PER_IP_COOLDOWN_S:
        wait = int(PER_IP_COOLDOWN_S - (now - last))
        return f"One rehearsal at a time, please. Try again in {wait}s."

    return None


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


@app.get("/api/flagship")
async def flagship() -> JSONResponse:
    """The recorded rehearsal shown on first paint."""
    if not FLAGSHIP.exists():
        return JSONResponse({"error": "no recorded run available"}, status_code=404)
    return JSONResponse(json.loads(FLAGSHIP.read_text(encoding="utf-8")))


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/rehearse")
async def rehearse(request: Request, change: str = "") -> StreamingResponse:
    """Run a live rehearsal, streaming progress as server-sent events."""
    change = (change or "").strip()[:MAX_REQUEST_CHARS]
    ip = (request.client.host if request.client else "unknown") or "unknown"

    async def stream():
        if not change:
            yield _sse("error", {"message": "Describe a change first."})
            return

        refusal = _rate_limited(ip)
        if refusal:
            yield _sse("error", {"message": refusal})
            return

        if _running.locked():
            yield _sse(
                "error",
                {"message": "A rehearsal is already running. Give it a moment."},
            )
            return

        _last_seen[ip] = time.time()
        _recent.append(time.time())

        queue: asyncio.Queue = asyncio.Queue()

        def progress(stage: str, detail: str) -> None:
            queue.put_nowait(("progress", {"stage": stage, "detail": detail}))

        async def run() -> None:
            try:
                report = await rehearse_change(REPO, change, progress)
                await queue.put(("report", report_to_dict(report)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the browser
                await queue.put(
                    ("error", {"message": f"{type(exc).__name__}: {exc}"})
                )
            finally:
                await queue.put(("done", {}))

        async with _running:
            task = asyncio.create_task(run())
            try:
                while True:
                    try:
                        event, payload = await asyncio.wait_for(
                            queue.get(), timeout=HEARTBEAT_S
                        )
                    except asyncio.TimeoutError:
                        # Nothing to report yet. Keep the connection alive.
                        yield ": keepalive\n\n"
                        if await request.is_disconnected():
                            task.cancel()
                            break
                        continue

                    if event == "done":
                        break
                    yield _sse(event, payload)
                    if await request.is_disconnected():
                        task.cancel()
                        break
            finally:
                if not task.done():
                    task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
