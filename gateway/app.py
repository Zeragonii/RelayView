"""Authenticated camera PTZ + central M3U API. No camera video is handled here."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

CAMERA_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PRESET_RE = re.compile(r"^preset_[A-Za-z0-9_-]{1,64}$")
CONTINUOUS = frozenset({"MOVE_UP", "MOVE_DOWN", "MOVE_LEFT", "MOVE_RIGHT",
                        "ZOOM_IN", "ZOOM_OUT"})
COMMANDS = CONTINUOUS | {"STOP"}
MAX_PLAYLIST = 1_048_576


@dataclass(frozen=True)
class Config:
    token: str
    playlist: Path
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str
    mqtt_password: str
    mqtt_tls: bool
    topic_prefix: str
    cameras: frozenset[str]
    stop_seconds: float = 0.9

    @staticmethod
    def from_environment() -> "Config":
        cams = frozenset(x.strip() for x in os.getenv("FRIGATE_PTZ_CAMERAS", "").split(",") if x.strip())
        prefix = os.getenv("MQTT_TOPIC_PREFIX", "frigate").strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_/-]{1,80}", prefix) or ".." in prefix:
            raise ValueError("Invalid MQTT_TOPIC_PREFIX")
        if not all(CAMERA_RE.fullmatch(c) for c in cams):
            raise ValueError("FRIGATE_PTZ_CAMERAS must contain simple Frigate camera IDs")
        seconds = float(os.getenv("PTZ_STOP_SECONDS", "0.9"))
        if not 0.3 <= seconds <= 2:
            raise ValueError("PTZ_STOP_SECONDS must be between 0.3 and 2 seconds")
        token = os.getenv("RELAYVIEW_API_TOKEN", "")
        if len(token) < 32 or token.startswith("REPLACE_"):
            raise ValueError("Set RELAYVIEW_API_TOKEN to 32+ unpredictable characters")
        return Config(
            token=token,
            playlist=Path(os.getenv("PLAYLIST_PATH", "/data/master.m3u")),
            mqtt_host=os.getenv("MQTT_HOST", "mqtt"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_user=os.getenv("MQTT_USERNAME", ""),
            mqtt_password=os.getenv("MQTT_PASSWORD", ""),
            mqtt_tls=os.getenv("MQTT_TLS", "false").lower() in ("true", "1", "yes"),
            topic_prefix=prefix,
            cameras=cams,
            stop_seconds=seconds,
        )


class Publisher(Protocol):
    def send(self, topic: str, command: str) -> bool: ...
    def close(self) -> None: ...


class MqttPublisher:
    def __init__(self, config: Config):
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="relayview-gateway")
        if config.mqtt_user:
            self.client.username_pw_set(config.mqtt_user, config.mqtt_password)
        if config.mqtt_tls:
            self.client.tls_set()
        self.client.reconnect_delay_set(min_delay=1, max_delay=20)
        self.client.connect_async(config.mqtt_host, config.mqtt_port, keepalive=30)
        self.client.loop_start()

    def send(self, topic: str, command: str) -> bool:
        import paho.mqtt.client as mqtt

        if not self.client.is_connected():
            return False
        result = self.client.publish(topic, payload=command, qos=0, retain=False)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def etag(content: bytes) -> str:
    return '"' + hashlib.sha256(content).hexdigest() + '"'


def validate_m3u(content: bytes) -> None:
    if len(content) > MAX_PLAYLIST:
        raise HTTPException(413, "Playlist exceeds 1 MiB")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Playlist must be UTF-8") from None
    lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U":
        raise HTTPException(400, "Playlist must start with #EXTM3U")
    for line in lines[1:]:
        if not line.startswith("#") and not line.lower().startswith(("rtsp://", "rtspt://", "http://", "https://")):
            raise HTTPException(400, "Playlist includes unsupported stream URL")
    if "\x00" in decoded:
        raise HTTPException(400, "Playlist cannot contain NUL bytes")


class PtController:
    def __init__(self, config: Config, publisher: Publisher):
        self.config = config
        self.publisher = publisher
        self._stop_tasks: dict[str, asyncio.Task] = {}

    def _publish(self, camera: str, command: str) -> None:
        topic = f"{self.config.topic_prefix}/{camera}/ptz"
        if not self.publisher.send(topic, command):
            raise HTTPException(503, "MQTT broker disconnected")

    async def command(self, camera: str, command: str) -> None:
        if camera not in self.config.cameras or not CAMERA_RE.fullmatch(camera):
            raise HTTPException(404, "PTZ camera is not configured")
        if command not in COMMANDS and not PRESET_RE.fullmatch(command):
            raise HTTPException(400, "Unsupported PTZ command")
        old = self._stop_tasks.pop(camera, None)
        if old is not None:
            old.cancel()
        self._publish(camera, command)
        if command in CONTINUOUS:
            self._stop_tasks[camera] = asyncio.create_task(self._auto_stop(camera))

    async def _auto_stop(self, camera: str) -> None:
        try:
            await asyncio.sleep(self.config.stop_seconds)
            # Never send MOVE indefinitely when clients disconnect.
            self._publish(camera, "STOP")
        except asyncio.CancelledError:
            return
        except HTTPException:
            return  # Broker down: Frigate will not receive further commands.
        finally:
            if self._stop_tasks.get(camera) is asyncio.current_task():
                self._stop_tasks.pop(camera, None)

    async def shutdown(self) -> None:
        for camera, task in list(self._stop_tasks.items()):
            task.cancel()
            try:
                self._publish(camera, "STOP")
            except HTTPException:
                pass
        self._stop_tasks.clear()


def create_app(config: Config | None = None, publisher: Publisher | None = None) -> FastAPI:
    # Lazy environment resolution allows importing this module in test runners.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = config if config is not None else Config.from_environment()
        own_publisher = publisher is None
        broker = publisher if publisher is not None else MqttPublisher(cfg)
        app.state.config = cfg
        app.state.controller = PtController(cfg, broker)
        app.state.lock = asyncio.Lock()
        try:
            yield
        finally:
            await app.state.controller.shutdown()
            if own_publisher:
                broker.close()

    application = FastAPI(title="RelayView Gateway", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)

    def authenticated(request: Request, authorization: str | None = Header(default=None)) -> None:
        expected = request.app.state.config.token
        provided = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(401, "Invalid API token", headers={"WWW-Authenticate": "Bearer"})

    def playlist_bytes(request: Request) -> bytes:
        path: Path = request.app.state.config.playlist
        return path.read_bytes() if path.exists() else b"#EXTM3U\n"

    @application.get("/api/v1/health")
    async def health() -> dict:
        return {"ok": True, "service": "relayview-gateway"}

    @application.get("/api/v1/playlist", dependencies=[Depends(authenticated)])
    async def get_playlist(request: Request):
        content = playlist_bytes(request)
        return PlainTextResponse(content.decode("utf-8-sig"),
                                 media_type="audio/x-mpegurl", headers={"ETag": etag(content),
                                 "Cache-Control": "no-store"})

    @application.put("/api/v1/playlist", dependencies=[Depends(authenticated)])
    async def put_playlist(request: Request, if_match: str | None = Header(default=None)):
        if if_match is None:
            raise HTTPException(428, "If-Match required (fetch current playlist first)")
        content = await request.body()
        validate_m3u(content)
        async with request.app.state.lock:
            existing = playlist_bytes(request)
            if not hmac.compare_digest(if_match, etag(existing)):
                raise HTTPException(412, "Master playlist changed; pull and review before pushing")
            path: Path = request.app.state.config.playlist
            path.parent.mkdir(parents=True, exist_ok=True)
            tempname = None
            try:
                with tempfile.NamedTemporaryFile(mode="wb", prefix=".master-", dir=path.parent, delete=False) as fp:
                    tempname = fp.name
                    os.chmod(tempname, 0o600)
                    fp.write(content)
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(tempname, path)
            finally:
                if tempname and os.path.exists(tempname):
                    os.unlink(tempname)
        return {"saved": True, "etag": etag(content)}

    @application.get("/api/v1/ptz/cameras", dependencies=[Depends(authenticated)])
    async def ptz_cameras(request: Request):
        return {"cameras": sorted(request.app.state.config.cameras)}

    @application.post("/api/v1/ptz/{camera}/command", dependencies=[Depends(authenticated)])
    async def ptz_command(camera: str, request: Request):
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("command"), str):
            raise HTTPException(400, "Expected JSON object with command")
        await request.app.state.controller.command(camera, payload["command"])
        return {"accepted": True}

    return application


app = create_app()
