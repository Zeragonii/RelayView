"""Source contracts for Android rotation/fullscreen handling.

These are fast source-level regression checks. The GitHub Actions Gradle job
still compiles Android and a device test is needed to validate the UI.
"""
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "android/app/src/main/java/com/relayview/android/MainActivity.kt").read_text()


def test_rotation_sensitive_ui_state_is_saveable():
    for setting in ("fullscreen", "showList", "muted", "paused", "cameraFilter", "favouritesOnly"):
        pattern = rf"var\s+{setting}\s+by\s+rememberSaveable\s*\{{"
        assert re.search(pattern, MAIN), f"{setting} must survive Activity recreation"


def test_fullscreen_uses_immersive_mode_and_back_button():
    assert "controller.hide(WindowInsetsCompat.Type.systemBars())" in MAIN
    assert "controller.show(WindowInsetsCompat.Type.systemBars())" in MAIN
    assert "BackHandler(enabled = fullscreen != null) { fullscreen = null }" in MAIN
    assert 'contentDescription = "Exit fullscreen"' in MAIN
    assert "if (fullscreen != null) {" in MAIN
    assert "GridViewer(Modifier.fillMaxSize(), state, fullscreen, muted, paused," in MAIN


def test_camera_sidebar_filters_hoisted_out_of_orientation_branches():
    assert "onCameraFilter = { cameraFilter = it }" in MAIN
    assert "onFavouritesOnly = { favouritesOnly = it }" in MAIN
    assert MAIN.count("cameraFilter, onCameraFilter, favouritesOnly, onFavouritesOnly,") == 2


def test_release_version_matches_android_fallback_and_python_package():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f'orElse("{version}")' in (ROOT / "android/app/build.gradle.kts").read_text()
    assert f'__version__ = "{version}"' in (ROOT / "relayview/__init__.py").read_text()


def test_edge_to_edge_insets_safe_in_normal_mode_and_immersive_in_fullscreen():
    """Guard against Android 15+ overlap with status/navigation bars and cutouts."""
    assert "WindowCompat.setDecorFitsSystemWindows(window, false)" in MAIN
    assert "isAppearanceLightStatusBars = false" in MAIN
    assert "isAppearanceLightNavigationBars = false" in MAIN
    assert "if (fullscreen == null) Modifier.safeDrawingPadding() else Modifier" in MAIN
    assert re.search(r"contentWindowInsets\s*=\s*WindowInsets\(0,\s*0,\s*0,\s*0\)", MAIN)
    assert ".background(background)" in MAIN
