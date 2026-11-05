# netgear-lte2mqtt

Small service that polls a Netgear LTE modem and publishes its status to MQTT.

## Why It Exists

My home network uses a Netgear LTE modem for automatic failover when wired internet drops. Because "unlimited"
cellular plans still have strict data caps, I need my automated `restic` backups (from my
[.dotfiles](https://github.com/obatiuk/dotfiles)) to pause when running on cellular backup.

Home Assistant has a Netgear LTE integration, but my full backup script shuts down Home Assistant before taking
snapshots. This service runs standalone next to Mosquitto so backup scripts can check MQTT directly to see if wired
internet is active.

Supported models (via [eternalegypt](https://github.com/amelchio/eternalegypt)):

- `LB1120`
- `LB1121`
- `LB2120`
- `Nighthawk M1 (MR1100)`
- `Nighthawk M2 (MR2100)`

## Quick Start

By default, the service connects to port `1883` on `MQTT_HOST` and publishes to `netgear-lte2mqtt/state` every `60`
seconds.

1. **Get your modem credentials**: Check the sticker on the bottom of your modem for its IP address (default is
   `192.168.5.1`, reachable in both Router and Bridge mode) and the admin web password.
2. **Create a `.env` file** (see [deploy/.env.minimal.example](deploy/.env.minimal.example)):

```ini
MODEM_HOST=192.168.5.1
MODEM_PASSWORD=your_admin_password
MQTT_HOST=localhost
```

3. **Run the container** (or see [deploy/docker-compose.yml](deploy/docker-compose.yml) for a Compose setup):

```bash
docker run -d \
  --name netgear-lte2mqtt \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  ghcr.io/obatiuk/netgear-lte2mqtt:latest
```

Every `60` seconds, the service publishes a retained JSON payload to `netgear-lte2mqtt/state`:

```json
{
  "model": "LB1120",
  "serial_number": "4631730N01234",
  "wire_connected": true,
  "mobile_connected": false,
  "upstream": "Wired",
  "connection_text": "Connected",
  "connection_type": "IPv4",
  "current_nw_service_type": "LTE",
  "current_ps_service_type": "LTE",
  "register_network_display": "Carrier",
  "roaming": false,
  "radio_quality": 85,
  "rx_level": -92,
  "tx_level": 0,
  "current_band": "LTE B4",
  "cell_id": "1234567",
  "usage": 45219840
}
```

Key telemetry fields:

- `wire_connected` / `mobile_connected`: Booleans indicating active WAN and LTE data bearers
- `upstream`: Active WAN path (`Wired`, `Mobile`, or `LTE` depending on model and failover state)
- `radio_quality`: Signal quality percentage (`0` to `100`)
- `rx_level` / `tx_level`: RSRP receive and transmit power in `dBm`
- `usage`: Cellular data used in the current billing cycle in `bytes`

If the modem becomes unreachable, or if the service stops or crashes (via synchronous shutdown publish, MQTT Last Will,
and MQTT v5 message expiry), it publishes `{}` so consumers never act on stale status data.

### Checking Connection Status from a Shell Script

Use `mosquitto_sub` and `jq -e` to check whether wired internet is active. This check fails safely if the network is on
LTE backup, the modem is unreachable (`{}`), the service is stopped, or the MQTT broker is down:

```bash
if mosquitto_sub -h localhost -t netgear-lte2mqtt/state -C 1 -W 5 2>/dev/null \
  | jq -e '.wire_connected == true' >/dev/null 2>&1; then
  echo "Wired internet active, starting backup..."
else
  echo "On cellular backup or status unavailable, skipping backup."
fi
```

## Advanced Configuration

See [deploy/.env.full.example](deploy/.env.full.example) for a complete template with all optional settings:

- `MQTT_TOPIC`: MQTT topic to publish status, supports `{model}` and `{serial_number}` placeholders (default:
  `netgear-lte2mqtt/state`)
- `MQTT_PUBLISH_INTERVAL`: Seconds between polls, minimum `1` (default: `60`)
- `MQTT_PORT`: Broker port (default: `1883`)
- `MQTT_CLIENT_ID`: Client identifier, max 64 chars (default: `netgear-lte2mqtt`)
- `MQTT_USERNAME`: Broker username (default: empty)
- `MQTT_PASSWORD`: Broker password, requires `MQTT_USERNAME` (default: empty)
- `MQTT_CONNECTION_TIMEOUT`: Broker connection timeout in seconds, minimum `5` (default: `60`)
- `MQTT_MAX_RETRIES`: Startup connection retries, `0` for unlimited (default: `5`)
- `MQTT_TLS`: Enable TLS (`true`/`false`, default: `false`)
- `MQTT_VALIDATE_CERT`: Verify broker TLS certificate (`true`/`false`, default: `false`)
- `MQTT_CA_CERT_PATH`: Path to custom CA certificate file (default: empty, uses system CAs)
- `LOG_LEVEL`: Logging verbosity, case-insensitive (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default: `INFO`)

> [!NOTE]
> To monitor multiple modems, run one container per modem with a unique `MODEM_HOST`, `MQTT_CLIENT_ID`, and
> `MQTT_TOPIC`. For example:
> - Dynamic placeholders: `MQTT_TOPIC=netgear-lte2mqtt/{model}/state` or `netgear-lte2mqtt/{serial_number}/state`
> - Separate static paths: `MQTT_TOPIC=netgear-lte2mqtt/primary/state` and `netgear-lte2mqtt/secondary/state`

## Acknowledgments

Thanks to Anders Melchiorsen ([@amelchio](https://github.com/amelchio)) for creating and maintaining the
[eternalegypt](https://github.com/amelchio/eternalegypt) library that powers communication with the Netgear modem.

## License

[MIT](LICENSE)
