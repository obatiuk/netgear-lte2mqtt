import asyncio
import contextlib
import logging
import signal
import sys

from netgear_lte2mqtt.app import MonitorApp, check_health
from netgear_lte2mqtt.config import get_config

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


async def main() -> None:
    """Bootstraps configuration, registers signal handlers, and runs the monitor daemon."""
    if "--healthcheck" in sys.argv[1:]:
        sys.exit(0 if check_health() else 1)

    try:
        config = get_config()
        logging.getLogger().setLevel(config.LOG_LEVEL)
        app = MonitorApp(config)

        # Handle termination signals gracefully
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, app.stop)

        await app.run()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Application failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
