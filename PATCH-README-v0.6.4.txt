RelayView v0.6.4 - Single-view mouse wheel zoom

Extract the contents of RelayView-v0.6.4-Single-View-Zoom-Patch.zip
into your existing RelayView git checkout, preserving directory paths.

The patch is based on the v0.6.3 complete source generated in this chat.
It does not modify the libmpv playback engine or the Android UI.

Run: python -m pytest -q
Then commit and push main to confirm your GitHub Actions Windows build.
If using the existing tag-based workflow, publish as v0.6.4 after the main build passes.
