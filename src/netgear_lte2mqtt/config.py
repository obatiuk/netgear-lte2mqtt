import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default configuration values
DEFAULT_MQTT_TOPIC = "netgear-lte2mqtt/state"
DEFAULT_MQTT_PORT = "1883"
DEFAULT_MQTT_CLIENT_ID = "netgear-lte2mqtt"
DEFAULT_MQTT_CONNECTION_TIMEOUT = "60"
DEFAULT_MQTT_MAX_RETRIES = "5"
DEFAULT_MQTT_PUBLISH_INTERVAL = "60"
DEFAULT_LOG_LEVEL = "INFO"

# Validation bounds
MAX_CLIENT_ID_LENGTH = 64
MIN_PORT = 1
MAX_PORT = 65535
MIN_PUBLISH_INTERVAL = 1
MIN_CONNECTION_TIMEOUT = 5
MIN_MAX_RETRIES = 0

# Allowed enumerations and secret masking
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ALLOWED_TOPIC_PLACEHOLDERS = ("model", "serial_number")
SENSITIVE_FIELDS = frozenset({"MODEM_PASSWORD", "MQTT_PASSWORD"})
MASKED_SECRET = "******"

_PLACEHOLDER_PATTERN = re.compile(r"\{([^{}]*)\}")


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable application configuration parsed from environment variables."""

    MODEM_HOST: str
    MODEM_PASSWORD: str
    MQTT_TOPIC: str
    MQTT_HOST: str
    MQTT_PORT: int
    MQTT_CLIENT_ID: str
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    MQTT_TLS: bool
    MQTT_VALIDATE_CERT: bool
    MQTT_CA_CERT_PATH: str
    MQTT_CONNECTION_TIMEOUT: int
    MQTT_MAX_RETRIES: int
    MQTT_PUBLISH_INTERVAL: int
    LOG_LEVEL: str

    def sanitize(self) -> dict[str, Any]:
        """Returns a copy of config with sensitive fields masked."""
        return {
            key: (MASKED_SECRET if getattr(self, key) else "") if key in SENSITIVE_FIELDS else getattr(self, key)
            for key in self.__slots__
        }


def _validate_host(host: str, field_name: str = "host") -> str:
    """Validates that the host string is a non-empty hostname or IP without a URL scheme."""
    if not isinstance(host, str) or not host.strip():
        raise ConfigError(f"Invalid {field_name}: '{host}'")
    cleaned = host.strip()
    if "://" in cleaned or any(ch.isspace() for ch in cleaned):
        raise ConfigError(f"Invalid {field_name}: '{host}'. Must be a hostname or IP without URL scheme or spaces.")
    return cleaned


def _validate_password(password: str) -> str:
    """Validates that the modem password is a non-empty string."""
    if not isinstance(password, str) or not password.strip():
        raise ConfigError("MODEM_PASSWORD must be a non-empty string.")
    return password


def _validate_mqtt_topic(topic: str) -> str:
    """Validates the MQTT topic and any {model} or {serial_number} placeholders."""
    if not isinstance(topic, str) or not topic.strip():
        raise ConfigError(f"Invalid MQTT topic: '{topic}'")
    cleaned = topic.strip()
    if any(ch.isspace() for ch in cleaned) or "\x00" in cleaned:
        raise ConfigError(f"MQTT topic must not contain whitespace or null characters: '{cleaned}'")
    if "+" in cleaned or "#" in cleaned:
        raise ConfigError(f"MQTT topic must not contain wildcards: '{cleaned}'")

    # Validate any {placeholder} segments
    placeholders = _PLACEHOLDER_PATTERN.findall(cleaned)
    for name in placeholders:
        if name not in ALLOWED_TOPIC_PLACEHOLDERS:
            allowed = ", ".join(f"{{{p}}}" for p in ALLOWED_TOPIC_PLACEHOLDERS)
            raise ConfigError(f"Unsupported placeholder '{{{name}}}' in MQTT_TOPIC. Allowed: {allowed}")

    # Check for unbalanced braces after stripping valid placeholders
    stripped = _PLACEHOLDER_PATTERN.sub("", cleaned)
    if "{" in stripped or "}" in stripped:
        raise ConfigError(f"MQTT topic contains unbalanced braces: '{cleaned}'")

    return cleaned


def _validate_mqtt_client_id(client_id: str) -> str:
    """Validates that the MQTT client ID is non-empty and within length limits."""
    if not isinstance(client_id, str) or not client_id.strip():
        raise ConfigError("MQTT_CLIENT_ID must be a non-empty string")
    cleaned = client_id.strip()
    if len(cleaned) > MAX_CLIENT_ID_LENGTH:
        raise ConfigError(f"MQTT_CLIENT_ID too long ({len(cleaned)} chars). Max {MAX_CLIENT_ID_LENGTH} allowed.")
    return cleaned


def _validate_ca_cert_path(ca_cert_path: str, mqtt_tls: bool) -> str:
    """Validates that the custom CA certificate path points to an existing file when TLS is enabled."""
    cleaned = ca_cert_path.strip()
    if mqtt_tls and cleaned and not Path(cleaned).is_file():
        raise ConfigError(f"MQTT_CA_CERT_PATH does not exist or is not a file: '{cleaned}'")
    return cleaned


def _validate_log_level(level: str) -> str:
    """Validates and normalizes the logging level name."""
    if not isinstance(level, str) or not level.strip():
        raise ConfigError("LOG_LEVEL must be a non-empty string.")
    cleaned = level.strip().upper()
    if cleaned not in VALID_LOG_LEVELS:
        allowed = ", ".join(VALID_LOG_LEVELS)
        raise ConfigError(f"Invalid LOG_LEVEL: '{level}'. Must be one of: {allowed}")
    return cleaned


def _parse_int(var_name: str, default: str, min_val: int, max_val: int | None = None) -> int:
    """Parses an integer environment variable and enforces minimum and optional maximum bounds."""
    raw = os.environ.get(var_name, default).strip()
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"Environment variable '{var_name}' must be an integer.") from None

    if max_val is not None and not (min_val <= value <= max_val):
        raise ConfigError(f"Invalid {var_name}: {value}. Must be between {min_val} and {max_val}.")
    if value < min_val:
        raise ConfigError(f"Invalid {var_name}: {value}. Must be at least {min_val}.")
    return value


def _parse_bool(s: str, error_msg: str) -> bool:
    """Parses a strict 'true' or 'false' boolean string."""
    s_lower = s.strip().lower()
    if s_lower == "true":
        return True
    if s_lower == "false":
        return False
    raise ConfigError(error_msg)


def get_config() -> Config:
    """Reads configuration from environment variables and returns a validated Config object."""
    required_vars = (
        "MODEM_HOST",
        "MODEM_PASSWORD",
        "MQTT_HOST",
    )

    for var in required_vars:
        if var not in os.environ:
            raise ConfigError(f"Required environment variable '{var}' not set.")

    mqtt_username = os.environ.get("MQTT_USERNAME", "").strip()
    mqtt_password = os.environ.get("MQTT_PASSWORD", "")
    if mqtt_password and not mqtt_username:
        raise ConfigError("MQTT_USERNAME must be set when MQTT_PASSWORD is provided.")

    mqtt_tls = _parse_bool(os.environ.get("MQTT_TLS", "false"), "MQTT_TLS must be boolean ('true' or 'false').")
    mqtt_validate_cert = _parse_bool(
        os.environ.get("MQTT_VALIDATE_CERT", "false"), "MQTT_VALIDATE_CERT must be boolean ('true' or 'false')."
    )
    mqtt_ca_cert_path = _validate_ca_cert_path(os.environ.get("MQTT_CA_CERT_PATH", ""), mqtt_tls)

    return Config(
        MODEM_HOST=_validate_host(os.environ["MODEM_HOST"], "MODEM_HOST"),
        MODEM_PASSWORD=_validate_password(os.environ["MODEM_PASSWORD"]),
        MQTT_TOPIC=_validate_mqtt_topic(os.environ.get("MQTT_TOPIC", DEFAULT_MQTT_TOPIC)),
        MQTT_HOST=_validate_host(os.environ["MQTT_HOST"], "MQTT_HOST"),
        MQTT_PORT=_parse_int("MQTT_PORT", DEFAULT_MQTT_PORT, MIN_PORT, MAX_PORT),
        MQTT_CLIENT_ID=_validate_mqtt_client_id(os.environ.get("MQTT_CLIENT_ID", DEFAULT_MQTT_CLIENT_ID)),
        MQTT_USERNAME=mqtt_username,
        MQTT_PASSWORD=mqtt_password,
        MQTT_TLS=mqtt_tls,
        MQTT_VALIDATE_CERT=mqtt_validate_cert,
        MQTT_CA_CERT_PATH=mqtt_ca_cert_path,
        MQTT_CONNECTION_TIMEOUT=_parse_int(
            "MQTT_CONNECTION_TIMEOUT", DEFAULT_MQTT_CONNECTION_TIMEOUT, MIN_CONNECTION_TIMEOUT
        ),
        MQTT_MAX_RETRIES=_parse_int("MQTT_MAX_RETRIES", DEFAULT_MQTT_MAX_RETRIES, MIN_MAX_RETRIES),
        MQTT_PUBLISH_INTERVAL=_parse_int("MQTT_PUBLISH_INTERVAL", DEFAULT_MQTT_PUBLISH_INTERVAL, MIN_PUBLISH_INTERVAL),
        LOG_LEVEL=_validate_log_level(os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)),
    )
