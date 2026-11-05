# AGENTS.md

## Architecture

Service-oriented daemon that polls a Netgear LTE modem via `eternalegypt` and publishes JSON status telemetry to MQTT.

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

- **Toolchain**: Python 3.14, `pipenv`, Ruff (format + lint), Pyright (type checking), Pytest, and Podman.
- **Execution**: Run as a module via `python -m netgear_lte2mqtt.main` with `PYTHONPATH=src`.
- **Test Layout**: Mirror `src/netgear_lte2mqtt/` under `tests/netgear_lte2mqtt/`, keep `__init__.py` in both
  `tests/` and `tests/netgear_lte2mqtt/` so `pytest` resolves test modules without shadowing `src/netgear_lte2mqtt/`,
  and define all `pytest` fixtures in `tests/conftest.py`.
- **Type Checking**: `eternalegypt` has incomplete type stubs; keep the `reportCallIssue` Pyright ignore comment on
  `Modem()` instantiation.
- **Container Networking**: Supports standard bridge networking (as in `deploy/docker-compose.yml`) or `--network host`
  when `MQTT_HOST=localhost`.
- **Local Container Testing**: `deploy/docker-compose.yml` is a self-contained consumer Compose example (`mosquitto` +
  `ghcr.io` image + inline minimal `environment`), while `make docker-start` runs an inline `eclipse-mosquitto`
  container and the local `$(BUILD_TAG)` image with `.env`.
- **Healthcheck Semantics**: `--healthcheck` indicates service readiness (`/tmp/healthcheck` is created once startup
  completes and removed on shutdown), not individual poll or MQTT publish outcomes.

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

- **Single Source of Truth**: Never hardcode release versions in `Makefile` or source files. `BUILD_VERSION` resolves
  dynamically from exact Git tags via `git describe --tags --exact-match`, falling back to `latest` when untagged.
- **Publishing**: `make publish` pushes both `:$(BUILD_VERSION)` and `:$(PUBLISH_TAG)` (default: `latest`) to
  `$(REGISTRY)` (default: `localhost`).
- **GitHub / GHCR**: Tagging a release (`git tag v0.0.1 && git push origin v0.0.1` or via the GitHub Releases UI)
  triggers `make publish REGISTRY=ghcr.io/obatiuk`, updating both the versioned tag and `:latest`.

## Environment Variables

Required:

- `MODEM_HOST`: Netgear modem IP or hostname
- `MODEM_PASSWORD`: Modem admin password
- `MQTT_HOST`: MQTT broker IP or hostname

Optional:

- `MQTT_TOPIC` (default: `netgear-lte2mqtt/state`, supports `{model}` and `{serial_number}` placeholders)
- `MQTT_PUBLISH_INTERVAL` (default: `60` seconds, min: `1`)
- `MQTT_PORT` (default: `1883`)
- `MQTT_CLIENT_ID` (default: `netgear-lte2mqtt`, max 64 chars)
- `MQTT_USERNAME` (default: empty string)
- `MQTT_PASSWORD` (default: empty string; requires `MQTT_USERNAME`)
- `MQTT_TLS` (`true`/`false`, default: `false`)
- `MQTT_VALIDATE_CERT` (`true`/`false`, default: `false`)
- `MQTT_CA_CERT_PATH` (default: empty string; uses system CAs when `MQTT_TLS=true`)
- `MQTT_CONNECTION_TIMEOUT` (default: `60` seconds, min: `5`)
- `MQTT_MAX_RETRIES` (default: `5`, use `0` for unlimited retries)
- `LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, case-insensitive; default: `INFO`)

## Coding & Documentation Conventions

- **Minimal Changes**: Do not refactor code unless necessary. Keep changes minimal, focused, and easy to review.
- **Preserve Existing Comments**: Never remove existing comments in source or test files unless explicitly required.
- **Concise, Human Docs**: Write short, direct documentation. Avoid verbose or AI-sounding filler.
- **No Magic Numbers**: Never use raw numeric literals in loops, retries, or timeouts; define named constants or
  configuration properties.
- **Ignore Files**: List only exact paths that exist in the project in `.gitignore` and `.dockerignore`; never add
  speculative or wildcard ignores.
- **No PII or Carrier Names**: Never include personal identifiable information (names, emails, local IPs, hostnames, or
  specific cellular carrier names) in repository files, excluding the GitHub handle (`obatiuk`).
- **Plain-Text Markdown Output**: Always provide `.md` files in unbroken 4-backtick plain-text blocks for one-click
  copying.
- **Markdown Formatting**: Wrap all `.md` lines at a maximum of 120 characters and only use square brackets for links,
  task checkboxes (`- [x]` / `- [ ]`), or GitHub callouts (`> [!NOTE]`).
- **Commit Messages**: Omit the first summary/subject line. Start directly with brief bullet points and end with
  `Co-authored-by: Gemini <noreply@google.com>`.
- **Maintain `AGENTS.md`**: Always record new project conventions, constraints, and user feedback in `AGENTS.md`.
