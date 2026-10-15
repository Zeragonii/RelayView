# RelayView v0.6.2 — Android system-bar and cutout compatibility

## Fixed

- Corrected the Android 15+ edge-to-edge layout for devices such as the Pixel 10 Pro XL.
  RelayView's normal toolbar, sidebar and grid now remain inside the device's safe
  drawing area rather than sitting beneath the status bar, camera cutout or
  bottom navigation region. Handles landscape side insets as well.
- Immersive fullscreen continues to use the complete display with the system bars
  hidden; on exit, the normal safe-area padding returns automatically.
- Unified window inset configuration across earlier Android versions and newer
  enforced edge-to-edge devices. The dark UI uses light system-bar icons.
- Explicitly zeroed `Scaffold` content insets because safe drawing padding is now
  applied once around the full normal screen, including the custom app bar.

## Unchanged

Media3 playback, camera management, saved layouts, playback state across rotation,
playlist format, release signing and in-app updates are unchanged.

## Build and testing

Version updated to `0.6.2` in the Python package, `pyproject.toml`, and the
Android Gradle default. Publish with Git tag `v0.6.2`, using the same signing
keystore as v0.6.1 so the Android update installs over the existing version.

The Python regression suite and source contract tests can be run with
`python -m pytest -q`. GitHub Actions must compile the Android APK, followed
by a real-device validation on the Pixel 10 Pro XL and OnePlus 9 Pro, including
portrait/landscape, normal/fullscreen, and gesture/three-button navigation.
