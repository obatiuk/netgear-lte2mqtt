# TODO

## Open

None.

## Done

### dev

- [x] Share the `pip` cache directory with `pipenv` in `GitHub Actions` to speed up dependency installation
- [x] Use default container networking and explicit configuration placeholders in documentation and templates
- [x] Skip waiting for `MQTT` publish completion on failed publishes, eliminate real-time sleeps in unit tests,
  annotate all test signatures, require keyword-only boolean modifier flags, and anonymize sample serial numbers
- [x] Upgrade `GitHub Actions` to `Node 24`, enable `pip` caching, publish `:dev` images on `master` pushes, and
  suppress `CI` and container build warnings
- [x] Add `CI` status, release tag, `Python` version, code style, and license badges to project documentation

### v0.0.2

- [x] Separate MQTT socket `connect_timeout` from `MQTT_KEEPALIVE_SECONDS` and run `connect()` via `asyncio.to_thread`
- [x] Simplify `.gitignore` and `.dockerignore` and trim generic Python conventions from `AGENTS.md`

### v0.0.1

- [x] Add GitHub Actions CI/GHCR release workflow, `deploy/docker-compose.yml`, `.env` templates, and docs
- [x] Unit tests (99% coverage), expanded Ruff rule set, Pyright type checking, and strict `pip-audit`
- [x] Multi-stage rootless Python 3.14 container build with built-in `--healthcheck` and Git tag versioning
- [x] Minimize memory footprint with `__slots__`, pre-allocated MQTT properties, and stripped `pip` in container runtime
- [x] Log modem state transitions and connection recovery at `INFO` while suppressing repeated unreachable warnings
- [x] Support optional MQTT username/password authentication and TLS 1.2/1.3 (`PROTOCOL_TLS_CLIENT`)
- [x] Require `MODEM_HOST`, `MODEM_PASSWORD`, and `MQTT_HOST`, validate all settings and `LOG_LEVEL`, and mask passwords
- [x] Add HTTP timeout for modem requests and capped exponential backoff for MQTT connections
- [x] Re-login automatically when the modem session expires and survive modem reboots during startup
- [x] Configure MQTT Last Will, MQTT v5 `MessageExpiryInterval`, and synchronous `{}` publish on disconnect
- [x] Support and strictly validate `{model}` and `{serial_number}` placeholders in `MQTT_TOPIC`
- [x] Publish full modem status (including `model` and `serial_number`) as JSON via `eternalegypt`
- [x] Rename project and package to `netgear-lte2mqtt` (`ModemClient`, `MqttClient`)
