"""Check/fix obsolete files left by in-place extraction of the v0.5.0 zip.

The replacement source archive cannot delete files that remain tracked in an
existing Git checkout. Run `python scripts/cleanup_mpv_migration.py --fix`
from the RelayView repository root, then `git add -A` and commit the deletions.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATHS = (
    'relayview/vlc_backend.py',
    'scripts/trim_vlc.ps1',
    'tests/test_viewport_zoom.py',
    'tests/test_vlc_lifecycle.py',
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fix', action='store_true', help='Delete only known obsolete migration files')
    args = parser.parse_args()

    stale = [ROOT / relative for relative in LEGACY_PATHS if (ROOT / relative).is_file()]
    if not stale:
        print('libmpv migration cleanup: OK (no obsolete files)')
        return 0

    for path in stale:
        if args.fix:
            path.unlink()
            print(f'Removed: {path.relative_to(ROOT).as_posix()}')
        else:
            print(f'Obsolete: {path.relative_to(ROOT).as_posix()}')

    if args.fix:
        print('Cleanup complete. Run git add -A to stage the deletions before committing.')
        return 0

    print('Migration not complete: run python scripts/cleanup_mpv_migration.py --fix, then git add -A')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
