import json
import ssl
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from netgear_lte2mqtt.mqtt_client import EXPIRY_INTERVAL_MULTIPLIER, PUBLISH_TIMEOUT_SECONDS, MqttClient


class TestMqttClient:
    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.mqtt_client.Client")
    async def test_connect_success(self, mock_client_cls, mock_config):
        # Verify Last Will configuration, broker connection, and background network loop start
        mock_client = mock_client_cls.return_value
        client = MqttClient(mock_config)

        assert client.topic == mock_config.MQTT_TOPIC
        await client.connect()

        mock_client.will_set.assert_called_once_with(mock_config.MQTT_TOPIC, payload=json.dumps({}), qos=1, retain=True)
        mock_client.connect.assert_called_once_with(
            mock_config.MQTT_HOST, mock_config.MQTT_PORT, mock_config.MQTT_CONNECTION_TIMEOUT
        )
        mock_client.loop_start.assert_called_once()

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_auth_configured_when_username_present(self, mock_client_cls, mock_config):
        # Verify broker username and password credentials are set when configured
        mock_client = mock_client_cls.return_value
        auth_config = replace(mock_config, MQTT_USERNAME="broker_user", MQTT_PASSWORD="broker_password")

        MqttClient(auth_config)

        mock_client.username_pw_set.assert_called_once_with("broker_user", "broker_password")

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.mqtt_client.Client")
    async def test_connect_retry_then_success(self, mock_client_cls, mock_config):
        mock_client = mock_client_cls.return_value
        # Fail twice, then succeed
        mock_client.connect.side_effect = [Exception("Fail"), Exception("Fail"), None]
        client = MqttClient(mock_config)

        with patch("asyncio.sleep", return_value=None):  # Don't actually sleep in tests
            await client.connect()

        assert mock_client.connect.call_count == 3

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.mqtt_client.Client")
    async def test_connect_max_retries_exceeded(self, mock_client_cls, mock_config):
        # Verify connection failure raises after exhausting configured retries
        mock_client = mock_client_cls.return_value
        mock_client.connect.side_effect = RuntimeError("Permanent Fail")
        client = MqttClient(mock_config)

        with patch("asyncio.sleep", return_value=None), pytest.raises(RuntimeError, match="Permanent Fail"):
            await client.connect()

        assert mock_client.connect.call_count == 3

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_publish_status_success(self, mock_client_cls, mock_config):
        # Verify JSON payload, QoS 1, retain flag, and MQTT v5 MessageExpiryInterval property
        mock_client = mock_client_cls.return_value
        mock_client.publish.return_value = (0, None)  # Return code 0 for success
        client = MqttClient(mock_config)
        status = {"wire_connected": True, "upstream": "Wired"}

        published = client.publish_status(status)

        assert published is True
        mock_client.publish.assert_called_once()
        call_args, call_kwargs = mock_client.publish.call_args
        assert call_args == (mock_config.MQTT_TOPIC, json.dumps(status))
        assert call_kwargs["qos"] == 1
        assert call_kwargs["retain"] is True
        assert (
            call_kwargs["properties"].MessageExpiryInterval
            == mock_config.MQTT_PUBLISH_INTERVAL * EXPIRY_INTERVAL_MULTIPLIER
        )

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_publish_status_fail(self, mock_client_cls, mock_config):
        # Simulate MQTT publish failure (return code != 0)
        mock_client = mock_client_cls.return_value
        mock_client.publish.return_value = (1, "Failure")
        client = MqttClient(mock_config)

        # Should return False and not crash when publishing fails
        published = client.publish_status({"wire_connected": True})
        assert published is False

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_publish_exception_returns_false(self, mock_client_cls, mock_config):
        # Test that publishing doesn't crash if client raises an exception
        mock_client = mock_client_cls.return_value
        mock_client.publish.side_effect = RuntimeError("Socket closed")
        client = MqttClient(mock_config)

        published = client.publish_status({"wire_connected": False})
        assert published is False

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.mqtt_client.Client")
    async def test_disconnect_waits_for_empty_publish_only_when_connected(self, mock_client_cls, mock_config):
        mock_client = mock_client_cls.return_value
        mock_msg_info = MagicMock()
        mock_msg_info.__getitem__.side_effect = lambda idx: 0 if idx == 0 else None
        mock_client.publish.return_value = mock_msg_info
        client = MqttClient(mock_config)

        # Calling disconnect before connect should be a no-op
        client.disconnect()
        mock_client.publish.assert_not_called()
        mock_client.disconnect.assert_not_called()

        await client.connect()
        client.disconnect()

        mock_msg_info.wait_for_publish.assert_called_once_with(timeout=PUBLISH_TIMEOUT_SECONDS)
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_callbacks_log_without_error(self, mock_client_cls, mock_config):
        client = MqttClient(mock_config)
        # Verify connect and disconnect callbacks handle both success and error reason codes
        client._on_connect(None, None, None, 0)
        client._on_connect(None, None, None, 135)
        client._on_disconnect(None, None, None, 0)
        client._on_disconnect(None, None, None, 1)

    @patch("netgear_lte2mqtt.mqtt_client.Client")
    def test_setup_tls_enabled(self, mock_client_cls, mock_config):
        # Verify TLS client protocol, custom CA certificate path, and certificate validation
        mock_client = mock_client_cls.return_value
        tls_config = replace(
            mock_config,
            MQTT_PORT=8883,
            MQTT_TLS=True,
            MQTT_VALIDATE_CERT=True,
            MQTT_CA_CERT_PATH="/path/to/ca.crt",
        )

        MqttClient(tls_config)

        mock_client.tls_set.assert_called_once_with(
            ca_certs="/path/to/ca.crt",
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        mock_client.tls_insecure_set.assert_called_once_with(False)
