"""Native libmpv smoke check for the pinned Windows DLL in CI.

Run from the repository root as ``python -m scripts.smoke_mpv``.
Directly running scripts/smoke_mpv.py does not put the project root on
sys.path, and consequently cannot import the ``relayview`` package.
"""
from __future__ import annotations

import sys

from relayview.mpv_native import MpvClient, view_properties


def main(arguments: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    if args == ["--import-only"]:
        # Portable preflight that exercises the *exact* module entry point
        # without requiring a bundled Windows DLL on Linux test runners.
        assert view_properties(1.0, 0.5, 0.5)["video-zoom"] == 0.0
        print("libmpv smoke module import OK")
        return 0
    if args:
        raise SystemExit("Usage: python -m scripts.smoke_mpv [--import-only]")

    client = MpvClient()
    client.initialize(None, headless=True)
    client.property("volume", 40)
    for name, value in view_properties(3, 0.35, 0.65).items():
        client.property(name, value)
    assert client.read("volume") is not None
    print("libmpv native API initialized and zoom/alignment properties accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
