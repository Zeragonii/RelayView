"""CI guard: native smoke check must be executed in module mode."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_import_from_module_entrypoint():
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.smoke_mpv", "--import-only"],
        cwd=ROOT, text=True, capture_output=True, timeout=15,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "libmpv smoke module import OK" in proc.stdout


def test_windows_workflow_calls_smoke_as_module():
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    assert "python -m scripts.smoke_mpv" in workflow
    assert "python scripts/smoke_mpv.py" not in workflow
