# AGENTS.md

## Architecture

Service-oriented daemon that polls a Netgear `LTE` modem via `eternalegypt` and publishes `JSON` status telemetry to
`MQTT`.

```text
├── docker/
│   └── Dockerfile             # Multi-stage Python 3.14 container build
├── src/
│   └── netgear_lte2mqtt/
│       ├── __init__.py
│       ├── main.py            # Bootstraps config, handles --healthcheck, registers signal handlers, starts MonitorApp
│       ├── app.py             # MonitorApp: Orchestrates polling loop, placeholders, transitions, and health state
│       ├── config.py          # Config: Environment variable parsing, strict validation, and secret sanitization
│       ├── mqtt_client.py     # MqttClient: MQTT v5 connectivity, Last Will, expiry, auth, retries, and JSON publish
│       └── modem_client.py    # ModemClient: Wrapper around eternalegypt with automatic session re-authentication
└── tests/
    ├── __init__.py
    ├── conftest.py            # Shared pytest fixtures and random string helpers
    └── netgear_lte2mqtt/      # Mirrors src/netgear_lte2mqtt/ module structure 1:1
        ├── __init__.py
        ├── test_app.py
        ├── test_config.py
        ├── test_main.py
        ├── test_modem_client.py
        └── test_mqtt_client.py
```

### Constraints & Quirks

- **Type Checking**: `eternalegypt` has incomplete type stubs; keep the `reportCallIssue` `Pyright` ignore comment on
  `Modem()` instantiation.
- **Container Networking**: Supports standard bridge networking (as in `deploy/docker-compose.yml`) or `--network host`
  when `MQTT_HOST=localhost`.
- **Local Container Testing**: `deploy/docker-compose.yml` is a self-contained consumer Compose example (`mosquitto` +
  `ghcr.io` image + inline minimal `environment`), while `make docker-start` runs an inline `eclipse-mosquitto`
  container and the local `$(BUILD_TAG)` image with `.env`.
- **Healthcheck Semantics**: `--healthcheck` indicates service readiness (`/tmp/healthcheck` is created once startup
  completes and removed on shutdown), not individual poll or `MQTT` publish outcomes.

## Key Commands

- **Setup environment**: `make setup` (creates `.venv/` and installs dependencies via `pipenv`)
- **Format code**: `make format` (runs `ruff format`)
- **Lint & typecheck**: `make lint` (runs `ruff check --fix` and `pyright`)
- **Audit dependencies**: `make check` (runs `pipenv audit`) and `make fix-audit` (runs `pip-audit --fix`)
- **Run unit tests**: `make test` (runs `pytest` with coverage report)
- **Full local verification**: `make build` (runs `format`, `lint`, `check`, and `test`)
- **Run locally**: `make run` (sources `.env` or `ENV_FILE` and runs the module)
- **Build container image**: `make docker-build` (or `make`, builds `$(PROJECT_NAME):$(BUILD_VERSION)` locally)
- **Publish container image**: `make publish REGISTRY=<registry>` (tags and pushes both `$(BUILD_VERSION)` and
  `$(PUBLISH_TAG)`)

## Release & Versioning Flow

- **GitHub / GHCR**: Pushing to `master`/`main` triggers `make publish` with `BUILD_VERSION=dev PUBLISH_TAG=dev`
  (updating `:dev`), while tagging a release (`git tag v0.0.1 && git push origin v0.0.1` or via the GitHub Releases UI)
  triggers `make publish REGISTRY=ghcr.io/obatiuk`, updating both `:$(BUILD_VERSION)` and `:latest`.

## Environment Variables

Required:

- `MODEM_HOST`: Netgear modem IP or hostname
- `MODEM_PASSWORD`: Modem admin password
- `MQTT_HOST`: `MQTT` broker IP or hostname

Optional:

- `MQTT_TOPIC` (default: `netgear-lte2mqtt/state`, supports `{model}` and `{serial_number}` placeholders)
- `MQTT_PUBLISH_INTERVAL` (default: `60` seconds, min: `1`)
- `MQTT_PORT` (default: `1883`)
- `MQTT_CLIENT_ID` (default: `netgear-lte2mqtt`, max 64 chars)
- `MQTT_USERNAME` (default: empty string)
- `MQTT_PASSWORD` (default: empty string; requires `MQTT_USERNAME`)
- `MQTT_TLS` (`true`/`false`, default: `false`)
- `MQTT_VALIDATE_CERT` (`true`/`false`, default: `false`)
- `MQTT_CA_CERT_PATH` (default: empty string; uses system `CA`s when `MQTT_TLS=true`)
- `MQTT_CONNECTION_TIMEOUT` (default: `60` seconds, min: `5`)
- `MQTT_MAX_RETRIES` (default: `5`, use `0` for unlimited retries)
- `LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, case-insensitive; default: `INFO`)

## Skills & Conventions

- **Global Skills (`~/.agents/skills/`)**: Load and follow the corresponding skill before working on:
  - `Python` code, tests, `Pipfile`, or `pyproject.toml`: `python-development`
  - Commit messages, diffs, or `git commit`: `git-commit`
  - Markdown files (`README.md`, `TODO.md`, `AGENTS.md`, `SKILL.md`): `markdown`
  - `Makefile`, `Dockerfile`, `GitHub Actions`, `.gitignore`, `.dockerignore`, or release tags: `release-and-ci`
- **PII Exception**: Exclude all PII and carrier names from repository files; only the GitHub handle `obatiuk` is
  permitted.
- **Maintain `AGENTS.md` & Skills**: Keep only project-specific architecture, quirks, and env vars in `AGENTS.md`;
  route generic workflow, language, or formatting rules to `~/.agents/skills/` after user approval.
