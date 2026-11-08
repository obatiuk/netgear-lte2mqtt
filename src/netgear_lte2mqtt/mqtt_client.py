import asyncio
import contextlib
import json
import logging
import ssl
from typing import Any

from paho.mqtt.client import Client, MQTTv5
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from netgear_lte2mqtt.config import Config

logger = logging.getLogger(__name__)

MQTT_QOS = 1
MQTT_SUCCESS_RC = 0
MQTT_KEEPALIVE_SECONDS = 60
MIN_RECONNECT_DELAY = 1
BACKOFF_BASE = 2
MAX_BACKOFF_SECONDS = 60
PUBLISH_TIMEOUT_SECONDS = 5.0
EXPIRY_INTERVAL_MULTIPLIER = 3
EMPTY_STATUS_PAYLOAD = json.dumps({})


class MqttClient:
    """Client for managing MQTT connectivity and publishing."""

    __slots__ = ("_client", "_config", "_connected", "_publish_properties", "_session_active", "_topic")

    def __init__(self, config: Config) -> None:
        """Initializes the MQTT v5 client, properties, Last Will, authentication, and TLS."""
        self._config = config
        self._topic = config.MQTT_TOPIC
        self._connected = False
        self._session_active = True
        self._publish_properties = Properties(PacketTypes.PUBLISH)
        self._publish_properties.MessageExpiryInterval = config.MQTT_PUBLISH_INTERVAL * EXPIRY_INTERVAL_MULTIPLIER

        self._client = Client(
            client_id=config.MQTT_CLIENT_ID,
            protocol=MQTTv5,
            callback_api_version=CallbackAPIVersion.VERSION2,
        )
        self._client.connect_timeout = float(config.MQTT_CONNECTION_TIMEOUT)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=MIN_RECONNECT_DELAY, max_delay=MAX_BACKOFF_SECONDS)
        self._setup_auth()
        self.set_topic(self._topic)
        self._setup_tls()
        self._client.enable_logger()

    @property
    def topic(self) -> str:
        """Returns the active MQTT topic."""
        return self._topic

    def set_topic(self, topic: str) -> None:
        """Updates the active MQTT topic and configures the Last Will message."""
        self._topic = topic
        self._client.will_set(
            self._topic,
            payload=EMPTY_STATUS_PAYLOAD,
            qos=MQTT_QOS,
            retain=True,
        )
        logger.debug(f"Configured MQTT Last Will on topic '{self._topic}' with payload '{EMPTY_STATUS_PAYLOAD}'")

    def _setup_auth(self) -> None:
        """Configures username and password authentication if provided."""
        if self._config.MQTT_USERNAME:
            self._client.username_pw_set(self._config.MQTT_USERNAME, self._config.MQTT_PASSWORD or None)
            logger.debug(f"Configured MQTT authentication for user '{self._config.MQTT_USERNAME}'")

    def _setup_tls(self) -> None:
        """Configures TLS settings for the MQTT client."""
        if self._config.MQTT_TLS:
            ca_certs = self._config.MQTT_CA_CERT_PATH or None
            cert_reqs = ssl.CERT_REQUIRED if self._config.MQTT_VALIDATE_CERT else ssl.CERT_NONE
            self._client.tls_set(
                ca_certs=ca_certs,
                cert_reqs=cert_reqs,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
            self._client.tls_insecure_set(not self._config.MQTT_VALIDATE_CERT)
            logger.debug(
                f"Configured MQTT TLS (validate_cert={self._config.MQTT_VALIDATE_CERT}, "
                f"ca_certs={ca_certs or 'system-default'})"
            )

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
        """Callback invoked when the client connects or reconnects to the MQTT broker."""
        if reason_code == MQTT_SUCCESS_RC:
            self._session_active = True
            logger.info(f"MQTT session active with broker at {self._config.MQTT_HOST}:{self._config.MQTT_PORT}")
        else:
            self._session_active = False
            logger.error(f"MQTT broker connection refused (reason_code={reason_code})")

    def _on_disconnect(
        self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None
    ) -> None:
        """Callback invoked when the client disconnects from the MQTT broker."""
        self._session_active = False
        if reason_code == MQTT_SUCCESS_RC:
            logger.debug("MQTT client disconnected cleanly")
        else:
            logger.warning(
                f"Unexpected disconnect from MQTT broker (reason_code={reason_code}); "
                "background loop will attempt to reconnect automatically"
            )

    async def connect(self, stop_event: asyncio.Event | None = None) -> None:
        """Establishes connection to the MQTT broker with exponential backoff retry logic."""
        connect_attempts = 0
        while self._config.MQTT_MAX_RETRIES <= 0 or connect_attempts < self._config.MQTT_MAX_RETRIES:
            try:
                logger.debug(
                    f"Connecting to MQTT broker at {self._config.MQTT_HOST}:{self._config.MQTT_PORT} "
                    f"(client_id={self._config.MQTT_CLIENT_ID})..."
                )
                await asyncio.to_thread(
                    self._client.connect,
                    self._config.MQTT_HOST,
                    self._config.MQTT_PORT,
                    MQTT_KEEPALIVE_SECONDS,
                )
                logger.info(f"Connected to MQTT broker at {self._config.MQTT_HOST}:{self._config.MQTT_PORT}")
                break
            except Exception as e:
                connect_attempts += 1
                if 0 < self._config.MQTT_MAX_RETRIES <= connect_attempts:
                    logger.error(f"Failed to connect to MQTT broker after {connect_attempts} attempts")
                    raise

                max_retries_label = str(self._config.MQTT_MAX_RETRIES) if self._config.MQTT_MAX_RETRIES > 0 else "∞"
                wait_time = min(BACKOFF_BASE ** (connect_attempts - 1), MAX_BACKOFF_SECONDS)
                logger.warning(
                    f"MQTT connection attempt {connect_attempts}/{max_retries_label} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                if stop_event is not None:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(stop_event.wait(), timeout=wait_time)
                    if stop_event.is_set():
                        return
                else:
                    await asyncio.sleep(wait_time)

        self._client.loop_start()
        self._connected = True
        self._session_active = True

    def publish_status(self, status: dict[str, Any], *, wait: bool = False) -> bool:
        """Publishes the modem status dictionary as JSON to the configured MQTT topic."""
        if not self._session_active:
            logger.error(f"Failed to publish status to topic '{self._topic}': MQTT session is not active")
            return False

        payload = json.dumps(status) if status else EMPTY_STATUS_PAYLOAD

        try:
            result = self._client.publish(
                self._topic,
                payload,
                qos=MQTT_QOS,
                retain=True,
                properties=self._publish_properties,
            )
            if result[0] == MQTT_SUCCESS_RC:
                if wait and hasattr(result, "wait_for_publish"):
                    result.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
                expiry_seconds = self._config.MQTT_PUBLISH_INTERVAL * EXPIRY_INTERVAL_MULTIPLIER
                logger.debug(
                    f"Published status to topic '{self._topic}' "
                    f"(qos={MQTT_QOS}, retain=True, expiry={expiry_seconds}s): {payload}"
                )
                return True

            logger.error(f"Failed to publish status to topic '{self._topic}' (rc={result[0]})")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error(f"Exception while publishing status to topic '{self._topic}': {e}")
            return False

    def disconnect(self) -> None:
        """Publishes empty status, disconnects from the broker, and stops the MQTT loop."""
        if not self._connected:
            return
        logger.debug("Publishing empty status payload before disconnecting from MQTT broker...")
        self.publish_status({}, wait=True)
        self._client.disconnect()
        self._client.loop_stop()
        self._connected = False
        self._session_active = False
        logger.info("Disconnected from MQTT broker")
