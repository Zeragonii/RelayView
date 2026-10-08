from relayview.logging_config import redact_url, set_log_level, get_log_level


def test_redact_url_credentials_and_secrets():
    value = "rtsp://user:password@example.local:8554/cam?token=abc123&quality=high"
    redacted = redact_url(value)
    assert "user" not in redacted
    assert "password" not in redacted
    assert "abc123" not in redacted
    assert "example.local:8554" in redacted
    assert "quality=" in redacted
    assert "quality=high" not in redacted


def test_log_level_switching():
    assert set_log_level("DEBUG") == "DEBUG"
    assert get_log_level() == "DEBUG"
    assert set_log_level("not-a-level") == "ERROR"
    assert get_log_level() == "ERROR"
