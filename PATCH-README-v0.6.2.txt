RelayView v0.6.2 — Pixel 10 Pro XL system bar / cutout fix

Patch contains only the files changed since the supplied v0.6.1 source.

INSTALL
  1. Back up/commit your current work.
  2. Extract this ZIP directly into the ROOT of your RelayView Git repository.
     Preserve folder paths and overwrite the listed files.
  3. Inspect your changes, run tests and push:
       python -m pytest -q
       git add android/app/src/main/java/com/relayview/android/MainActivity.kt android/app/build.gradle.kts pyproject.toml relayview/__init__.py tests/test_android_ui_contract.py RELEASE_NOTES-0.6.2.md
       git commit -m "RelayView v0.6.2 - Fix Android system bar insets"
       git push origin main
  4. After CI's debug build passes, publish the signed Android update:
       git tag v0.6.2
       git push origin v0.6.2

You must keep using the SAME Android signing keystore and credentials as
v0.6.1, so that in-app updates work without uninstalling and losing data.

Validation: Python regression/source tests passed (78 passed, 2 skipped).
Android compilation and on-device layout behaviour must be validated in CI
and on the Pixel 10 Pro XL and OnePlus 9 Pro.
