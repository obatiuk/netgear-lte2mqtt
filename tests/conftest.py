import random
import string
from unittest.mock import MagicMock

import pytest

from netgear_lte2mqtt.config import Config


@pytest.fixture(scope="session")
def helpers():
    """Provides shared random string generators for test fixtures."""

    class TestHelpers:
        @staticmethod
        def random_string(length=8):
            letters = string.ascii_letters + string.digits
            return "".join(random.choice(letters) for _ in range(length))

    return TestHelpers


@pytest.fixture
def base_env(helpers):
    """Provides the minimal required environment variables for configuration tests."""
    return {
        "MODEM_HOST": helpers.random_string(15),
        "MODEM_PASSWORD": helpers.random_string(12),
        "MQTT_HOST": helpers.random_string(10),
    }


@pytest.fixture
def mock_config(helpers):
    """Provides a validated Config instance with randomized hosts and credentials."""
    return Config(
        MODEM_HOST=helpers.random_string(15),
        MODEM_PASSWORD=helpers.random_string(12),
        MQTT_TOPIC=helpers.random_string(10),
        MQTT_HOST=helpers.random_string(8),
        MQTT_PORT=1883,
        MQTT_CLIENT_ID=helpers.random_string(12),
        MQTT_USERNAME="",
        MQTT_PASSWORD="",
        MQTT_TLS=False,
        MQTT_VALIDATE_CERT=False,
        MQTT_CA_CERT_PATH="",
        MQTT_CONNECTION_TIMEOUT=60,
        MQTT_MAX_RETRIES=3,
        MQTT_PUBLISH_INTERVAL=1,  # Short interval for testing
        LOG_LEVEL="INFO",
    )


@pytest.fixture
def mock_session():
    """Provides a mocked aiohttp ClientSession for modem client tests."""
    return MagicMock()
