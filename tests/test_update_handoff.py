import sys
import types
import pytest
# Qt is intentionally absent in the headless CI environment.
qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QThread = type("QThread", (), {})
qtcore.Signal = lambda *args: None
qt = types.ModuleType("PySide6")
sys.modules.setdefault("PySide6", qt)
sys.modules.setdefault("PySide6.QtCore", qtcore)
from relayview import updater


def test_update_handoff_uses_external_updater_and_restart(monkeypatch):
    calls = []
    class Manager:
        def __init__(self, source):
            calls.append(("source", source))
        def get_update_pending_restart(self):
            return "pending-release"
        def wait_exit_then_apply_updates(self, update, **kwargs):
            calls.append(("handoff", update, kwargs))
    monkeypatch.setattr(updater, "REPOSITORY_URL", "https://example.test/releases")
    monkeypatch.setitem(sys.modules, "velopack", types.SimpleNamespace(UpdateManager=Manager))
    updater.handoff_update_and_restart()
    assert calls[-1] == ("handoff", "pending-release", {"silent": False, "restart": True})


def test_update_handoff_refuses_missing_pending_package(monkeypatch):
    class Manager:
        def __init__(self, source):
            pass
        def get_update_pending_restart(self):
            return None
    monkeypatch.setattr(updater, "REPOSITORY_URL", "https://example.test/releases")
    monkeypatch.setitem(sys.modules, "velopack", types.SimpleNamespace(UpdateManager=Manager))
    with pytest.raises(RuntimeError, match="No downloaded update"):
        updater.handoff_update_and_restart()
