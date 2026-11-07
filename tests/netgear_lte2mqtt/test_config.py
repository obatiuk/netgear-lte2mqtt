import os
from pathlib import Path
from unittest.mock import patch

import pytest

from netgear_lte2mqtt.config import (
    MAX_CLIENT_ID_LENGTH,
    Config,
    ConfigError,
    _validate_ca_cert_path,
    get_config,
)


class TestConfig:
    @pytest.mark.parametrize(
        "missing_var",
        [
            "MODEM_HOST",
            "MODEM_PASSWORD",
            "MQTT_HOST",
        ],
    )
    def test_missing_required_env_vars(self, base_env: dict[str, str], missing_var: str) -> None:
        # Verify missing any required environment variable raises ConfigError
        test_env = {k: v for k, v in base_env.items() if k != missing_var}
        with patch.dict(os.environ, test_env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert missing_var in str(exc_info.value)

    def test_returns_config_dataclass(self, base_env: dict[str, str]) -> None:
        # Verify required environment variables populate a Config instance
        with patch.dict(os.environ, base_env, clear=True):
            config = get_config()
            assert isinstance(config, Config)
            assert config.MODEM_HOST == base_env["MODEM_HOST"]
            assert config.MODEM_PASSWORD == base_env["MODEM_PASSWORD"]
            assert config.MQTT_HOST == base_env["MQTT_HOST"]

    def test_uses_defaults_for_optional_vars(self, base_env: dict[str, str]) -> None:
        # Verify optional environment variables fall back to documented defaults
        with patch.dict(os.environ, base_env, clear=True):
            config = get_config()
            assert config.MQTT_TOPIC == "netgear-lte2mqtt/state"
            assert config.MQTT_PUBLISH_INTERVAL == 60
            assert config.MQTT_PORT == 1883
            assert config.MQTT_USERNAME == ""
            assert config.MQTT_PASSWORD == ""
            assert config.MQTT_TLS is False
            assert config.MQTT_VALIDATE_CERT is False
            assert config.MQTT_CLIENT_ID == "netgear-lte2mqtt"
            assert config.MQTT_CA_CERT_PATH == ""
            assert config.MQTT_CONNECTION_TIMEOUT == 60
            assert config.MQTT_MAX_RETRIES == 5
            assert config.LOG_LEVEL == "INFO"

    def test_custom_values_override_defaults(self, base_env: dict[str, str], tmp_path: Path) -> None:
        # Verify custom environment variables override all default settings
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text("dummy-cert", encoding="utf-8")
        env = {
            **base_env,
            "MQTT_TOPIC": "netgear-lte2mqtt/{model}/{serial_number}/state",
            "MQTT_PUBLISH_INTERVAL": "30",
            "MQTT_HOST": "mqtt.example.com",
            "MQTT_PORT": "8883",
            "MQTT_USERNAME": "mqtt-user",
            "MQTT_PASSWORD": "mqtt-password",
            "MQTT_TLS": "true",
            "MQTT_VALIDATE_CERT": "false",
            "MQTT_CLIENT_ID": "custom-client",
            "MQTT_CA_CERT_PATH": str(cert_file),
            "LOG_LEVEL": "debug",
        }
        with patch.dict(os.environ, env, clear=True):
            config = get_config()
            assert config.MQTT_TOPIC == "netgear-lte2mqtt/{model}/{serial_number}/state"
            assert config.MQTT_PUBLISH_INTERVAL == 30
            assert config.MQTT_HOST == "mqtt.example.com"
            assert config.MQTT_PORT == 8883
            assert config.MQTT_USERNAME == "mqtt-user"
            assert config.MQTT_PASSWORD == "mqtt-password"
            assert config.MQTT_TLS is True
            assert config.MQTT_VALIDATE_CERT is False
            assert config.MQTT_CLIENT_ID == "custom-client"
            assert config.MQTT_CA_CERT_PATH == str(cert_file)
            assert config.LOG_LEVEL == "DEBUG"

    @pytest.mark.parametrize(
        ("var", "value", "expected_error"),
        [
            ("MQTT_PORT", "not_an_integer", "must be an integer"),
            ("MQTT_CONNECTION_TIMEOUT", "abc", "must be an integer"),
            ("MQTT_PUBLISH_INTERVAL", "xyz", "must be an integer"),
            ("MQTT_MAX_RETRIES", "1.5", "must be an integer"),
            ("MODEM_HOST", "", "Invalid MODEM_HOST"),
            ("MODEM_HOST", "http://192.168.5.1", "without URL scheme"),
            ("MQTT_HOST", "", "Invalid MQTT_HOST"),
            ("MQTT_HOST", "mqtt host", "without URL scheme or spaces"),
            ("MODEM_PASSWORD", "", "non-empty string"),
            ("MODEM_PASSWORD", "   ", "non-empty string"),
            ("MQTT_PASSWORD", "secret_without_user", "MQTT_USERNAME must be set"),
            ("MQTT_PORT", "70000", "Must be between 1 and 65535"),
            ("MQTT_PORT", "0", "Must be between 1 and 65535"),
            ("MQTT_PUBLISH_INTERVAL", "0", "Must be at least 1"),
            ("MQTT_PUBLISH_INTERVAL", "-10", "Must be at least 1"),
            ("MQTT_CONNECTION_TIMEOUT", "2", "Must be at least 5"),
            ("MQTT_MAX_RETRIES", "-1", "Must be at least 0"),
        ],
    )
    def test_invalid_values_raise_config_error(
        self, base_env: dict[str, str], var: str, value: str, expected_error: str
    ) -> None:
        # Verify out-of-range integers, malformed hosts, and invalid credentials raise ConfigError
        env = {**base_env, var: value}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert expected_error in str(exc_info.value)

    @pytest.mark.parametrize(
        ("var", "value"),
        [
            ("MQTT_TLS", "not-a-bool"),
            ("MQTT_VALIDATE_CERT", "1"),
            ("MQTT_TLS", "yes"),
        ],
    )
    def test_invalid_boolean_raises_config_error(self, base_env: dict[str, str], var: str, value: str) -> None:
        # Verify non-boolean strings for boolean flags raise ConfigError
        env = {**base_env, var: value}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert "boolean" in str(exc_info.value).lower()

    def test_invalid_client_id_raises_config_error(self, base_env: dict[str, str]) -> None:
        # Verify whitespace-only client ID is rejected
        env = {**base_env, "MQTT_CLIENT_ID": "   "}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert "non-empty string" in str(exc_info.value)

    def test_mqtt_client_id_too_long(self, base_env: dict[str, str]) -> None:
        # Verify client ID exceeding MAX_CLIENT_ID_LENGTH is rejected
        env = {**base_env, "MQTT_CLIENT_ID": "a" * (MAX_CLIENT_ID_LENGTH + 1)}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert "too long" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("topic", "expected_error"),
        [
            ("", "Invalid MQTT topic"),
            ("home/topic with space/state", "whitespace"),
            ("home/+/status", "wildcards"),
            ("home/#/status", "wildcards"),
            ("netgear/{unknown}/state", "Unsupported placeholder"),
            ("netgear/{}/state", "Unsupported placeholder"),
            ("netgear/{model/state", "unbalanced braces"),
            ("netgear/model}/state", "unbalanced braces"),
        ],
    )
    def test_invalid_mqtt_topic(self, base_env: dict[str, str], topic: str, expected_error: str) -> None:
        # Verify topics with whitespace, wildcards, unsupported placeholders, or unbalanced braces fail
        env = {**base_env, "MQTT_TOPIC": topic}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert expected_error in str(exc_info.value)

    def test_missing_ca_cert_file_when_tls_enabled(self, base_env: dict[str, str]) -> None:
        # Verify nonexistent CA certificate file raises ConfigError and requires keyword-only mqtt_tls flag
        with pytest.raises(TypeError):
            _validate_ca_cert_path("/nonexistent/path/ca.crt", True)  # pyright: ignore[reportCallIssue]

        env = {
            **base_env,
            "MQTT_TLS": "true",
            "MQTT_CA_CERT_PATH": "/nonexistent/path/ca.crt",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert "MQTT_CA_CERT_PATH does not exist" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("raw_level", "expected_level"),
        [
            ("debug", "DEBUG"),
            ("Info", "INFO"),
            ("wArNiNg", "WARNING"),
            ("error", "ERROR"),
            ("CRITICAL", "CRITICAL"),
        ],
    )
    def test_log_level_is_case_insensitive(self, base_env: dict[str, str], raw_level: str, expected_level: str) -> None:
        # Verify LOG_LEVEL accepts any casing and normalizes to uppercase
        env = {**base_env, "LOG_LEVEL": raw_level}
        with patch.dict(os.environ, env, clear=True):
            config = get_config()
            assert config.LOG_LEVEL == expected_level

    @pytest.mark.parametrize("bad_level", ["", "VERBOSE", "TRACE"])
    def test_invalid_log_level_raises_config_error(self, base_env: dict[str, str], bad_level: str) -> None:
        # Verify unsupported log level names raise ConfigError
        env = {**base_env, "LOG_LEVEL": bad_level}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                get_config()
            assert "LOG_LEVEL" in str(exc_info.value)

    def test_sanitize_masks_passwords(self, base_env: dict[str, str]) -> None:
        # Verify non-empty passwords are masked while empty optional passwords remain empty
        env = {**base_env, "MQTT_USERNAME": "mqtt-user", "MQTT_PASSWORD": "secret-mqtt-password"}
        with patch.dict(os.environ, env, clear=True):
            config = get_config()
            sanitized = config.sanitize()
            assert sanitized["MODEM_PASSWORD"] == "******"
            assert sanitized["MQTT_PASSWORD"] == "******"
            assert sanitized["MODEM_HOST"] == base_env["MODEM_HOST"]

        with patch.dict(os.environ, base_env, clear=True):
            config_empty_mqtt_pw = get_config()
            assert config_empty_mqtt_pw.sanitize()["MQTT_PASSWORD"] == ""
