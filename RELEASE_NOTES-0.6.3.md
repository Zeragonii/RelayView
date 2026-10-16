# RelayView v0.6.3 — Windows zoom input reliability

## Fixed

- Windows mouse-wheel camera zoom now uses Qt logical cursor coordinates for native-window hit-testing instead of raw Windows mouse-hook pixels. This is important with HiDPI scaling and mixed-DPI monitors.
- Native low-level mouse hooks now queue zoom changes for the Qt event loop instead of running playback/IPC work inside the hook callback, reducing the chance Windows will silently disable a slow hook.
- Qt-delivered mouse wheel events on the video host are accepted as a fallback if the native hook is unavailable. The hook consumes native wheel input when active to avoid double zooming.
- Added deterministic regression tests for DPI-safe event targeting and deferred zoom dispatch.

## Unchanged

The underlying libmpv zoom properties, per-tile zoom bounds and middle-button pan maths are unchanged. The Android UI, Media3 playback, playlist formats, signing and updater are unchanged.

## Verification and diagnostics

The Python unit tests can run outside Windows. A real Windows installer and live RTSP feed are needed to confirm the behaviour of the low-level Windows hook.

If the zoom label changes from 1.25× but the image does not visibly zoom, the problem is beyond mouse event routing. Turn on Logging → DEBUG and inspect `%LOCALAPPDATA%\RelayView\logs\relayview.log` for `Set libmpv view`, `Worker view acknowledgement`, and `Worker rejected command=zoom`; inspect `player-workers.log` for native errors.

Use Git tag `v0.6.3` after the main-branch CI jobs pass.
