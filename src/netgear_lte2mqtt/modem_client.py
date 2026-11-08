import logging
from typing import Any

import aiohttp
from eternalegypt import Modem

from netgear_lte2mqtt.config import Config

logger = logging.getLogger(__name__)

MAX_STATUS_ATTEMPTS = 2

STATUS_FIELDS = (
    "model",
    "serial_number",
    "wire_connected",
    "mobile_connected",
    "upstream",
    "connection_text",
    "connection_type",
    "current_nw_service_type",
    "current_ps_service_type",
    "register_network_display",
    "roaming",
    "radio_quality",
    "rx_level",
    "tx_level",
    "current_band",
    "cell_id",
    "usage",
)


class ModemClient:
    """Client for interacting with the Netgear modem."""

    __slots__ = ("_config", "_modem")

    def __init__(self, config: Config, session: aiohttp.ClientSession) -> None:
        """Initializes the modem client with the shared HTTP session."""
        self._config = config
        self._modem = Modem(hostname=config.MODEM_HOST, websession=session)  # pyright: ignore[reportCallIssue]

    async def login(self) -> None:
        """Performs authentication with the modem."""
        logger.debug(f"Authenticating with modem at {self._config.MODEM_HOST}...")
        try:
            await self._modem.login(password=self._config.MODEM_PASSWORD)
            logger.info(f"Successfully logged into modem at {self._config.MODEM_HOST}")
        except Exception as e:
            logger.error(f"Failed to log into modem at {self._config.MODEM_HOST}: {e}")
            raise

    async def get_status(self) -> dict[str, Any] | None:
        """
        Retrieves the current status attributes from the modem.
        Re-authenticates if the modem session has expired.
        Returns a dictionary of modem status fields, or None if an error occurs.
        """
        for attempt in range(MAX_STATUS_ATTEMPTS):
            try:
                logger.debug(
                    f"Polling modem at {self._config.MODEM_HOST} (attempt {attempt + 1}/{MAX_STATUS_ATTEMPTS})..."
                )
                result = await self._modem.information()
                # eternalegypt returns None fields without raising when the web session expires
                if getattr(result, "wire_connected", None) is None:
                    raise RuntimeError("Modem returned empty status (session expired)")

                status = {field: getattr(result, field, None) for field in STATUS_FIELDS}
                # Fall back to the raw general.model item when the top-level attribute is unpopulated
                items = getattr(result, "items", None)
                if status["model"] is None and isinstance(items, dict):
                    status["model"] = items.get("general.model")

                logger.debug(
                    f"Modem poll succeeded: model={status.get('model')}, "
                    f"serial_number={status.get('serial_number')}, "
                    f"upstream={status.get('upstream')}, "
                    f"wire_connected={status.get('wire_connected')}, "
                    f"mobile_connected={status.get('mobile_connected')}"
                )
                return status
            except Exception as e:  # noqa: BLE001
                if attempt < MAX_STATUS_ATTEMPTS - 1:
                    logger.debug(f"Error retrieving modem status ({e}), attempting re-login...")
                    try:
                        await self.login()
                    except Exception:  # noqa: BLE001
                        logger.error("Re-login attempt failed; aborting current status poll")
                        return None
                else:
                    logger.error(f"Error retrieving modem status after re-login: {e}")
        return None
