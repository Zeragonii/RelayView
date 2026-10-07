# RelayView

RelayView is a small, modern desktop viewer for M3U/M3U8 camera playlists. It is designed around Frigate/go2rtc-style restreams but works with ordinary VLC-compatible stream URLs too.

## Features

- Clean dark PySide6 interface
- M3U/M3U8 playlist parsing
- Searchable camera list
- Click-to-switch streams
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

## Windows releases

RelayView uses Velopack. Install `RelayView-Setup.exe` from the latest GitHub Release once; subsequent releases can be downloaded as delta updates from inside RelayView when available.

The packaged Windows build includes a trimmed VLC runtime, so a separate VLC installation is not required.

### Creating a release

Update the version in both `pyproject.toml` and `relayview/__init__.py`, commit it, then tag that commit:

```bash
git tag v0.1.1
git push origin v0.1.1
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
