"""Owned backend process for scripts/start_system.ps1 and scripts/stop_system.ps1.

Serves backend.main:app with uvicorn and watches a stop-request file in the control directory.
When the file appears, uvicorn performs its normal graceful exit, so the backend lifespan runs:
active missions are stopped and recorded with reason "backend shutdown", pending tick data is
persisted, WebSocket connections are closed and database connections are released.

Windows has no portable way to deliver Ctrl+C to another console process, which is why a
file under runs/system (git-ignored, local only) is used as the shutdown signal.
"""

import asyncio
import io
import json
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from orchestration.manifest import ROOT

CONTROL_DIR = ROOT / "runs" / "system"
STOP_FILE = "backend.stop"
STATE_FILE = "backend.state.json"
POLL_SECONDS = 0.5
LOG_MAX_BYTES = 10 * 2**20


async def watch_stop(server: object, stop_file: Path) -> None:
    """Set uvicorn's should_exit when the stop file appears."""
    while not getattr(server, "should_exit", False):
        if stop_file.exists():
            stop_file.unlink(missing_ok=True)
            server.should_exit = True  # type: ignore[attr-defined]
            return
        await asyncio.sleep(POLL_SECONDS)


class RotatingStream(io.TextIOBase):
    """Text stream that rotates its file at a size limit, keeping one previous copy, so a
    long-running server cannot grow its log without bound (access logs are written per
    request)."""

    def __init__(self, path: Path, max_bytes: int = LOG_MAX_BYTES) -> None:
        self.path, self.max_bytes = path, max_bytes
        self.lock = threading.Lock()
        self.stream = path.open("a", encoding="utf-8")
        self.size = path.stat().st_size

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        with self.lock:
            written = self.stream.write(text)
            self.stream.flush()
            self.size += len(text.encode("utf-8", errors="replace"))
            if self.size >= self.max_bytes:
                self.stream.close()
                self.path.replace(self.path.with_name(self.path.name + ".1"))
                self.stream = self.path.open("a", encoding="utf-8")
                self.size = 0
            return written

    def flush(self) -> None:
        with self.lock:
            self.stream.flush()


def redirect_output(log: Path, max_bytes: int = LOG_MAX_BYTES) -> RotatingStream:
    """Send this process's output to a size-rotated log file (current + one previous copy).
    The start script launches the server without inheritable console handles, so it cannot
    redirect them itself."""
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists():
        log.replace(log.with_name(log.name + ".1"))
    stream = RotatingStream(log, max_bytes)
    sys.stdout = sys.stderr = stream
    return stream


def serve(control_dir: Path = CONTROL_DIR, log: Path | None = None) -> int:
    import uvicorn

    if log is not None:
        redirect_output(log)

    from backend.core.config import ConfigurationError, load_settings

    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", flush=True)
        return 2
    control_dir.mkdir(parents=True, exist_ok=True)
    stop_file = control_dir / STOP_FILE
    state_file = control_dir / STATE_FILE
    stop_file.unlink(missing_ok=True)
    server = uvicorn.Server(
        uvicorn.Config(
            "backend.main:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            lifespan="on",
            timeout_graceful_shutdown=30,
        )
    )

    async def main() -> None:
        state_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "host": settings.host,
                    "port": settings.port,
                    "started_at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        watcher = asyncio.create_task(watch_stop(server, stop_file))
        try:
            await server.serve()
        finally:
            watcher.cancel()
            state_file.unlink(missing_ok=True)

    asyncio.run(main())
    print("backend stopped", flush=True)
    return 0
