import logging
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netgear_lte2mqtt.main import main

DOCKERFILE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "Dockerfile"
DURATION_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)(ns|us|\u00b5s|ms|s|m|h)")
DURATION_UNIT_SECONDS = {
    "ns": 1e-9,
    "us": 1e-6,
    "\u00b5s": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}


def _parse_go_duration_seconds(raw: str) -> float:
    """Parses a Dockerfile/Go duration literal into seconds, raising ValueError if invalid."""
    if not raw or raw.startswith("-"):
        raise ValueError(f"Invalid positive duration: {raw!r}")
    unsigned = raw.removeprefix("+")
    pos = 0
    total = 0.0
    for match in DURATION_TOKEN_RE.finditer(unsigned):
        if match.start() != pos:
            raise ValueError(f"Invalid duration syntax: {raw!r}")
        total += float(match.group(1)) * DURATION_UNIT_SECONDS[match.group(2)]
        pos = match.end()
    if pos != len(unsigned) or pos == 0:
        raise ValueError(f"Invalid duration syntax: {raw!r}")
    return total


class TestMain:
    @pytest.mark.asyncio
    @patch("netgear_lte2mqtt.main.get_config")
    @patch("netgear_lte2mqtt.main.MonitorApp")
    async def test_main_success(self, mock_app_cls: MagicMock, mock_get_config: MagicMock) -> None:
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
    async def test_main_config_error(self, mock_get_config: MagicMock) -> None:
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
    async def test_main_healthcheck_flag(self, is_healthy: bool, expected_exit_code: int) -> None:
        # Verify --healthcheck exits with 0 when healthy and 1 when unhealthy
        with (
            patch("sys.argv", ["netgear_lte2mqtt.main", "--healthcheck"]),
            patch("netgear_lte2mqtt.main.check_health", return_value=is_healthy),
            pytest.raises(SystemExit) as exc_info,
        ):
            await main()

        assert exc_info.value.code == expected_exit_code

    def test_dockerfile_healthcheck_options_are_valid(self) -> None:
        # Regression: Verify Dockerfile HEALTHCHECK flags use strictly positive durations and target --healthcheck
        logical_lines: list[str] = []
        current = ""
        for raw_line in DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith("\\"):
                current += f"{stripped[:-1].rstrip()} "
            else:
                logical_lines.append(f"{current}{stripped}")
                current = ""

        healthchecks = [line for line in logical_lines if line.startswith("HEALTHCHECK ")]
        assert len(healthchecks) == 1

        before_cmd, sep, cmd_part = healthchecks[0].removeprefix("HEALTHCHECK ").partition("CMD ")
        assert sep == "CMD "
        assert "netgear_lte2mqtt.main" in cmd_part
        assert "--healthcheck" in cmd_part

        for token in before_cmd.split():
            assert token.startswith("--"), f"Unexpected HEALTHCHECK token: {token!r}"
            assert "=" in token, f"Missing value in HEALTHCHECK option: {token!r}"
            flag, value = token.removeprefix("--").split("=", 1)
            match flag:
                case "interval" | "timeout" | "start-period" | "start-interval":
                    assert _parse_go_duration_seconds(value) > 0, f'Interval "{flag}" must be positive, got {value!r}'
                case "retries":
                    assert int(value) >= 1
                case _:
                    pytest.fail(f"Unknown HEALTHCHECK option: --{flag}")
