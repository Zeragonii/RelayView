import json
import pytest
from scripts.generate_android_update_manifest import manifest, version_code


def test_android_versions_are_monotonic():
    assert version_code("0.5.1") == 5001
    assert version_code("0.5.2") > version_code("0.5.1")
    assert version_code("0.6.0") > version_code("0.5.999")
    assert version_code("1.0.0") > version_code("0.999.999")


@pytest.mark.parametrize("bad", ["0.5", "v0.5.1", "0.1000.1", "0.5.-1", "x.y.z"])
def test_version_validation(bad):
    with pytest.raises(ValueError):
        version_code(bad)


def test_release_manifest(tmp_path):
    apk = tmp_path / "RelayView-Android-v0.5.1.apk"
    apk.write_bytes(b"apk sample bytes")
    data = manifest(apk, "testowner/relayview", "0.5.1")
    assert data["versionCode"] == 5001
    assert data["apkUrl"].endswith("/v0.5.1/RelayView-Android-v0.5.1.apk")
    assert len(data["sha256"]) == 64
    assert json.loads(json.dumps(data)) == data
