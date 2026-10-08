### v0.4.3 — fix unclickable zoom controls

- Correct Qt footer mouse-event transparency that prevented the + and - buttons from receiving clicks.
- Add logs for UI zoom input and backend dispatch.
- Native VLC video surfaces may still intercept wheel events on Windows; footer buttons provide the dependable interaction path.
- No change to player process isolation or grid swapping.

### v0.4.2 — digital zoom compatibility fix

- Corrected crop geometry coordinates for offset crops in libVLC 3.x.
- Added zoom request and worker acknowledgement logging in the main RelayView log.
- Added one-time logging for unavailable video dimensions and VLC errors.
- Serialized worker zoom operations to avoid overlapping crop commands.
- Removed two misplaced backend methods that referenced nonexistent attributes.

**Known limitation:** VLC 3.x video output implementations can interpret crop geometry differently. This fix is based on documented VLC 3.x crop behaviour; it needs testing with the installed Windows runtime. `player-workers.log` remains available for worker-side messages.

### v0.4.1 — per-tile digital zoom

- Each camera grid tile has `+` / `−` zoom controls in its footer (1×–5× in 0.25× steps).
- Mouse wheel over a Qt-managed tile area zooms. Some Windows/libVLC video child windows intercept wheel events; the footer controls are always available.
- Right-click a tile for Reset zoom and stepwise pan directions; middle-drag pans when Qt receives the event.
- Zoom is stored per tile while the tile/session exists, carries with tile swaps, and is restored after a VLC worker reconnects. Zoom resets on reassignment or app restart.
- Uses libVLC 3.x `video_set_crop_geometry` inside existing isolated workers; no second decoder or stream connection.
- **Windows validation needed:** VLC 3.x video output implementations vary in whether arbitrary crop offsets are respected. Verify zoom and panning on your RTSP cameras before deploying broadly.

# RelayView

### v0.4.0 — smarter camera grids

- **Saved layouts:** use the main menu → **Saved camera layouts** to save, load, or delete named camera grids; assignments use stream URLs and unknown cameras appear as empty tiles. Existing last-used grid persistence is retained.
- **Swap without reconnecting:** dragging a populated tile to a different position moves its entire QWidget and native video host along with the running VLC process rather than destroying both playback workers.
- **Resource protection:** grids are limited to 64 tiles; the grid dialog prevents exceeding the limit and legacy saved dimensions are clamped to 2×2.
- **Fewer redundant restarts:** unchanged grid configurations, repeated assignments and existing supervised feeds avoid unnecessary playback restarts.
- **CI behaviour unchanged:** the existing single optimised GitHub Actions workflow continues to build and publish RelayView.

**Note:** Windows Qt/libVLC HWND behaviour should be tested with drag swaps of active 2×2 and 4×4 streams before publishing an automatic update. This version does not yet implement separate low-resolution substream mapping or decoder-aware load balancing; those require camera-specific source configuration.


### v0.3.1 — playback stall detection, diagnostics & update restart

- Playback workers report displayed-video-frame counters when exposed by libVLC; the supervisor retries if reported frames remain unchanged for more than 20 seconds while playing. Unsupported stats do not trigger false positives.
- Copied diagnostics now include sanitised process state, active worker PID, retry count, last exit code and frame-progress age.
- The downloaded-update confirmation now hands off to Velopack's external updater (`wait_exit_then_apply_updates`) for install-and-restart after the GUI shuts down, instead of requiring a manual Start-menu launch. Only supported in installed Velopack builds; must be validated on Windows.

### v0.3.0 — playback supervision (source release)

- **Bidirectional child-worker protocol:** JSON-lines on stdin/stdout. Workers send `ready`, `state`, `heartbeat`, `fatal` and `command_error` events. stdout has a dedicated reader thread, and Qt callbacks execute on the existing UI watchdog timer.
- **Playback status:** VLC's `Playing`, `Paused`, `Buffering`, and `Opening` states appear in single-view status and on each grid tile.
- **Automatic recovery:** unexpected worker exit, VLC `Error` or a worker becoming unresponsive schedules a fresh isolated worker. Retries back off from 1 second up to 30 seconds. Explicit stop/release disables recovery.
- **Generation filtering:** messages left over from terminated workers cannot change the status of a replacement process.
- **Native isolation preserved:** the GUI never loads libVLC; shutdown/teardown still occurs by terminating separate workers.
- **Regression tests** include state reporting, worker exits, ignored stale protocol events, error backoff and intentional stop.

**Important limitations:** the heartbeat measures whether the worker's VLC state polling responds; it does not verify that actual video frames are advancing. Some streams can remain reported `Playing` despite a frozen picture. The worker status thread invokes VLC state polling; this needs a Windows RTSP endurance test. There is no compiled Windows installer in this source package. Test single view and 2×2 / 4×4 layouts against actual RTSP streams before publishing an automatic update.

### v0.2.3 — playback lifecycle maintenance

- Worker termination and OS-process reaping no longer wait on the GUI thread.
- A lightweight Qt timer detects unexpected playback-worker exits.
- Playback commands no longer implicitly create workers after an explicit stop.
- Playlist and logging hardening, with lifecycle regression tests.

### v0.2.2 — playback isolation
- Runs every VLC player in an isolated RelayView child process.
- Grid/single transitions terminate workers instead of calling native `libvlc_media_player_stop()`.
- Stream changes replace the worker process, avoiding fragile RTSP teardown/reuse.
- App/update shutdown can forcibly terminate playback workers without taking down the GUI.
- Adds `player-workers.log` for isolated playback diagnostics.


> v0.1.9 grid-stability hotfix: Windows libVLC video hosts now receive the required native window styles, duplicate HWND attachment is prevented, and native crash diagnostics are written under `%LOCALAPPDATA%\RelayView\logs`.

RelayView is a small, modern desktop viewer for M3U/M3U8 camera playlists. It is designed around Frigate/go2rtc-style restreams but works with ordinary VLC-compatible stream URLs too.

## Features

- Clean dark PySide6 interface
- M3U/M3U8 playlist parsing
- Searchable camera list with favourites and notes
- Built-in playlist editor for renaming, reordering and stream metadata
- Click-to-switch streams
- Arbitrary camera grids (1×2, 2×2, 6×2, and beyond)
- Click a grid tile then choose a camera to assign it
- Drag populated grid tiles onto each other to rearrange/swap feeds
- Grid size and camera assignments persist across launches
- Previous/Next navigation with wraparound
- Pause, mute and fullscreen controls
- Drag-and-drop playlists
- Remembers the last playlist, stream and window geometry
- Embedded libVLC playback
- Windows installer and delta updates via Velopack/GitHub Releases

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Left / Right | Previous / next camera |
| Space | Pause / resume |
| M | Mute / unmute |
| F | Fullscreen |
| Esc | Exit fullscreen |
| Ctrl+O | Open playlist |
| Tab | Show / hide camera list |

## GitHub Actions build optimisation (CI update; app remains v0.3.1)

The **same** GitHub Actions workflow continues to run tests, build the Windows executable, package a Velopack installer and publish tag releases. There is no second build mode to manage.

- Python downloads are cached against `requirements-dev.txt`.
- The trimmed VLC 3.0.23 runtime is cached; Chocolatey and trimming run only when the cache is absent. Change the VLC version in both the cache key and installation command when upgrading VLC.
- PyInstaller's Windows binary cache is retained between workflow runs, and forced `--clean` was removed. A fresh GitHub-hosted runner still rebuilds the application; the cache improves binary processing but is **not** a persistent incremental build directory.
- Velopack delta packages use `BestSpeed` rather than `BestSize` (potentially larger update downloads in exchange for faster packaging).
- Tests have read-only repository permissions; release publishing retains the required write permission.

For the first run after this workflow change, both Windows caches will be cold. Cache entries can also be evicted by GitHub. The release trigger, version/tag validation, updater feed, and installer artifact remain unchanged.

## Windows releases

RelayView uses Velopack. Install `RelayView-Setup.exe` from the latest GitHub Release once; subsequent releases can be downloaded as delta updates from inside RelayView when available.

The packaged Windows build includes a trimmed VLC runtime, so a separate VLC installation is not required.

### Creating a release

Update the version in both `pyproject.toml` and `relayview/__init__.py`, commit it, then tag that commit:

```bash
git tag v0.1.8
git push origin v0.1.8
```

GitHub Actions will test the project, build the Windows application, create Velopack installer/update packages, generate a delta against the previous Velopack release when possible, and publish the GitHub Release.

> v0.1.1 is the first Velopack release, so it is necessarily a full install. Delta updates begin with the next release built from the Velopack release chain.

## Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py
```

When running directly from source, the update source is intentionally unset; update checking is enabled in packaged GitHub builds.

## Tests

```bash
pytest -q
```

## License

MIT. VLC/libVLC and Qt/PySide6 retain their respective upstream licenses.




## v0.1.8

- Reworked update installation for reliability. RelayView no longer asks Velopack to replace the live application while Qt/libVLC are still running.
- After a download finishes, **Install now** cleanly closes RelayView. Launch it once more and Velopack applies the pending update before the GUI starts.
- This intentionally trades automatic restart for a safer update handoff and avoids the native crash seen in earlier releases.

## v0.1.7

### Grid stability hotfix

- Fixed duplicate/deferred VLC attachment races when opening or resizing grids.
- Grid streams now start only after Qt has created stable native video windows.
- Grid startup is staggered slightly to avoid opening many RTSP decoders simultaneously.
- Discarded grid VLC players are explicitly released before their Qt widgets are destroyed.
- Stale deferred callbacks are invalidated when the grid is rebuilt.


- Added a built-in M3U playlist editor.
- Rename streams without manually editing the playlist file.
- Drag and drop streams to change their playlist order.
- Edit stream group, URL, favourite status and notes.
- Favourites are shown with a star in the camera sidebar.
- Notes are searchable and shown in camera tooltips.
- RelayView metadata is stored as compatible custom `#EXTINF` attributes.
- Unknown existing `#EXTINF` attributes are preserved when saving.
- Playlist saves use atomic file replacement to reduce the risk of a partially written M3U.

## v0.1.5

- Added configurable multi-camera grid view with independent row/column sizing (up to 32×32).
- Existing feeds are preserved when resizing a grid; newly added cells are populated from unused playlist cameras when available.
- Click any tile to make it active, then click a camera in the sidebar to assign or replace that tile.
- Drag a populated tile onto another tile to swap their positions.
- Grid dimensions and assignments are persisted by stream URL across restarts.
- Empty tiles do not create VLC players until a stream is assigned.
- Single-camera and grid modes can be switched from the always-visible top controls or the menu.

## v0.1.3

- Fixed the in-app updater crashing with `cannot import name 'Sources' from 'velopack'`.
- Uses Velopack's supported Python `UpdateManager(REPOSITORY_URL)` API, which auto-detects GitHub release feeds.
- This is a one-time manual installer update for users on v0.1.1/v0.1.2 because the updater in those versions cannot repair itself.

## v0.1.2

- Added an always-available **Cameras** button in the player header so the camera list can always be restored after hiding it.
- Added a real `Tab` shortcut for toggling the camera list.
- Fullscreen now remembers whether the camera list was visible before entering fullscreen.
- Added a persistent 0–100 volume slider next to the mute control.
- Updated Velopack to 1.2.161 and explicitly package Windows releases as `win-x64`.
- Reduced the normal GitHub Actions artifact to the setup executable; full/delta packages remain on GitHub Releases for the updater.

## v0.2.0 — Diagnostics & granular logging

RelayView 0.2.0 adds a persistent rotating logging system aimed at diagnosing native Qt/libVLC grid crashes and update failures.

- Default log level: **ERROR**
- Runtime levels: **ERROR / WARNING / INFO / DEBUG**
- Menu: **Logging → Open log folder**
- Menu: **Logging → Copy diagnostic summary**
- Main log: `%LOCALAPPDATA%\RelayView\logs\relayview.log` on Windows
- Rotation: 5 MB per file, 5 backups
- Native crash traces remain alongside the main log as `crash-*.log`
- Debug logging traces grid lifecycle, HWND preparation, VLC player attach/play/release, updater checks/downloads, UI transitions and shutdown.
- Credentials and common secret query parameters are redacted from stream URLs before they are written to logs.

For reproducing a grid crash, set **Logging → Debug**, reproduce the crash, then send `relayview.log` plus the newest `crash-*.log` from the log folder.

## v0.2.2 — VLC lifecycle hardening

RelayView 0.2.1 focuses on the native libVLC lifecycle shared by grid transitions and application/update shutdown.

- Detaches libVLC from its Qt/native video window before stopping playback.
- Logs detach, native stop, media clear, player release, and libVLC instance release as distinct lifecycle steps.
- Tears down the single-view player before changing grid widgets during single → grid transitions.
- Fully releases grid players before switching back to single view, then reattaches the primary player to its video host.
- Uses one idempotent VLC backend shutdown path for normal close and update-close handoff.
- Invalidates pending grid startup callbacks when grid playback is stopped/released.
- Adds lifecycle ordering tests to prevent regressions.

For troubleshooting, set Logging → Debug before reproducing a grid or update issue. The last lifecycle message before a native process failure should now identify the exact libVLC operation involved.

## Playback isolation (v0.2.2)

RelayView now hosts each libVLC media player in a separate child process. The main Qt GUI no longer loads libVLC directly. Closing, switching, or rebuilding a stream terminates the corresponding worker process instead of calling `libvlc_media_player_stop()`, isolating native VLC RTSP teardown failures from the application and updater. The packaged `RelayView.exe` doubles as the hidden playback worker, so there is no second executable to install.


### v0.4.4 — Windows native mouse controls

- Mouse-wheel zoom and middle-button drag-to-pan over camera images, including VLC-owned native child windows, using a scoped Windows low-level mouse hook.
- Only processes input within an assigned, visible camera video rectangle while RelayView is foreground.
- The existing +/− buttons, drag-to-swap and crop-based zoom are unchanged.
- The Windows hook is removed at application shutdown; if installation fails, the footer controls continue to work.
