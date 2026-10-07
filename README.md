# RelayView

RelayView is a small, modern desktop viewer for M3U/M3U8 camera playlists. It is designed around Frigate/go2rtc-style restreams but works with ordinary VLC-compatible stream URLs too.

## Features

- Clean dark PySide6 interface
- M3U/M3U8 playlist parsing
- Searchable camera list
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

## Windows releases

RelayView uses Velopack. Install `RelayView-Setup.exe` from the latest GitHub Release once; subsequent releases can be downloaded as delta updates from inside RelayView when available.

The packaged Windows build includes a trimmed VLC runtime, so a separate VLC installation is not required.

### Creating a release

Update the version in both `pyproject.toml` and `relayview/__init__.py`, commit it, then tag that commit:

```bash
git tag v0.1.5
git push origin v0.1.5
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
