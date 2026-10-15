# RelayView v0.6.1 — Android UI fixes

## Fixed

- **Rotation:** Hiding or showing the camera list, mute/unmute, pause/play,
  fullscreen selection, camera search text and favourites-only filtering now
  survive Activity recreation (including device rotation).
- **True fullscreen:** The selected camera now occupies the viewer with the
  camera sidebar and RelayView toolbar hidden, plus immersive Android system
  bars. In fullscreen the grid is 1×1; leaving restores the configured grid
  and the original list visibility.
- **Exit fullscreen:** Use the top-right exit button, the fullscreen/exit
  button in the camera tile, double tap on the camera, or Android Back.
- **Version alignment:** Windows Python package and Android Gradle fallback
  version are both 0.6.1, matching `pyproject.toml`.

## Notes

- This preserves *UI controls* across rotation. Android may recreate the
  activity on orientation changes, which can reconnect live video streams.
  Seamless decoder continuity during rotation is not part of this patch.
- Settings are not permanently saved between explicit app launches; the
  existing saved camera grid and playlist data remain persisted separately.
- In multi-camera grids, optional substreams are still preferred; fullscreen
  continues to use the main camera URL if one is configured.
- Android APK needs a successful CI build and real-device verification.

## Validate on a phone

1. Start a 2×2 grid, unmute and hide the sidebar, rotate portrait→landscape→portrait.
   Confirm the sidebar stays hidden and audio remains unmuted.
2. Show the sidebar, enter a search, enable favourites-only and rotate.
   Confirm filtering and text remain intact.
3. Tap the fullscreen icon on a populated tile. Confirm only that camera fills
   the content, the sidebar/toolbar disappear, and status/navigation bars are hidden.
4. Rotate while fullscreen. Confirm fullscreen stays active and audio remains unmuted.
5. Exit via top-right icon; repeat with Android Back and double-tap. Confirm
   the previous grid, list setting and audio state return unchanged.
6. Repeat with pause enabled, and verify the paused state survives rotation.
7. Test on an Android TV device with its remote if available.

## Publish

Set `version = "0.6.1"` in `pyproject.toml` (included in this patch), push to
main, check the Android debug build under Actions, then create/push tag
`v0.6.1` for signed release publishing. A debug-signed APK will not install
in place over an APK signed with a different certificate.
