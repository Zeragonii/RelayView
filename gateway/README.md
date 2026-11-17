# RelayView Gateway — Frigate PTZ + Master Playlist

One small Docker service lets RelayView for Windows and Android use Frigate's
**existing ONVIF PTZ connection**, via MQTT, while keeping all video on the
existing go2rtc / RTSP connection. It also holds one master `.m3u` file.

Frigate's documented MQTT topic is `frigate/<camera_name>/ptz`. Commands are
`MOVE_UP/DOWN/LEFT/RIGHT`, `ZOOM_IN/OUT`, `STOP`, or `preset_<name>`.
The gateway **never** opens a second video stream.

## Deploy (existing MQTT broker recommended)

1. Point the gateway at the **same MQTT broker that Frigate uses**. If you use
   Home Assistant / Zigbee2MQTT you probably have Mosquitto already.
   Check Frigate's `mqtt:` settings and ensure MQTT is enabled; PTZ in Frigate's
   web UI alone does not guarantee MQTT is configured.
2. Copy `gateway/.env.example` to `gateway/.env` **on your server only**, fill
   in `MQTT_HOST`, credentials, `FRIGATE_PTZ_CAMERAS` and a newly generated
   `RELAYVIEW_API_TOKEN`. NEVER commit this file or your real camera M3U.
   Camera names are Frigate config IDs (e.g. `front_door`), not stream titles.
3. From repository root run:
   ```sh
   docker compose --env-file gateway/.env -f gateway/docker-compose.yml up -d --build
   ```
   This starts the API on **127.0.0.1:8098** and persists the master playlist
   in the Docker volume `relayview-data`.
4. Securely expose it to your phone and Windows clients with **Nginx Proxy
   Manager + HTTPS** on your trusted network or VPN. Join the container and NPM
   to an appropriate persistent Docker network, and proxy to
   `http://relayview-gateway:8080`. Do not expose the raw HTTP port to the
   internet. Both the playlist and PTZ API require a bearer token.
5. Configure the gateway HTTPS URL and API token on each RelayView device.
   Use **Pull** to replace its local playlist or **Push** to replace the master
   when desired. Edits are local until pushed—there is no surprise overwrite.
   Pulling doesn't touch saved per-device grid layouts.

### Optional new Mosquitto broker

Only deploy a second broker if you don't already have one:

```sh
# Run from gateway/ on the server; supply passwords interactively.
docker run --rm -it -v "$PWD:/work" eclipse-mosquitto:2 \
  mosquitto_passwd -c /work/passwordfile frigate
docker run --rm -it -v "$PWD:/work" eclipse-mosquitto:2 \
  mosquitto_passwd /work/passwordfile relayview
docker compose -f gateway/mosquitto.compose.yml up -d
```

Configure **Frigate and the RelayView gateway** to use the new broker host and
corresponding credentials; add broker ACLs if this broker is shared. This example
uses a password-protected MQTT listener, not anonymous MQTT. Do not expose MQTT
port 1883 outside your LAN/VPN. Use an existing MQTT broker if possible.

## Pairing a camera with Frigate PTZ

In Windows and Android camera editors, fill in **Frigate PTZ camera ID** using
the camera key from Frigate's `cameras:` YAML. RelayView preserves it in the
M3U EXTINF attribute `relayview-ptz-camera`:

```m3u
#EXTM3U
#EXTINF:-1 group-title="Outdoor" relayview-ptz-camera="front_door",Front Door
rtsp://192.168.1.10:8554/front_door
```

The ID must be in `FRIGATE_PTZ_CAMERAS` to send PTZ commands.
Only the *camera control* goes through the gateway; **the video URL does not
change**.

## API specification

All protected requests: `Authorization: Bearer <RELAYVIEW_API_TOKEN>`.

- `GET /api/v1/playlist` — master M3U and `ETag`.
- `PUT /api/v1/playlist` — UTF-8 M3U (up to 1 MiB), requires exact
  `If-Match: "<etag>"` from GET. Returns HTTP 412 if another device wrote
  a different version. Writes are atomic with persistent storage.
- `GET /api/v1/ptz/cameras` — configured Frigate camera IDs.
- `POST /api/v1/ptz/{camera}/command`, JSON `{"command":"MOVE_LEFT"}`
  — sends MQTT on Frigate's control topic.
- `GET /api/v1/health` — non-sensitive health response.

**PTZ safety:** A movement command automatically sends STOP after 0.9 seconds.
Clients repeat the movement command every ~250 ms while a button is held and
send STOP immediately on release. If phone connectivity vanishes, the watchdog
still stops motion. The watchdog runs only in one Uvicorn process; do not scale
this container to multiple workers.

**Security:** The same administrator-grade token can pull/write playlists and
steer cameras. Give it only to trusted RelayView devices. The master playlist
may contain embedded camera credentials: use TLS, private networking, and
protected backups. Rotate the token if any device is lost. MQTT auth and PTZ
allowlisting prevent arbitrary MQTT topic publishing. No API credentials are
added to video URLs or committed to source control.

## Tests

```sh
pip install -r gateway/requirements.txt pytest httpx
python -m pytest -q gateway/tests
```
