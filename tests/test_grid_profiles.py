import pytest
from types import SimpleNamespace
from relayview.grid_profiles import validate_profile, resolve_assignments


def test_valid_layout():
    assert validate_profile({"rows": 2, "columns": 3, "urls": ["rtsp://one", ""]}) == (2, 3, ["rtsp://one", ""])


@pytest.mark.parametrize("profile", [
    None, [], {}, {"rows": 1, "columns": 65, "urls": []},
    {"rows": -1, "columns": 2, "urls": []},
    {"rows": 2, "columns": 2, "urls": ["a"] * 5},
    {"rows": 1, "columns": 1, "urls": [None]},
])
def test_invalid_layouts(profile):
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_missing_cameras_leave_empty_tiles():
    camera = SimpleNamespace(url="rtsp://one")
    assert resolve_assignments(["rtsp://one", "rtsp://missing", ""], 2, 2, [camera]) == [camera, None, None, None]


def test_explicitly_empty_layout():
    assert resolve_assignments([], 2, 2, [SimpleNamespace(url="a")]) == [None] * 4
