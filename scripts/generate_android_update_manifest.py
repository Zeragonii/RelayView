"""Create a reproducible GitHub-release Android updater manifest.

The APK is signed by Gradle in CI before this script runs. App updater verifies
SHA256 and package name; Android package installer validates the signing cert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def version_code(version: str) -> int:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdecimal() for part in parts):
        raise ValueError("Version must be major.minor.patch")
    major, minor, patch = map(int, parts)
    if not (0 <= major <= 1999 and 0 <= minor <= 999 and 0 <= patch <= 999):
        raise ValueError("Android version code parts are out of range")
    code = major * 1_000_000 + minor * 1_000 + patch
    if code > 2_100_000_000:
        raise ValueError("Android version code exceeds distribution range")
    return code


def manifest(apk: Path, repo: str, version: str, package: str = "com.relayview.android") -> dict:
    if len(repo.split("/")) != 2 or any(not x for x in repo.split("/")):
        raise ValueError("Repository must be owner/repo")
    if not apk.is_file():
        raise FileNotFoundError(apk)
    with apk.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "version": version,
        "versionCode": version_code(version),
        "packageName": package,
        "apkUrl": f"https://github.com/{repo}/releases/download/v{version}/{apk.name}",
        "sha256": digest,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apk", type=Path, required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--output", type=Path, default=Path("android-update.json"))
    a = p.parse_args()
    a.output.write_text(json.dumps(manifest(a.apk, a.repo, a.version), indent=2) + "\n", encoding="utf-8")
    print(f"Written {a.output} for RelayView Android v{a.version}")


if __name__ == "__main__":
    main()
