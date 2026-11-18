# AGENTS.md

Service-oriented daemon (`src/netgear_lte2mqtt/`) that polls a Netgear `LTE` modem via `eternalegypt` (`ModemClient`)
and publishes `JSON` status telemetry to `MQTT` v5 (`MqttClient`, orchestrated by `MonitorApp`).

## Project Rules & Quirks

- **Type Checking**: `eternalegypt` has incomplete type stubs; keep the `reportCallIssue` `Pyright` ignore comment on
  `Modem()` instantiation in [modem_client.py](src/netgear_lte2mqtt/modem_client.py).
- **Container Networking**: Standalone `docker run` uses default networking;
  [docker-compose.yml](deploy/docker-compose.yml) uses a `mqtt` bridge; `make docker-start` uses `--network host`.
- **Compose vs Local Testing**: Keep [docker-compose.yml](deploy/docker-compose.yml) as a self-contained consumer
  example (`ghcr.io` image + inline `environment`); use `make docker-start` for local `$(BUILD_TAG)` + `.env` testing.
- **Healthcheck Semantics**: `--healthcheck` checks daemon readiness (`/tmp/healthcheck` created after startup and
  removed on shutdown), not individual poll or `MQTT` publish outcomes.
- **PII Exception**: Only the GitHub handle `obatiuk` is permitted in repository files.

## Reference Map

- [architecture.md](docs/architecture.md): Read when modifying module responsibilities, startup or shutdown lifecycle,
  dynamic topic resolution, session recovery, or deployment layout.
- [README.md](README.md): Read when changing telemetry payload fields, `MQTT` behavior, or environment variables.
- [.env.full.example](deploy/.env.full.example) and [.env.minimal.example](deploy/.env.minimal.example): Read when
  adding, renaming, or changing default environment variables in [config.py](src/netgear_lte2mqtt/config.py).
- [CHANGELOG.md](CHANGELOG.md) and [TODO.md](docs/TODO.md): Read when recording completed work, tracking open tasks, or
  cutting a release.
