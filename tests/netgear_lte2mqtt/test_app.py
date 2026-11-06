import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from netgear_lte2mqtt import app as app_module
from netgear_lte2mqtt.app import (
    INITIAL_PLACEHOLDER_MAX_ATTEMPTS,
    MonitorApp,
    _format_seconds,
    _resolve_topic,
    check_health,
)


class TestMonitorApp:
    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_run_cycle(self, mock_modem_cls, mock_mqtt_cls, mock_config):
        # Verify full poll-and-publish lifecycle and clean disconnect on stop
        # Setup mocks
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock()  # IMPORTANT: connect is async
        mock_mqtt.publish_status.return_value = True

        expected_status = {"wire_connected": True, "upstream": "Wired"}
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()  # IMPORTANT: login is async
        mock_modem.get_status = AsyncMock(return_value=expected_status)

        app = MonitorApp(mock_config)

        # Start the app in a task so we can stop it
        run_task = asyncio.create_task(app.run())

        # Give it time to run at least one cycle
        await asyncio.sleep(1.5)

        # Stop and wait for completion
        app.stop()
        await run_task

        # Verify interactions
        mock_mqtt.connect.assert_called_once()
        mock_modem.login.assert_called_once()
        # Should have published status at least once
        assert mock_mqtt.publish_status.called
        mock_mqtt.publish_status.assert_any_call(expected_status)
        mock_mqtt.disconnect.assert_called_once()

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_run_resolves_topic_placeholders_without_double_poll(
        self, mock_modem_cls, mock_mqtt_cls, mock_config
    ):
        # Verify dynamic MQTT_TOPIC placeholders resolve before MQTT connect and reuse initial status
        # Setup mocks with placeholders in MQTT_TOPIC
        placeholder_config = replace(mock_config, MQTT_TOPIC="netgear-lte2mqtt/{model}/{serial_number}/state")
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock()
        mock_mqtt.publish_status.return_value = True

        expected_status = {"model": "LB1120", "serial_number": "SN123", "wire_connected": True}
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        mock_modem.get_status = AsyncMock(return_value=expected_status)

        app = MonitorApp(placeholder_config)
        run_task = asyncio.create_task(app.run())
        await asyncio.sleep(0.3)
        app.stop()
        await run_task

        # Verify topic placeholders were resolved before connecting to MQTT and initial status was reused
        mock_mqtt.set_topic.assert_called_once_with("netgear-lte2mqtt/LB1120/SN123/state")
        mock_mqtt.connect.assert_called_once()
        assert mock_modem.get_status.call_count == 1
        mock_mqtt.publish_status.assert_called_once_with(expected_status)

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_placeholder_resolution_failure_raises_error(self, mock_modem_cls, mock_mqtt_cls, mock_config):
        # Verify startup aborts before MQTT connection if dynamic topic placeholders cannot be resolved
        placeholder_config = replace(mock_config, MQTT_TOPIC="netgear-lte2mqtt/{model}/state")
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock()

        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        mock_modem.get_status = AsyncMock(return_value=None)

        app = MonitorApp(placeholder_config)
        with (
            patch("asyncio.sleep", return_value=None),
            pytest.raises(RuntimeError, match="Failed to resolve MQTT_TOPIC"),
        ):
            await app.run()

        assert mock_modem.get_status.call_count == INITIAL_PLACEHOLDER_MAX_ATTEMPTS
        mock_mqtt.connect.assert_not_called()

    def test_resolve_topic_missing_field_raises_error(self):
        # Verify _resolve_topic raises RuntimeError when a required placeholder value is None
        with pytest.raises(RuntimeError, match="modem did not return 'model'"):
            _resolve_topic("netgear-lte2mqtt/{model}/state", {"wire_connected": True, "model": None})

    def test_format_seconds(self):
        # Verify singular and plural unit formatting for interval durations
        assert _format_seconds(3661) == "1 hour 1 minute and 1 second"
        assert _format_seconds(60) == "0 hours 1 minute and 0 seconds"

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_initial_login_failure_on_static_topic_continues_polling(
        self, mock_modem_cls, mock_mqtt_cls, mock_config
    ):
        # Verify static topic startup survives initial modem unreachability and publishes empty state
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock()
        mock_mqtt.publish_status.return_value = True

        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock(side_effect=Exception("Modem rebooting"))
        mock_modem.get_status = AsyncMock(return_value=None)

        app = MonitorApp(mock_config)
        run_task = asyncio.create_task(app.run())
        await asyncio.sleep(0.3)
        app.stop()
        await run_task

        mock_mqtt.connect.assert_called_once()
        mock_mqtt.publish_status.assert_called_with({})

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_state_transition_and_recovery_logging(self, mock_modem_cls, mock_mqtt_cls, mock_config):
        # Verify state change and connection recovery transitions are logged at INFO level
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.publish_status.return_value = False

        mock_modem = mock_modem_cls.return_value
        state_wired = {
            "wire_connected": True,
            "mobile_connected": False,
            "upstream": "Wired",
            "connection_text": "Connected",
            "roaming": False,
        }
        state_lte = {
            "wire_connected": False,
            "mobile_connected": True,
            "upstream": "Mobile",
            "connection_text": "Connected",
            "roaming": False,
        }
        mock_modem.get_status = AsyncMock(side_effect=[state_wired, state_lte, None, state_wired])

        app = MonitorApp(mock_config)
        app._modem_client = mock_modem

        with patch("netgear_lte2mqtt.app.logger.info") as mock_log_info:
            await app._poll_and_publish()
            await app._poll_and_publish()
            await app._poll_and_publish()
            await app._poll_and_publish()

            messages = [call.args[0] for call in mock_log_info.call_args_list]
            assert any("Modem state changed" in msg for msg in messages)
            assert any("Modem connection restored" in msg for msg in messages)

    def test_healthcheck_lifecycle_and_oserror(self, mock_config, tmp_path):
        # Verify readiness file creation on startup and removal on cleanup
        heartbeat_file = tmp_path / "healthcheck"
        app = MonitorApp(mock_config)

        with patch.object(app_module, "HEARTBEAT_FILE", heartbeat_file):
            assert check_health() is False

            app._set_healthy(True)
            assert check_health() is True

            app._cleanup()
            assert check_health() is False

        # Verify OSError is caught and does not crash the daemon
        bad_path = tmp_path / "nonexistent_dir" / "healthcheck"
        with patch.object(app_module, "HEARTBEAT_FILE", bad_path):
            app._set_healthy(True)

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    async def test_bootstrap_failure(self, mock_mqtt_cls, mock_config):
        # Verify critical MQTT connection failure propagates during startup
        # Simulate critical connection error during bootstrap
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock(side_effect=RuntimeError("MQTT Connection Failed"))

        app = MonitorApp(mock_config)
        with pytest.raises(RuntimeError, match="MQTT Connection Failed"):
            await app.run()

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    @patch("netgear_lte2mqtt.app.ModemClient")
    async def test_run_modem_unavailable(self, mock_modem_cls, mock_mqtt_cls, mock_config):
        # Verify unreachable modem publishes empty status payload to clear stale state
        mock_mqtt = mock_mqtt_cls.return_value
        mock_mqtt.connect = AsyncMock()
        mock_mqtt.publish_status.return_value = True

        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        # Modem returns None (error)
        mock_modem.get_status = AsyncMock(return_value=None)

        app = MonitorApp(mock_config)
        run_task = asyncio.create_task(app.run())

        await asyncio.sleep(1.2)
        app.stop()
        await run_task

        # Should publish empty dict when modem is unreachable
        mock_mqtt.publish_status.assert_any_call({})

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.app.MqttClient")
    async def test_cleanup(self, mock_mqtt_cls, mock_config):
        # Verify _cleanup disconnects the MQTT client
        mock_mqtt = mock_mqtt_cls.return_value
        app = MonitorApp(mock_config)

        # Trigger cleanup directly or via stop
        app._cleanup()
        mock_mqtt.disconnect.assert_called_once()
