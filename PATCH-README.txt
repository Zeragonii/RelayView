RelayView Android v0.6.1 — Rotation + Immersive Fullscreen Patch

This is the PATCH package (not the entire repository).

Files changed:
- android/app/src/main/java/com/relayview/android/MainActivity.kt
  Preserves list visibility, mute, pause, fullscreen, search, favourites across rotation.
  Adds true immersive fullscreen, overlay exit control, Android Back handling.
- android/app/build.gradle.kts
  Updates local/fallback version to 0.6.1.
- pyproject.toml
  Updates project version to 0.6.1 (no 'v' prefix).
- relayview/__init__.py
  Matches the Python package version to 0.6.1.
- tests/test_android_ui_contract.py
  Adds static UI/version regression contract tests.
- RELEASE_NOTES-0.6.1.md
  Behaviour and device test checklist.

HOW TO APPLY
1. Back up any local changes (or commit them first).
2. Extract this ZIP at the ROOT of the RelayView repository, preserving paths.
3. If you've separately edited pyproject.toml or android/app/build.gradle.kts,
   merge the version bump instead of blindly overwriting those files.
4. Commit and push to main. Verify the debug Android build on Actions.
5. After validation, push the v0.6.1 tag to publish the signed APK.

Requires the already-installed GitHub Actions setup-android@v4 fix from 0.6.0.

BUILD VERIFICATION
- Python tests (including source-level UI regression checks): 77 passed, 2 skipped.
- Full Android Gradle build/device playback: NOT executed in this environment.

WARNING: A freshly generated GitHub debug APK may not have the same signing
certificate as your previously installed debug APK. Back up your M3U/layouts
before uninstalling anything, and use the consistently signed official release
channel for updates once set up.
