from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

from config import get_settings
from mt5_client import MT5Client

logger = logging.getLogger(__name__)
STATUS_PATH = Path(__file__).resolve().parent / "runtime_status.json"


class LocalWindowsRuntime:
    def __init__(self, status_path: str | Path = STATUS_PATH, poll_interval_seconds: int = 300) -> None:
        self.status_path = Path(status_path)
        self.poll_interval_seconds = poll_interval_seconds
        self._stop = Event()
        self._last_status = {
            "status": "starting",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "local_windows_desktop",
            "mt5_connected": False,
            "reason": "initializing",
        }

    def write_status(self, status: str, *, reason: str = "", mt5_connected: bool = False, details: dict[str, object] | None = None) -> dict[str, object]:
        payload = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "local_windows_desktop",
            "mt5_connected": mt5_connected,
            "reason": reason,
            "details": details or {},
        }
        self._last_status = payload
        self.status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def check_mt5_health(self) -> dict[str, object]:
        try:
            settings = get_settings()
            mt5_client = MT5Client(settings=settings)
            connected = mt5_client.is_connected()
            if connected:
                return self.write_status("ready", reason="MT5 terminal connected", mt5_connected=True, details={"mt5_path": os.getenv("MT5_PATH", "")})
            return self.write_status(
                "blocked",
                reason="MT5 terminal is available but not connected or not initialized.",
                mt5_connected=False,
                details={"mt5_path": os.getenv("MT5_PATH", "")},
            )
        except Exception as exc:  # pragma: no cover - runtime environment guard
            logger.warning("Local runtime health check failed: %s", exc)
            return self.write_status("blocked", reason=str(exc), mt5_connected=False, details={"mt5_path": os.getenv("MT5_PATH", "")})

    def run_loop(self) -> None:
        self.write_status("starting", reason="Waiting for MT5 initialization")
        while not self._stop.is_set():
            self.check_mt5_health()
            logger.info("Local Windows runtime heartbeat: %s", self._last_status)
            time.sleep(self.poll_interval_seconds)

    def stop(self) -> None:
        self._stop.set()


def _status_handler_factory(state: LocalWindowsRuntime):
    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in {"/", "/status", "/status.json"}:
                body = json.dumps(state._last_status).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    return StatusHandler


def run_local_windows_runtime(*, poll_interval_seconds: int = 300, status_port: int = 8765) -> None:
    runtime = LocalWindowsRuntime(poll_interval_seconds=poll_interval_seconds)
    runtime.write_status("starting", reason="Local Windows runtime starting")

    def serve_status() -> None:
        handler = _status_handler_factory(runtime)
        server = ThreadingHTTPServer(("0.0.0.0", status_port), handler)
        logger.info("Status server listening on http://0.0.0.0:%s/status", status_port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Status server interrupted.")
        finally:
            server.server_close()

    status_thread = Thread(target=serve_status, daemon=True)
    status_thread.start()

    try:
        runtime.run_loop()
    except KeyboardInterrupt:
        logger.info("Runtime stopped by user interrupt.")
    finally:
        runtime.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_local_windows_runtime()
