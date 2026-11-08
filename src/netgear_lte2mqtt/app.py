import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

from netgear_lte2mqtt.config import ALLOWED_TOPIC_PLACEHOLDERS, Config
from netgear_lte2mqtt.modem_client import ModemClient
from netgear_lte2mqtt.mqtt_client import MqttClient

logger = logging.getLogger(__name__)

MODEM_HTTP_TIMEOUT = 10
INITIAL_PLACEHOLDER_MAX_ATTEMPTS = 3
INITIAL_PLACEHOLDER_RETRY_DELAY = 2
HEARTBEAT_FILE = Path("/tmp/healthcheck")
STATE_TRACKED_KEYS = ("wire_connected", "mobile_connected", "upstream", "connection_text", "roaming")


def check_health() -> bool:
    """Returns True if the service has completed startup and is running."""
    return HEARTBEAT_FILE.is_file()


def _has_topic_placeholders(topic: str) -> bool:
    """Returns True if the configured MQTT topic contains dynamic modem placeholders."""
    return any(f"{{{field}}}" in topic for field in ALLOWED_TOPIC_PLACEHOLDERS)


def _resolve_topic(topic: str, status: dict[str, Any] | None) -> str:
    """Replaces {model} and {serial_number} placeholders in the MQTT topic."""
    if not status:
        raise RuntimeError(f"Cannot resolve MQTT_TOPIC '{topic}': modem status is unavailable")

    resolved = topic
    for field in ALLOWED_TOPIC_PLACEHOLDERS:
        placeholder = f"{{{field}}}"
        if placeholder in resolved:
            value = status.get(field)
            if not value:
                raise RuntimeError(f"Cannot resolve MQTT_TOPIC '{topic}': modem did not return '{field}'")
            resolved = resolved.replace(placeholder, str(value))
    return resolved


def _format_seconds(seconds: int) -> str:
    """Formats seconds into human-readable H M S."""
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    h_unit = "hour" if hours == 1 else "hours"
    m_unit = "minute" if mins == 1 else "minutes"
    s_unit = "second" if secs == 1 else "seconds"
    return f"{hours} {h_unit} {mins} {m_unit} and {secs} {s_unit}"


class MonitorApp:
    """Orchestrator that monitors modem status and publishes to MQTT."""

    __slots__ = (
        "_config",
        "_last_state_summary",
        "_modem_client",
        "_modem_online",
        "_mqtt_client",
        "_stop_event",
    )

    def __init__(self, config: Config) -> None:
        """Initializes the monitor application with validated configuration."""
        self._config = config
        self._mqtt_client = MqttClient(config)
        self._modem_client: ModemClient | None = None
        self._stop_event = asyncio.Event()
        self._modem_online: bool | None = None
        self._last_state_summary: dict[str, Any] | None = None

    async def run(self) -> None:
        """Main execution loop of the application."""
        # Log bootstrap info
        self._log_startup()

        try:
            jar = aiohttp.CookieJar(unsafe=True)
            timeout = aiohttp.ClientTimeout(total=MODEM_HTTP_TIMEOUT)
            async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout) as session:
                modem_client = ModemClient(self._config, session)
                self._modem_client = modem_client
                initial_status: dict[str, Any] | None = None

                if _has_topic_placeholders(self._config.MQTT_TOPIC):
                    initial_status = await self._initialize_dynamic_topic(modem_client)
                    await self._mqtt_client.connect(stop_event=self._stop_event)
                else:
                    await self._mqtt_client.connect(stop_event=self._stop_event)
                    if not self._stop_event.is_set():
                        try:
                            await modem_client.login()
                        except Exception as e:  # noqa: BLE001
                            logger.warning(
                                f"Initial modem login failed ({e}); "
                                "will publish empty status and retry on next poll cycle"
                            )

                if self._stop_event.is_set():
                    return

                logger.info(
                    f"Publishing modem status to topic {self._mqtt_client.topic} every "
                    f"{_format_seconds(self._config.MQTT_PUBLISH_INTERVAL)}"
                )
                self._set_healthy(True)

                while not self._stop_event.is_set():
                    await self._poll_and_publish(prefetched_status=initial_status)
                    initial_status = None

                    # Wait for interval or shutdown signal
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.MQTT_PUBLISH_INTERVAL)

        except Exception as e:
            logger.error(f"Critical application error: {e}")
            raise
        finally:
            self._cleanup()

    async def _initialize_dynamic_topic(self, modem_client: ModemClient) -> dict[str, Any]:
        """Queries the modem to resolve {model} / {serial_number} placeholders before MQTT connect."""
        logger.info(f"Resolving dynamic topic placeholders for '{self._config.MQTT_TOPIC}'...")

        last_error: Exception | None = None
        for attempt in range(1, INITIAL_PLACEHOLDER_MAX_ATTEMPTS + 1):
            try:
                await modem_client.login()
                status = await modem_client.get_status()
                resolved_topic = _resolve_topic(self._config.MQTT_TOPIC, status)
                self._mqtt_client.set_topic(resolved_topic)
                logger.info(f"Resolved MQTT topic '{self._config.MQTT_TOPIC}' -> '{resolved_topic}'")
                return status or {}
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < INITIAL_PLACEHOLDER_MAX_ATTEMPTS:
                    logger.warning(
                        f"Attempt {attempt}/{INITIAL_PLACEHOLDER_MAX_ATTEMPTS} to resolve topic placeholders "
                        f"failed ({e}). Retrying in {INITIAL_PLACEHOLDER_RETRY_DELAY}s..."
                    )
                    await asyncio.sleep(INITIAL_PLACEHOLDER_RETRY_DELAY)

        raise RuntimeError(
            f"Failed to resolve MQTT_TOPIC '{self._config.MQTT_TOPIC}' after "
            f"{INITIAL_PLACEHOLDER_MAX_ATTEMPTS} attempts: {last_error}"
        )

    def stop(self) -> None:
        """Signals the application to shut down gracefully."""
        logger.info("Shutdown signal received...")
        self._stop_event.set()

    async def _poll_and_publish(self, prefetched_status: dict[str, Any] | None = None) -> None:
        """Polls modem for status and publishes result to MQTT."""
        status: dict[str, Any] = {}
        result: dict[str, Any] | None = prefetched_status

        if result is None and self._modem_client is not None:
            result = await self._modem_client.get_status()

        if result is not None:
            status = result
            self._log_state_transition(result)
        else:
            if self._modem_online is not False:
                logger.warning("Modem is unreachable; publishing empty status '{}' to clear stale state")
            else:
                logger.debug("Modem remains unreachable; publishing empty status '{}'")
            self._modem_online = False
            self._last_state_summary = None

        self._mqtt_client.publish_status(status)

    def _log_state_transition(self, result: dict[str, Any]) -> None:
        """Logs connection state transitions and recoveries at INFO level."""
        if self._modem_online is False:
            logger.info("Modem connection restored; resuming status telemetry publishing")
        self._modem_online = True

        current_summary = {key: result.get(key) for key in STATE_TRACKED_KEYS}
        if self._last_state_summary is None:
            logger.info(
                f"Modem state: upstream={current_summary['upstream']!r}, "
                f"wire_connected={current_summary['wire_connected']}, "
                f"mobile_connected={current_summary['mobile_connected']}, "
                f"connection_text={current_summary['connection_text']!r}, "
                f"roaming={current_summary['roaming']}"
            )
        elif current_summary != self._last_state_summary:
            changes = ", ".join(
                f"{key}: {self._last_state_summary.get(key)!r} -> {val!r}"
                for key, val in current_summary.items()
                if self._last_state_summary.get(key) != val
            )
            logger.info(f"Modem state changed ({changes})")

        self._last_state_summary = current_summary

    def _set_healthy(self, healthy: bool) -> None:
        """Creates or removes the service readiness file."""
        try:
            if healthy:
                HEARTBEAT_FILE.touch()
            else:
                HEARTBEAT_FILE.unlink(missing_ok=True)
        except OSError as e:
            logger.debug(f"Failed to update healthcheck file '{HEARTBEAT_FILE}': {e}")

    def _log_startup(self) -> None:
        """Logs the application start timestamp and sanitized configuration."""
        timestamp = datetime.now(UTC).isoformat()
        logger.info(f"Started at {timestamp}")
        logger.info("Config:")
        for key, value in self._config.sanitize().items():
            logger.info(f"  {key}: {value}")

    def _cleanup(self) -> None:
        """Performs final cleanup of clients."""
        self._set_healthy(False)
        self._mqtt_client.disconnect()
        logger.info("Application cleanup complete")
