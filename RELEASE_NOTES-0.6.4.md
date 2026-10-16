# RelayView v0.6.4 — Single-camera wheel zoom

## Windows fixes

- Enables scroll-wheel zoom over the primary **Single** camera view using the same native Windows wheel hook as **Grid** view.
- Continues to route wheel input to only the visible video surface; no additional low-level mouse hook is installed.
- Uses the same 0.25× zoom steps and 1×–5× bounds as existing grid zoom.
- Enables middle-button pan while zoomed in on Single view through the existing polled input path.
- Provides a Qt wheel-event fallback for single view on systems where the native hook is blocked.
- Resets zoom/pan to 1× when switching cameras or returning from Grid to Single view.

## Android

No Android functionality changes. Android version metadata is bumped to 0.6.4 so the existing combined release workflow can publish a matching signed APK.

## Validation

Python regression tests cover the single-camera zoom adapter, wheel dispatch, active view routing, visibility hit-testing, camera zoom resets, and existing grid behaviour. Native Windows mouse/Qt behaviour still requires validation in a Windows build.

## Manual smoke checks

1. In **Single** view, scroll over the picture. The image should zoom in/out in 0.25× increments.
2. While zoomed, hold the middle mouse button and drag to pan the image.
3. Select another camera; it should appear at 1×.
4. Switch to **Grid** and scroll over two different tiles; zoom should still affect only the tile under the pointer.
5. Switch back to Single and verify wheel zoom works again.
6. Test with Windows display scaling at 125% or 150%, if available.
