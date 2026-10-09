# RelayView native playback component

Windows packages include a pinned libmpv DLL sourced from the `shinchiro/mpv-winbuild-cmake`
2026-10-08 release. The DLL and bundled third-party dependencies have separate
copyright and license terms (including GPLv3 components) from RelayView's MIT-licensed
Python source code. Distributing the combined Windows installer may impose GPL
requirements. Refer to [mpv licensing](https://github.com/mpv-player/mpv/blob/master/Copyright)
and the [build project's sources](https://github.com/shinchiro/mpv-winbuild-cmake).

The download is SHA256-pinned in `scripts/prepare_mpv.ps1`. This notice is not a
substitute for complete license/source-offer compliance; review these obligations
before distributing a public installer. RelayView's repository retains its own
MIT `LICENSE` for the original source code.
