from __future__ import annotations

import argparse
import logging
import sys

from local_runtime import run_local_windows_runtime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Windows MT5 runtime with a lightweight status endpoint.")
    parser.add_argument("--poll-seconds", type=int, default=300, help="How often to check MT5 health in seconds.")
    parser.add_argument("--status-port", type=int, default=8765, help="Port for the read-only status page.")
    args = parser.parse_args()

    logger.info("Starting local Windows runtime. MT5 logic remains on the desktop machine; Vercel remains read-only.")
    run_local_windows_runtime(poll_interval_seconds=args.poll_seconds, status_port=args.status_port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.info("Local runtime stopped by user interrupt.")
        raise SystemExit(0)
    except Exception as exc:
        logger.exception("Scanner startup failed: %s", exc)
        sys.exit(1)
