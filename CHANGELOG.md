# Changelog

## dev

- Omit the zero-duration container healthcheck start period so container image builds succeed
- Mark the service healthy immediately at startup before external network connections and shorten the container
  healthcheck interval
- Extract release history into a dedicated changelog, split architecture reference docs from agent rules, add
  self-documenting build help sections, and enforce collection-type, exception-chaining, and keyword-only signature
  rules
- Run `CI` verification before container registry login on push events and prune project container images, builder
  layers, and build cache across `Podman` and `Docker` during cleanup

## v0.0.3

- Consolidate container build and deployment assets into a single deployment directory and remove the exported
  requirements file after container builds
- Disable `TLS` certificate chain verification when certificate validation is turned off
- Skip queuing `QoS 1` status publishes while the `MQTT` session is inactive
- Abort `MQTT` startup retries on shutdown signals before marking the service healthy, and disconnect the `MQTT`
  client before stopping the network loop so the `DISCONNECT` packet is flushed
- Downgrade routine modem session refresh logs before re-authentication to `DEBUG`
- Share the package cache directory between `pip` and `pipenv` in `GitHub Actions` to speed up dependency
  installation
- Use default container networking in standalone examples and unify configuration placeholders across templates and
  documentation
- Skip waiting for publish completion on failed `MQTT` publishes, eliminate real-time sleeps in unit tests, annotate
  test signatures, require keyword-only boolean flags, and anonymize sample serial numbers
- Publish development container images on main branch pushes, upgrade `GitHub Actions` to `Node 24` with `pip`
  caching, and suppress `CI` and container build warnings
- Add `CI` status, release tag, `Python` version, code style, and license badges to project documentation

## v0.0.2

- Separate `MQTT` broker connection timeout from the keepalive interval and make initial broker connections
  non-blocking
- Simplify project and container ignore rules and streamline project documentation

## v0.0.1

- Add `GitHub Actions` `CI` and container release workflow, Compose example, environment templates, and documentation
- Add unit test suite with `Ruff` linting, `Pyright` type checking, and `pip-audit` dependency auditing
- Add multi-stage rootless `Python 3.14` container build with built-in readiness healthcheck and `Git` tag versioning
- Minimize runtime memory footprint with slotted classes, pre-allocated `MQTT` properties, and stripped `pip` in the
  runtime image
- Log modem state transitions and connection recovery at `INFO` while suppressing repeated unreachable warnings
- Support optional `MQTT` username and password authentication and `TLS` 1.2/1.3 encryption
- Validate required and optional environment settings at startup and mask secrets in startup logs
- Add `HTTP` request timeouts for modem polling and capped exponential backoff for `MQTT` broker connections
- Re-authenticate automatically when the modem web session expires and survive modem reboots during startup
- Configure `MQTT` Last Will, `MQTT` v5 message expiry, and synchronous empty-payload publishing on disconnect
- Support and validate dynamic model and serial number placeholders in the `MQTT` topic
- Poll Netgear `LTE` modem telemetry via `eternalegypt` and publish retained `JSON` status to `MQTT`
