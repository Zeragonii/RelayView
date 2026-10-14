# RelayView Android — Implementation, Building & Publishing

**Status:** Android source integration / release candidate. The independent M3U Kotlin parser compiles, and the existing Python/Windows suite passes. Android Gradle and hardware smoke tests must run in GitHub Actions and on actual devices before production release. **No APK has been built or tested in this offline environment.**

This repository now contains the original Windows PySide6/libmpv RelayView and a new Kotlin/Jetpack Compose app in `android/`. **Android uses AndroidX Media3 ExoPlayer**, including the Media3 RTSP and HLS extensions, not VLC or mpv.

## Android features implemented in source

- Android phone, tablet, and Google/Android TV launcher entry points, dark responsive UI.
- File-picker import/export of RelayView `.m3u`/`.m3u8` camera playlists, preserving `group-title`, `tvg-id`, `tvg-name`, `relayview-favorite`, `relayview-notes` and unknown EXTINF attributes.
- Camera add/edit/delete, reorder, favourites, group filtering, search, notes.
- Select a grid tile, then tap a camera in the list to assign it. Swap tiles using the swap button on one tile followed by another tile. Saved layout presets and JSON import/export.
- Configurable grids: 1×1, 1×2, 2×2, 3×3, 4×4 (decoder count depends on device). Double-tap/fullscreen, pinch zoom (1×–5×), pan, mute/pause and TV remote-accessible controls.
- Per-feed ExoPlayer with forced RTSP/RTP over TCP, retry backoff and buffering timeout; releases decoders when views leave composition; pauses playback when app is backgrounded.
- Optional `relayview-substream` attribute in each M3U camera: lower-resolution H.264 stream used for grids, while fullscreen uses the main URL. Configure it in the Android camera editor or add it to an EXTINF line, for example `relayview-substream="rtsp://192.168.1.50:8554/front_low"`.
- Optional update availability check at startup; in-app download of tagged *signed* APKs; verify SHA-256 and package ID; hand off to the **standard Android installation confirmation screen**. Updates are not silent. The Android signature is ultimately validated by the OS.
- `REQUEST_INSTALL_PACKAGES` (sideload workflow only); Android asks the user to allow the RelayView app as an unknown-install source before the first self-update.

**Codec limitation:** AndroidX Media3's RTSP module supports a narrower set of formats than desktop mpv. Plan on H.264 RTSP from go2rtc and H.264 substreams for larger grids; H.265 RTSP cannot be assumed to work. HTTP/HLS playback uses Media3's default/HLS sources. Actual codec and multi-decoder support is hardware-dependent.

## Quick start: using GitHub Actions

1. Copy these files into your actual RelayView repository **preserving paths**, including `.github/workflows/build.yml`, `android/`, `scripts/generate_android_update_manifest.py`, and the Windows `relayview/main_window.py` changes. Do not copy the archive's contents over a different version of the Windows source without reviewing differences.
2. Commit and push to `main`. The existing **Build RelayView** workflow will run Python tests, the Windows installer pipeline, and Android's `testDebugUnitTest` / `assembleDebug` in separate jobs.
3. In the Actions run's artifacts, download **RelayView-Android-Debug-<version>** and extract `app-debug.apk` to install a test build. This APK is signed with a temporary **debug** certificate and is not a production update candidate. Different CI debug builds may have different certificates, requiring uninstall before installing the next debug version.
4. For production signing, generate one permanent Android keystore and configure GitHub secrets (below).
5. Increment the version in `pyproject.toml` (e.g., from `0.5.1` to `0.5.2`) and commit it. **Do not reuse an existing release tag.** Tag exactly the same version, e.g. `git tag v0.5.2` then `git push origin v0.5.2`.
6. On this tag the Windows job publishes the Velopack GitHub Release; the Android job builds a release APK; `publish_android` waits for **both jobs** and attaches `RelayView-Android-v0.5.2.apk` and `android-update.json` to that *same* release. Windows release assets are not overwritten.
7. Sideload the **release** APK on each Android device. Subsequently use RelayView > update icon > Check / Download / Install. For in-app checks, GitHub's `/releases/latest` must point to a publicly accessible published release with `android-update.json`.

### GitHub repository signing secrets

**Create and permanently back up your signing key:**

```bash
keytool -genkeypair -v -keystore relayview-release.jks -alias relayview \
  -keyalg RSA -keysize 3072 -validity 10000
```

Never commit `relayview-release.jks` or any passwords. Encode the keystore file into a **single-line** Base64 string:

```bash
# Linux/macOS:
base64 -w 0 relayview-release.jks
# Windows PowerShell:
[Convert]::ToBase64String([IO.File]::ReadAllBytes("relayview-release.jks"))
```

Add these *Actions repository secrets* under GitHub > Settings > Secrets and variables > Actions:

| Secret | Value |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64 of your permanent JKS file |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | `relayview` (or the alias you chose) |
| `ANDROID_KEY_PASSWORD` | Alias's private-key password |

The Android workflow **refuses to publish tag builds if any signing secret is missing**. If you lose the signing key, devices that already have the release app cannot receive normal in-place updates from a new key. Keep an encrypted offline backup.

**Repository Actions permissions:** Allow actions to create/update GitHub releases. The `windows` and `publish_android` jobs request `contents: write`. If organization policy restricts `GITHUB_TOKEN`, enable the required workflow release permission.

### Local Android build

Install Android Studio or Android Command Line Tools (Android SDK API 36, Build Tools) plus **JDK 17** and **Gradle 8.13**. This archive does not include Gradle's binary wrapper JAR; the workflow uses `gradle/actions/setup-gradle` to install the required Gradle release on the runner.

From repository root:

```bash
gradle -p android :app:testDebugUnitTest :app:assembleDebug \
  -PrelayviewVersion=0.5.1 \
  -PrelayviewRepo=OWNER/REPO
```

`android/app/build/outputs/apk/debug/app-debug.apk` is the resulting **debug** package.

For **local release** signing, set four environment variables before running `:app:assembleRelease`:

```bash
export RELAYVIEW_KEYSTORE="$PWD/relayview-release.jks"
export RELAYVIEW_KEYSTORE_PASSWORD='YOUR_KEYSTORE_PASSWORD'
export RELAYVIEW_KEY_ALIAS='relayview'
export RELAYVIEW_KEY_PASSWORD='YOUR_KEY_PASSWORD'
gradle -p android :app:assembleRelease \
  -PrelayviewVersion=0.5.1 -PrelayviewRepo=OWNER/REPO
```

The production package ID is `com.relayview.android`. Choose and **lock down** the final package ID **before the first public release**. Changing it later creates a different app and breaks in-place updates. `relayviewRepo` is embedded as an `owner/repo` string into the built APK; this lets the updater discover your own releases without hard-coded repository URLs in source control.

### Installing on a phone/tablet

You can copy `RelayView-Android-vX.Y.Z.apk` to the device and open it, approve installing apps from the file manager if asked, then launch RelayView. Import `sample.m3u` or a copy of your real M3U playlist using the folder icon; saved camera URLs are only accessible if the device can reach the go2rtc or Frigate host (same LAN or VPN).

### Installing on Google TV / Android TV

Install using a supported sideload method, e.g. from a laptop with Android Platform Tools:

```bash
adb connect DEVICE_IP:5555
adb install -r RelayView-Android-v0.5.2.apk
```

Enable network debugging / wireless ADB using your device's developer settings first. Some TV builds require pairing, a USB ADB connection, or TV-specific install permissions. The app exposes a `LEANBACK_LAUNCHER` category for TV home screens. Use D-pad to choose a camera, focus tiles, and operate Zoom/Fullscreen/Swap controls. Validate remote focus with the exact streaming device you own.

### In-app updater protocol

The workflow publishes `android-update.json` alongside the APK:

```json
{
  "version": "0.5.2",
  "versionCode": 5002,
  "packageName": "com.relayview.android",
  "apkUrl": "https://github.com/OWNER/REPO/releases/download/v0.5.2/RelayView-Android-v0.5.2.apk",
  "sha256": "<64 hex digits for the released APK>"
}
```

Clients GET `https://github.com/OWNER/REPO/releases/latest/download/android-update.json`. They accept update URLs only under `https://github.com/OWNER/REPO/releases/download/`, verify the checksum and package ID, then ask the Android system installer to install the APK. GitHub updates require internet; RTSP streams may work offline on the LAN. Update installation is *user-approved*, not background or silent, and may require a source-install permission on first use.

**Not designed for Google Play distribution.** The `REQUEST_INSTALL_PACKAGES` permission conflicts with Google Play's self-updating policy for ordinary apps. This is a sideload distribution design only. Android developer-verification requirements for sideloading may change by region and OS release; check current Android guidance before deploying widely.

### Known limitations / acceptance tests

- **Required:** GitHub CI completes the Android Gradle build and tests, APK signatures verify, physical Android hardware displays one H.264 RTSP stream and a 2×2 grid, Wi‑Fi disruptions reconnect, release APK updates successfully over the previous release without data loss.
- **Required:** Check Android TV remote focus, 4K display layouts, and device decoding capacity. A `4×4` grid is selectable but is *not* a promise that a device can decode 16 independent feeds.
- **Required:** Confirm zoom/pan works on real `TextureView`-backed playback surfaces; if OEM graphics drivers behave differently, adjust view transforms.
- No automatic substream discovery: set `relayview-substream` on each camera. Main streams are used if none is set.
- No Plex/NVR discovery, recording, PTZ, audio talkback, PiP, or background surveillance service in this version.
- The Windows app can now import/export the compatible named-layout JSON. Android imports Windows profiles up to **4×4**, skipping oversized profiles instead of truncating them. Playlist files use identical metadata format. Per-device live tile assignments are stored locally and are not continuously synchronised.
- Multi-stream decoding and true RTSP/H.265 playback parity with Windows mpv are **not** guaranteed by Media3.
- Camera credentials inside URL-based playlists are stored in **private app storage** (Android backup disabled); do not publish personal M3U files or include secrets in issue reports. HTTP cameras are supported by `usesCleartextTraffic`; prefer protected LAN/VPN and HTTPS where available.

## Layout of key files

```text
android/
  settings.gradle.kts           project repositories
  build.gradle.kts              Android and Kotlin plugin versions
  app/build.gradle.kts          versioning, signing and Media3 dependencies
  app/src/main/AndroidManifest.xml
  app/src/main/java/com/relayview/android/
    MainActivity.kt             Compose UX, camera grids, Media3 player
    M3u.kt                      Windows-compatible playlist codec
    Layouts.kt                  Windows-compatible layout JSON codec
    RelayViewModel.kt            camera/layout state and persistence
    Updates.kt                   HTTPS release lookup, checksum, installer
  app/src/test/.../M3uTest.kt  JVM parser tests
.github/workflows/build.yml     Windows + Android build/release pipeline
scripts/generate_android_update_manifest.py
relayview/main_window.py        Windows layout JSON import/export added
```

## Troubleshooting

- **H.265 RTSP fails:** select an H.264 camera profile or configure an H.264 go2rtc substream. Media3's RTSP module is not equivalent to desktop mpv.
- **Video stalls on VPN:** RTSP is forced to RTP/TCP; check the VPN's routes/firewall and camera restream host connectivity.
- **Update check unavailable:** your repository/build may not have `relayviewRepo` populated, or the latest *published* release lacks `android-update.json`, or the GitHub repository is private.
- **App not installed / cannot update:** test with the original release keystore; debug APKs and production APKs are signed differently. Also confirm `versionCode` increases.
- **APK on CI missing:** check the `android` job output. This offline archive intentionally does not contain a precompiled APK.
- **Signing secret issues:** check Base64 file encoding, passwords, and whether repository policies expose secrets to the protected tag workflow.
