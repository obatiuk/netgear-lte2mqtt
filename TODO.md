# TODO

## Backlog

- [ ] Client certificate authentication (mTLS) for MQTT
- [ ] Rate-limited retries for failed runtime MQTT publishes
- [ ] Config reload on `SIGHUP` without container restart

## Done

- [x] Rename project and package to `netgear-lte2mqtt` (`ModemClient`, `MqttClient`)
- [x] Publish full modem status (including `model` and `serial_number`) as JSON via `eternalegypt`
- [x] Support and strictly validate `{model}` and `{serial_number}` placeholders in `MQTT_TOPIC`
- [x] Configure MQTT Last Will, MQTT v5 `MessageExpiryInterval`, and synchronous `{}` publish on disconnect
- [x] Re-login automatically when the modem session expires and survive modem reboots during startup
- [x] Add HTTP timeout for modem requests and capped exponential backoff for MQTT connections
- [x] Require `MODEM_HOST`, `MODEM_PASSWORD`, and `MQTT_HOST`, validate all settings, and mask passwords in logs
- [x] Support optional MQTT username/password authentication and TLS 1.2/1.3 (`PROTOCOL_TLS_CLIENT`)
- [x] Minimize memory footprint with `__slots__`, pre-allocated MQTT properties, and stripped `pip` in container runtime
- [x] Multi-stage rootless Python 3.14 container build with built-in `--healthcheck` and Git tag versioning
- [x] Unit tests (99% coverage), expanded Ruff rule set, Pyright type checking, and strict `pip-audit`
