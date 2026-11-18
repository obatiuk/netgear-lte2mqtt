# Architecture

Read when: modifying module responsibilities, startup or shutdown lifecycle, dynamic topic resolution, session recovery,
or deployment layout.

## Repository Layout

```text
├── deploy/
│   ├── .env.full.example      # Complete environment variable template
│   ├── .env.minimal.example   # Minimal required environment variable template
│   ├── Dockerfile             # Multi-stage rootless Python 3.14 container build
│   └── docker-compose.yml     # Self-contained consumer Compose example (ghcr.io image + Mosquitto)
├── docs/
│   ├── TODO.md                # Open tasks and backlog
│   └── architecture.md        # Architecture, layout, and lifecycle reference
├── src/netgear_lte2mqtt/
│   ├── main.py                # CLI --healthcheck gate, config bootstrap, signal handlers
│   ├── app.py                 # MonitorApp: polling loop, topic placeholders, state logging, readiness file
│   ├── config.py              # Config: strict env parsing, bounds/placeholder validation, secret masking
│   ├── modem_client.py        # ModemClient: eternalegypt wrapper with session-expiry re-authentication
│   └── mqtt_client.py         # MqttClient: MQTT v5 connection backoff, TLS/auth, Last Will, JSON publish
└── tests/
    ├── conftest.py            # Shared pytest fixtures and randomized string helpers
    └── netgear_lte2mqtt/      # 1:1 unit test mirror of src/netgear_lte2mqtt/
```

## Runtime Data Flow & Lifecycle

```text
main.py ──→ get_config() ──→ MonitorApp.run()
  ├── dynamic MQTT_TOPIC: ModemClient.login/get_status ──→ MqttClient.set_topic ──→ connect
  ├── static MQTT_TOPIC:  MqttClient.connect ──→ ModemClient.login (non-fatal on failure)
  ├── touch /tmp/healthcheck
  ├── poll loop: ModemClient.get_status() ──→ MqttClient.publish_status() (QoS 1, retain)
  └── finally: unlink /tmp/healthcheck ──→ publish "{}" (wait) ──→ disconnect ──→ loop_stop
```

- **Startup & Topic Placeholders**: When `MQTT_TOPIC` contains `{model}` or `{serial_number}`,
  [app.py](../src/netgear_lte2mqtt/app.py) queries the modem (up to `3` attempts) and updates the `MQTT` Last Will
  topic before connecting to the broker, reusing that initial payload for the first publish. Static topics connect to
  `MQTT` first and tolerate an unreachable modem at startup by publishing `{}` until recovery.
- **Session Recovery**: `eternalegypt` returns `None` fields without raising when the modem web session expires;
  [modem_client.py](../src/netgear_lte2mqtt/modem_client.py) detects `wire_connected is None`, logs at `DEBUG`,
  re-authenticates once, and retries the poll inside the same cycle.
- **Stale-State Protection**: Consumers never read stale telemetry across failures:
  1. Unreachable modem polls publish retained `{}` (first failure logged at `WARNING`, consecutive failures at `DEBUG`).
  2. Graceful `SIGINT`/`SIGTERM` shutdowns synchronously publish retained `{}` before flushing `DISCONNECT`.
  3. Broker-side `MQTT` Last Will publishes retained `{}` on unexpected disconnects, and `MQTT` v5
     `MessageExpiryInterval` (`3x` `MQTT_PUBLISH_INTERVAL`) expires retained messages if both daemon and Last Will fail.
  4. While the `MQTT` session is inactive, [mqtt_client.py](../src/netgear_lte2mqtt/mqtt_client.py) skips `QoS 1`
     publishes to avoid unbounded offline queue growth.

For telemetry `JSON` fields and environment variables, see [README.md](../README.md) and
[.env.full.example](../deploy/.env.full.example).
