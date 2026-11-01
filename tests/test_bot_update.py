import asyncio
from types import SimpleNamespace

import pytest
from CalendarBot import self_update, bot


def test_prepare_pulls_and_checks_bot_before_restart(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        output = 'abc123' if args[:2] == ['git', 'rev-parse'] else ''
        return SimpleNamespace(returncode=0, stdout=output, stderr='')
    monkeypatch.setattr(self_update.subprocess, 'run', run)
    assert self_update.prepare_update()[0] == 0
    assert calls[2] == ['git', 'pull', '--ff-only']
    assert any('requirements-bot.txt' in cmd for cmd in calls)
    assert calls[-1][-1] == 'from CalendarBot.bot import build_app; build_app()'
    assert not any('systemctl' in cmd for cmd in calls)


@pytest.mark.parametrize('failure', ['dirty', 'pull', 'pip', 'validate'])
def test_prepare_stops_on_failed_step(monkeypatch, failure):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        output = ' M CalendarBot/bot.py' if failure == 'dirty' and 'status' in args else ''
        failed = ((failure == 'pull' and 'pull' in args) or
                  (failure == 'pip' and 'pip' in args) or
                  (failure == 'validate' and '-c' in args))
        return SimpleNamespace(returncode=int(failed), stdout=output, stderr='test error')
    monkeypatch.setattr(self_update.subprocess, 'run', run)
    assert self_update.prepare_update()[0] != 0
    if failure == 'dirty':
        assert len(calls) == 1
    if failure == 'pip':
        assert not any('-c' in cmd for cmd in calls)


def test_restart_targets_own_user_manager(monkeypatch):
    calls = []
    monkeypatch.setattr(self_update.os, 'getuid', lambda: 1234, raising=False)
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr(self_update.subprocess, 'run', run)
    self_update.restart('calendar-bot')
    assert calls[0][0] == ['systemctl', '--user', '--no-block', 'restart', 'calendar-bot']
    assert calls[0][1]['env']['XDG_RUNTIME_DIR'] == '/run/user/1234'


@pytest.mark.parametrize('server_code,bot_code,expected', [(1, 0, ['server']),
                                                        (0, 1, ['server', 'bot']),
                                                        (0, 0, ['server', 'bot', 'restart'])])
def test_update_pipeline_only_restarts_after_success(monkeypatch, server_code, bot_code, expected):
    calls = []
    async def reply(*args, **kwargs):
        pass
    def server():
        calls.append('server')
        return server_code, 'server result'
    def prepare():
        calls.append('bot')
        return bot_code, 'bot result'
    monkeypatch.setattr(bot, 'ADMIN_ID', 42)
    monkeypatch.setattr(bot, '_run_update', server)
    monkeypatch.setattr(bot, '_req', lambda *a: SimpleNamespace(status_code=200, json=lambda: {'build': 'test'}))
    monkeypatch.setattr(self_update, 'prepare_update', prepare)
    monkeypatch.setattr(self_update, 'restart', lambda unit: calls.append('restart'))
    context = SimpleNamespace(bot_data={})
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), callback_query=SimpleNamespace(
        answer=reply, edit_message_text=reply, data='upd:yes', message=SimpleNamespace(reply_text=reply)))
    asyncio.run(bot.update_decision(update, context))
    assert calls == expected
    assert not context.bot_data['update_in_progress']
