import asyncio
import json
from types import SimpleNamespace
from CalendarBot import bot


def test_delivery_acknowledges_only_after_telegram_success(monkeypatch):
    calls = []
    record = {"sequence": 1, "archive_id": "abc", "action": "create", "kind": "daily",
              "recorded_at": "2026-11-01", "event": {"id": 2, "title": "Event"}}
    def req(method, path, headers, **kwargs):
        calls.append(path)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"records": [record]})
    async def send(**kwargs):
        calls.append("telegram")
        assert json.loads(kwargs["document"].getvalue()) == record
        assert kwargs["chat_id"] == -123
    monkeypatch.setattr(bot, "ARCHIVE_CHAT_ID", -123)
    monkeypatch.setattr(bot, "_req", req)
    asyncio.run(bot.poll_archive(SimpleNamespace(bot=SimpleNamespace(send_document=send))))
    assert calls == ["/archive/pending", "telegram", "/archive/ack"]


def test_telegram_failure_does_not_ack(monkeypatch):
    calls = []
    def req(method, path, headers, **kwargs):
        calls.append(path)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"records": [
            {"sequence": 1, "archive_id": "abc", "action": "create", "kind": "daily",
             "recorded_at": "now", "event": {"id": 1}}]})
    async def fail(**kwargs):
        raise OSError("Telegram down")
    monkeypatch.setattr(bot, "ARCHIVE_CHAT_ID", -123)
    monkeypatch.setattr(bot, "_req", req)
    asyncio.run(bot.poll_archive(SimpleNamespace(bot=SimpleNamespace(send_document=fail))))
    assert calls == ["/archive/pending"]
