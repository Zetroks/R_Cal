import io
import json
import pytest
from scripts import check_health as health


def test_health_checks_both_services_and_versions(monkeypatch):
    urls = []
    def open_url(url, timeout):
        urls.append(url)
        payload = {"status": "ok"} if url.endswith("/") else {"build": health.BUILD, "protocol": health.PROTOCOL}
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(health, "urlopen", open_url)
    health.check_once(8011, 8002)
    assert urls == ["http://127.0.0.1:8011/", "http://127.0.0.1:8011/version",
                    "http://127.0.0.1:8002/app-version"]


def test_stale_web_build_fails_health(monkeypatch):
    def open_url(url, timeout):
        payload = ({"status": "ok"} if url.endswith("/") else
                   {"build": "old" if "app-version" in url else health.BUILD, "protocol": health.PROTOCOL})
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(health, "urlopen", open_url)
    with pytest.raises(RuntimeError, match="Unexpected version"):
        health.check_once(8011, 8002)


def test_exhausted_retries_return_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(health, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("CAL_SERVER_PORT", "8011")
    monkeypatch.setenv("CAL_WEB_PORT", "8002")
    monkeypatch.setattr(health.time, "sleep", lambda seconds: None)
    def fail(api, web):
        calls.append((api, web))
        raise OSError("Unavailable")
    monkeypatch.setattr(health, "check_once", fail)
    assert health.main() == 1
    assert calls == [(8011, 8002)] * 15
