# RelayView

A small, clean desktop viewer for M3U camera playlists. RelayView was designed for Frigate/go2rtc restream endpoints, but it works with any stream URL that VLC can play.

![RelayView icon](assets/relayview.png)

## What it does

- Opens `.m3u` and `.m3u8` playlists.
- Shows all stream names in a clean searchable camera list.
- Click a camera to switch immediately.
- Previous/Next controls wrap around the playlist.
- Fullscreen video, pause/resume and mute.
- Keyboard shortcuts for fast camera switching.
- Remembers the last playlist, window size and selected camera.
- Drag an M3U file onto the window to load it.
- Uses libVLC for playback, so RTSP/H.264/H.265 support is mature and familiar.

## Windows: easiest installation

You do **not** need Python or a separate VLC installation when using the packaged build.

1. Open the repository's **Actions** tab.
2. Open the latest successful `Build RelayView` workflow.
3. Download the `RelayView-Windows-x64` artifact.
4. Extract the zip somewhere permanent.
5. Run `RelayView.exe`.

For tagged versions (`v0.1.0`, etc.), the same zip is automatically attached to the GitHub Release.

> Keep the files in the extracted folder together. `RelayView.exe` uses the bundled `vlc` directory beside it.

## Playlist format

Standard extended M3U works well:

```m3u
#EXTM3U
#EXTINF:-1 group-title="Outside",Front Door
rtsp://192.168.1.50:8554/front_door
#EXTINF:-1 group-title="Outside",Driveway
rtsp://192.168.1.50:8554/driveway
#EXTINF:-1 group-title="Inside",Hallway
rtsp://192.168.1.50:8554/hallway
```

Bare URL lists also work; RelayView derives a friendly name from the final URL path segment.

## Controls

| Action | Mouse/UI | Keyboard |
| --- | --- | --- |
| Previous camera | Previous | `←` |
| Next camera | Next | `→` |
| Pause/resume | Pause | `Space` |
| Mute/unmute | Mute | `M` |
| Fullscreen | Fullscreen / double-click video | `F` |
| Leave fullscreen | — | `Esc` |
| Open playlist | Menu / Open playlist | `Ctrl+O` |

## Running from source

### Windows

Install Python 3.12+ and VLC 3.x, then:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Linux / CachyOS

Install VLC and Python first. On Arch/CachyOS:

```bash
sudo pacman -S vlc python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

VLC's Linux video embedding currently uses an X11 window handle. Under a native Wayland session, run RelayView through XWayland if required.

## Building locally

The supported packaged Windows build is made by GitHub Actions. If you want to build it yourself:

```powershell
pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean --windowed --onedir --name RelayView --icon assets/relayview.ico --add-data "assets;assets" --collect-all PySide6 main.py
```

Copy your VLC installation directory into `dist\RelayView\vlc` afterwards.

## GitHub Actions

`.github/workflows/build.yml` runs tests, creates the Windows package, bundles VLC, and uploads `RelayView-Windows-x64.zip` as an Actions artifact.

Push a tag to create a Release automatically:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Roadmap ideas

RelayView intentionally starts simple. Good future additions include a 2x2 multi-camera grid, favourite cameras, snapshots, configurable network cache, go2rtc/Frigate API discovery, PTZ controls, and an optional always-on-top mini-view.

## License

RelayView source is MIT licensed. The packaged Windows build includes VLC/libVLC and its plugins, which retain their own VideoLAN/LGPL/GPL licensing terms.
