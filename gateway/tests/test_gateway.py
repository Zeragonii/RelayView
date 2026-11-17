import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.app import Config, create_app, etag, validate_m3u


class Broker:
    def __init__(self):
        self.sent = []
        self.connected = True

    def send(self, topic, command):
        if not self.connected:
            return False
        self.sent.append((topic, command))
        return True

    def close(self):
        pass


@pytest.fixture
def gateway(tmp_path):
    broker = Broker()
    config = Config(
        token="test-" + "a" * 48,
        playlist=tmp_path / "master.m3u",
        mqtt_host="mqtt", mqtt_port=1883, mqtt_user="", mqtt_password="",
        mqtt_tls=False, topic_prefix="frigate", cameras=frozenset({"front", "driveway"}),
        stop_seconds=0.05,
    )
    with TestClient(create_app(config, broker)) as client:
        yield client, broker, config


def headers():
    return {"Authorization": "Bearer " + "test-" + "a" * 48}


def test_authentication_and_health(gateway):
    client, _, _ = gateway
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/playlist").status_code == 401
    assert client.get("/api/v1/playlist", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_playlist_write_requires_current_etag_and_persists(gateway):
    client, _, config = gateway
    first = client.get("/api/v1/playlist", headers=headers())
    assert first.status_code == 200
    assert first.text == "#EXTM3U\n"
    assert first.headers["etag"] == etag(b"#EXTM3U\n")
    contents = b'#EXTM3U\n#EXTINF:-1 relayview-ptz-camera="front",Front\nrtsp://example/front\n'
    assert client.put("/api/v1/playlist", headers=headers(), content=contents).status_code == 428
    good = client.put("/api/v1/playlist", headers={**headers(), "If-Match": first.headers["etag"]},
                      content=contents)
    assert good.status_code == 200
    assert config.playlist.read_bytes() == contents
    assert client.get("/api/v1/playlist", headers=headers()).content == contents
    assert client.put("/api/v1/playlist", headers={**headers(), "If-Match": first.headers["etag"]},
                      content=b"#EXTM3U\n").status_code == 412


def test_playlist_rejects_invalid_or_oversized_content(gateway):
    client, _, _ = gateway
    tag = client.get("/api/v1/playlist", headers=headers()).headers["etag"]
    for invalid in [b"invalid", b"#EXTM3U\nfile:///etc/passwd\n", b"#EXTM3U\n" + b"x" * 1_048_576]:
        assert client.put("/api/v1/playlist", content=invalid,
                          headers={**headers(), "If-Match": tag}).status_code in (400, 413)


def test_ptz_whitelist_commands_and_stop(gateway):
    client, broker, _ = gateway
    api = "/api/v1/ptz/front/command"
    response = client.post(api, headers=headers(), json={"command": "MOVE_LEFT"})
    assert response.status_code == 200
    assert broker.sent[-1] == ("frigate/front/ptz", "MOVE_LEFT")
    time.sleep(0.15)
    assert broker.sent[-1] == ("frigate/front/ptz", "STOP")
    assert client.post(api, headers=headers(), json={"command": "preset_Home"}).status_code == 200
    assert broker.sent[-1] == ("frigate/front/ptz", "preset_Home")
    assert client.post(api, headers=headers(), json={"command": "ZOOM_IN"}).status_code == 200
    assert client.post(api, headers=headers(), json={"command": "STOP"}).status_code == 200
    assert broker.sent[-1] == ("frigate/front/ptz", "STOP")


def test_ptz_rejects_unknown_cameras_or_commands(gateway):
    client, broker, _ = gateway
    assert client.post("/api/v1/ptz/notallowed/command", headers=headers(),
                       json={"command": "MOVE_UP"}).status_code == 404
    for command in ["MOVE_UP/evil", "RESET", "preset_../foo", "preset_", "MOVE_DIAGONAL"]:
        assert client.post("/api/v1/ptz/front/command", headers=headers(),
                           json={"command": command}).status_code == 400
    assert not broker.sent


def test_ptz_requires_available_mqtt(gateway):
    client, broker, _ = gateway
    broker.connected = False
    assert client.post("/api/v1/ptz/front/command", headers=headers(),
                       json={"command": "MOVE_UP"}).status_code == 503


def test_repeated_movement_extends_stop_deadline(gateway):
    client, broker, _ = gateway
    path = "/api/v1/ptz/driveway/command"
    assert client.post(path, headers=headers(), json={"command": "MOVE_RIGHT"}).status_code == 200
    time.sleep(0.025)
    assert client.post(path, headers=headers(), json={"command": "MOVE_RIGHT"}).status_code == 200
    time.sleep(0.025)
    assert broker.sent[-1][1] == "MOVE_RIGHT"
    time.sleep(0.075)
    assert broker.sent[-1][1] == "STOP"
