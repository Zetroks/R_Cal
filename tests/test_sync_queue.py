"""Outbox tests use a temporary database and never contact Google."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from CalendarServer import database_models as db, google_sync
from CalendarServer.database import EventRepository
from CalendarServer.sync_queue import SyncWorker, utcnow
from CalendarService.dto_models import EventUpsertDTO
from CalendarServer import event_archive
from fastapi import HTTPException


@pytest.fixture
def repo(tmp_path):
    repository = EventRepository.__new__(EventRepository)
    repository.engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    db.Base.metadata.create_all(repository.engine)
    repository.Session = sessionmaker(bind=repository.engine, autoflush=False)
    with repository.session_scope(commit=True) as session:
        session.add(db.EventType(id=1, name="Test", color="#fff", google_sync_enabled=True,
                                 google_calendar_id="target"))
    yield repository
    repository.engine.dispose()


def dto(**values):
    data = dict(action="upsert", kind="annual", title="First", type_id=1, version=1,
                start_date=datetime(2026, 10, 1, 12), end_date=datetime(2026, 10, 1, 13))
    return EventUpsertDTO(**(data | values))


ADMIN = SimpleNamespace(is_admin=True, login="admin")


def test_save_commits_without_google_and_survives_worker_restart(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(google_sync, "push_event", lambda *args: calls.append(args))
    result = repo.create_event(dto(), ADMIN)
    assert calls == []
    with repo.session_scope() as session:
        assert session.get(db.AnnualEvent, result["id"]).title == "First"
        assert session.query(db.GoogleSyncJob).count() == 1
        assert session.query(db.EventChangeLog).count() == 1
    worker = SyncWorker(repo)
    assert worker.process_one()
    assert calls[0][1].title == "First"
    assert calls[0][1].google_event_id == result["google_event_id"]
    assert not SyncWorker(repo).process_one()


def test_ordered_update_and_delete_use_same_remote_id(repo, monkeypatch):
    calls = []
    monkeypatch.setattr(google_sync, "push_event", lambda k, obj, group: calls.append(obj.title))
    monkeypatch.setattr(google_sync, "delete_google_event", lambda t, gid: calls.append(gid) or True)
    result = repo.create_event(dto(), ADMIN)
    repo.update_event(dto(id=result["id"], title="Second", version=2), ADMIN)
    repo.delete_event(dto(id=result["id"], version=2), ADMIN)
    worker = SyncWorker(repo)
    assert worker.process_one()
    assert worker.process_one()
    assert worker.process_one()
    assert calls == ["First", "Second", result["google_event_id"]]


def test_failed_job_retries_and_blocks_only_its_own_event(repo, monkeypatch):
    result = repo.create_event(dto(), ADMIN)
    repo.update_event(dto(id=result["id"], title="Second", version=2), ADMIN)
    repo.create_event(dto(title="Unrelated"), ADMIN)
    calls = []

    def push(kind, obj, group):
        calls.append(obj.title)
        if obj.title == "First":
            raise OSError("offline")

    monkeypatch.setattr(google_sync, "push_event", push)
    worker = SyncWorker(repo)
    worker.process_one()
    worker.process_one()
    assert calls == ["First", "Unrelated"]
    assert not worker.process_one()
    with repo.session_scope(commit=True) as session:
        job = session.query(db.GoogleSyncJob).order_by(db.GoogleSyncJob.id).first()
        assert job.attempts == 1 and "offline" in job.last_error
        job.retry_at = utcnow() - timedelta(seconds=1)
    monkeypatch.setattr(google_sync, "push_event", lambda k, obj, group: calls.append(obj.title))
    assert SyncWorker(repo).process_one()
    assert worker.process_one()
    assert calls[-2:] == ["First", "Second"]


def test_enqueue_failure_rolls_back_event_and_log(repo, monkeypatch):
    def fail(*args):
        raise RuntimeError("Cannot queue")
    monkeypatch.setattr(repo, "_google_after_write", fail)
    with pytest.raises(RuntimeError):
        repo.create_event(dto(), ADMIN)
    with repo.session_scope() as session:
        assert session.query(db.AnnualEvent).count() == 0
        assert session.query(db.EventChangeLog).count() == 0


def test_disabled_group_does_not_queue(repo):
    with repo.session_scope(commit=True) as session:
        session.get(db.EventType, 1).google_sync_enabled = False
    repo.create_event(dto(), ADMIN)
    assert not SyncWorker(repo).process_one()


def test_group_sync_queues_instead_of_contacting_google(repo, monkeypatch):
    repo.create_event(dto(), ADMIN)
    monkeypatch.setattr(google_sync, "push_event", lambda *a: pytest.fail("Network during request"))
    assert repo.sync_group_to_google(1, ADMIN)["queued"] == 1


def test_google_insert_retry_uses_reserved_id(monkeypatch):
    class NotFound(Exception):
        pass
    bodies = []
    class Events:
        def patch(self, **kw):
            raise NotFound("404")
        def insert(self, **kw):
            bodies.append(kw["body"])
            return SimpleNamespace(execute=lambda: {"id": kw["body"]["id"]})
    monkeypatch.setattr(google_sync, "_service", lambda: SimpleNamespace(events=Events))
    obj = SimpleNamespace(id=1, version=1, title="A", google_event_id="abc123",
                          _google_insert_id="abc123", start_date=datetime(2026, 1, 1),
                          end_date=datetime(2026, 1, 2))
    group = SimpleNamespace(google_calendar_id="target")
    assert google_sync.push_event("annual", obj, group) == "abc123"
    assert bodies[0]["id"] == "abc123"


@pytest.mark.parametrize("kind", ["annual", "daily"])
@pytest.mark.parametrize("allowed,success", [(set(), False), ({1}, False), ({2}, False), ({1, 2}, True)])
def test_update_checks_source_and_destination(repo, kind, allowed, success):
    with repo.session_scope(commit=True) as session:
        session.add(db.EventType(id=2, name="Destination", color="#fff"))
        for type_id in allowed:
            session.add(db.EventTypeAccess(user_id=42, type_id=type_id, access_level="member"))
    result = repo.create_event(dto(kind=kind, day=1, month=2), ADMIN)
    change = dto(id=result["id"], kind=kind, day=3, month=2, type_id=2, title="Changed")
    user = SimpleNamespace(id=42, login="member", is_admin=False)
    if success:
        assert repo.update_event(change, user)["status"] == "updated"
    else:
        with pytest.raises(HTTPException) as error:
            repo.update_event(change, user)
        assert error.value.status_code == 403
        model = db.AnnualEvent if kind == "annual" else db.DailyEvent
        with repo.session_scope() as session:
            obj = session.get(model, result["id"])
            assert obj.title == "First" and obj.type_id == 1
            assert session.query(db.ArchiveRecord).count() == 1


def test_archive_contains_full_snapshots_and_ack_is_idempotent(repo):
    result = repo.create_event(dto(url='[{"type":"comment","value":"note"}]'), ADMIN)
    repo.update_event(dto(id=result["id"], title="Changed", version=2), ADMIN)
    repo.delete_event(dto(id=result["id"], version=2), ADMIN)
    rows = event_archive.pending(repo)["records"]
    assert [r["action"] for r in rows] == ["create", "update", "delete"]
    assert rows[0]["event"]["url"] == '[{"type":"comment","value":"note"}]'
    assert rows[0]["group"]["name"] == "Test"
    assert rows[0]["event"]["start_date"] == "2026-10-01T12:00:00"
    assert rows[1]["event"]["title"] == rows[2]["event"]["title"] == "Changed"
    assert [r["sequence"] for r in rows] == sorted(r["sequence"] for r in rows)
    assert event_archive.pending(repo)["records"] == rows  # polling is not an ACK
    ids = [r["archive_id"] for r in rows]
    event_archive.acknowledge(repo, ids)
    event_archive.acknowledge(repo, ids)
    assert event_archive.pending(repo)["records"] == []
    with repo.session_scope() as session:
        assert session.query(db.ArchiveRecord).count() == 3  # retained journal


def test_snapshot_archives_existing_events(repo):
    repo.create_event(dto(), ADMIN)
    repo.create_event(dto(kind="daily", day=2, month=3), ADMIN)
    assert event_archive.snapshot(repo, "admin") == {"queued": 2}
    rows = event_archive.pending(repo)["records"]
    assert [r["kind"] for r in rows if r["action"] == "snapshot"] == ["annual", "daily"]


def test_archive_failure_rolls_back_save_and_google_queue(repo, monkeypatch):
    def fail(*args):
        raise OSError("Cannot archive")
    monkeypatch.setattr(event_archive, "record", fail)
    with pytest.raises(OSError):
        repo.create_event(dto(), ADMIN)
    with repo.session_scope() as session:
        assert session.query(db.AnnualEvent).count() == 0
        assert session.query(db.GoogleSyncJob).count() == 0
        assert session.query(db.EventChangeLog).count() == 0
