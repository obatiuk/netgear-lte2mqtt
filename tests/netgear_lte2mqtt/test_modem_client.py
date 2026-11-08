from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netgear_lte2mqtt.config import Config
from netgear_lte2mqtt.modem_client import MAX_STATUS_ATTEMPTS, STATUS_FIELDS, ModemClient


class TestModemClient:
    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_login_success(self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock) -> None:
        # Verify login passes the configured modem password to eternalegypt
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()

        client = ModemClient(mock_config, mock_session)
        await client.login()

        mock_modem.login.assert_called_once_with(password=mock_config.MODEM_PASSWORD)

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_login_failure(self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock) -> None:
        # Verify authentication errors propagate to the caller
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock(side_effect=RuntimeError("Auth failed"))

        client = ModemClient(mock_config, mock_session)
        with pytest.raises(RuntimeError, match="Auth failed"):
            await client.login()

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_get_status_success(
        self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock
    ) -> None:
        # Verify status dictionary extraction and general.model fallback
        mock_modem = mock_modem_cls.return_value
        mock_result = MagicMock()
        mock_result.model = None
        mock_result.items = {"general.model": "LB1120"}
        mock_result.serial_number = "SN0000000000"
        mock_result.wire_connected = True
        mock_result.mobile_connected = False
        mock_result.upstream = "Wired"
        mock_result.usage = 1048576
        mock_modem.information = AsyncMock(return_value=mock_result)

        client = ModemClient(mock_config, mock_session)
        status = await client.get_status()

        assert status is not None
        assert set(status.keys()) == set(STATUS_FIELDS)
        assert status["model"] == "LB1120"
        assert status["serial_number"] == "SN0000000000"
        assert status["wire_connected"] is True
        assert status["mobile_connected"] is False
        assert status["upstream"] == "Wired"
        assert status["usage"] == 1048576

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_get_status_empty_response_triggers_relogin(
        self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock
    ) -> None:
        # Verify empty wire_connected response triggers re-authentication and retry
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        expired_result = MagicMock()
        expired_result.wire_connected = None
        valid_result = MagicMock()
        valid_result.wire_connected = True
        mock_modem.information = AsyncMock(side_effect=[expired_result, valid_result])

        client = ModemClient(mock_config, mock_session)
        with patch("netgear_lte2mqtt.modem_client.logger.warning") as mock_log_warning:
            status = await client.get_status()

        assert status is not None
        assert status["wire_connected"] is True
        mock_log_warning.assert_not_called()
        mock_modem.login.assert_awaited_once_with(password=mock_config.MODEM_PASSWORD)
        assert mock_modem.information.call_count == MAX_STATUS_ATTEMPTS

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_get_status_relogin_success(
        self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock
    ) -> None:
        # Verify exception during information() triggers re-authentication and retry
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        mock_result = MagicMock()
        mock_result.wire_connected = True
        mock_modem.information = AsyncMock(side_effect=[Exception("Session expired"), mock_result])

        client = ModemClient(mock_config, mock_session)
        with patch("netgear_lte2mqtt.modem_client.logger.warning") as mock_log_warning:
            status = await client.get_status()

        assert status is not None
        assert status["wire_connected"] is True
        mock_log_warning.assert_not_called()
        mock_modem.login.assert_awaited_once_with(password=mock_config.MODEM_PASSWORD)
        assert mock_modem.information.call_count == MAX_STATUS_ATTEMPTS

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_get_status_error_when_relogin_fails(
        self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock
    ) -> None:
        # Verify failed re-authentication aborts the poll and returns None
        mock_modem = mock_modem_cls.return_value
        mock_modem.information = AsyncMock(side_effect=Exception("API Error"))
        mock_modem.login = AsyncMock(side_effect=Exception("Login Failed"))

        client = ModemClient(mock_config, mock_session)
        status = await client.get_status()

        assert status is None

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.modem_client.Modem")
    async def test_get_status_error(
        self, mock_modem_cls: MagicMock, mock_config: Config, mock_session: MagicMock
    ) -> None:
        # Verify persistent API error after successful re-authentication returns None
        mock_modem = mock_modem_cls.return_value
        mock_modem.login = AsyncMock()
        mock_modem.information = AsyncMock(side_effect=Exception("API Error"))

        client = ModemClient(mock_config, mock_session)
        status = await client.get_status()

        assert status is None
