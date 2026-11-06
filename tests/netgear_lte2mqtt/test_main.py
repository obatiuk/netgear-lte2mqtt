import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netgear_lte2mqtt.main import main


class TestMain:
    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.main.get_config")
    @patch("netgear_lte2mqtt.main.MonitorApp")
    async def test_main_success(self, mock_app_cls, mock_get_config):
        # Verify main bootstraps config, sets log level, and runs MonitorApp
        # Setup mocks
        mock_config = MagicMock()
        mock_config.LOG_LEVEL = "DEBUG"
        mock_get_config.return_value = mock_config

        mock_app = mock_app_cls.return_value
        mock_app.run = AsyncMock()

        # main is an async function, so we must await it in tests
        await main()

        mock_get_config.assert_called_once()
        assert logging.getLogger().level == logging.DEBUG
        mock_app_cls.assert_called_once_with(mock_config)
        mock_app.run.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.main.get_config")
    async def test_main_config_error(self, mock_get_config):
        # Verify startup exceptions are logged and exit with code 1
        # Simulate config failure during bootstrap
        mock_get_config.side_effect = Exception("Config Error")

        # main catches the exception inside its try-except and calls sys.exit(1)
        with patch("sys.exit") as mock_exit:
            await main()
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("is_healthy", "expected_exit_code"),
        [
            (True, 0),
            (False, 1),
        ],
    )
    async def test_main_healthcheck_flag(self, is_healthy, expected_exit_code):
        # Verify --healthcheck exits with 0 when healthy and 1 when unhealthy
        with (
            patch("sys.argv", ["netgear_lte2mqtt.main", "--healthcheck"]),
            patch("netgear_lte2mqtt.main.check_health", return_value=is_healthy),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()

        assert exc_info.value.code == expected_exit_code
