"""Persistent Google outbox. Run one API process per database (as in systemd).

Jobs are committed with the event; network calls never hold a DB transaction.
Ordering is preserved for each Google event, including retries and deletions.
"""

import logging
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

from . import google_sync
from .database_models import GoogleSyncJob


def utcnow():
    # SQLite DateTime stores naive values; all queue timestamps represent UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_write(session, kind, obj, event_type):
    if not event_type or not google_sync.is_sync_enabled(event_type):
        return
    target = google_sync.resolve_target_calendar(event_type)
    if not target:
        return
    # Google accepts UUID hex IDs. Reserve before sending so retries cannot
    # create duplicate remote events after a crash or ambiguous network failure.
    if not obj.google_event_id:
        obj.google_event_id = uuid4().hex
    fields = {name: getattr(obj, name, None) for name in (
        "id", "version", "title", "url", "start_date", "end_date", "day", "month", "google_event_id")}
    for name in ("start_date", "end_date"):
        if fields[name] is not None:
            fields[name] = fields[name].isoformat()
    session.add(GoogleSyncJob(payload={
        "action": "upsert", "kind": kind, "fields": fields,
        "target": target, "gid": obj.google_event_id,
        "color": event_type.google_color_id, "visibility": event_type.google_visibility,
    }))


def enqueue_delete(session, gid, event_type):
    target = google_sync.resolve_target_calendar(event_type) if event_type else None
    if gid and target:
        session.add(GoogleSyncJob(payload={"action": "delete", "target": target, "gid": gid}))


class SyncWorker:
    def __init__(self, repository):
        self.repository = repository
        self.stopped = Event()
        self.thread = Thread(target=self.run, name="google-sync", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=2)

    def run(self):
        while not self.stopped.is_set():
            try:
                if self.process_one():
                    continue
            except Exception:
                logging.exception("Google queue worker failed")
            self.stopped.wait(1)

    def process_one(self):
        now = utcnow()
        with self.repository.session_scope() as session:
            # A failed event must not block unrelated events, but its subsequent
            # writes/deletion must wait until the preceding operation succeeds.
            blocked = set()
            selected = None
            for job in session.query(GoogleSyncJob).order_by(GoogleSyncJob.id):
                payload = job.payload
                key = (payload["target"], payload["gid"])
                if key not in blocked and job.retry_at <= now:
                    selected = (job.id, payload)
                    break
                blocked.add(key)
        if selected is None:
            return False
        job_id, payload = selected
        try:
            if payload["action"] == "delete":
                if not google_sync.delete_google_event(payload["target"], payload["gid"]):
                    raise RuntimeError("Google delete failed; see server log")
            else:
                obj = SimpleNamespace(**payload["fields"], _google_insert_id=payload["gid"])
                group = SimpleNamespace(google_calendar_id=payload["target"],
                                        google_color_id=payload["color"],
                                        google_visibility=payload["visibility"])
                google_sync.push_event(payload["kind"], obj, group)
        except Exception as exc:
            logging.exception("Google sync job %s failed; will retry", job_id)
            with self.repository.session_scope(commit=True) as session:
                job = session.get(GoogleSyncJob, job_id)
                job.attempts += 1
                job.last_error = str(exc)[:2000]
                job.retry_at = utcnow() + timedelta(seconds=min(300, 2 ** min(job.attempts, 8)))
        else:
            with self.repository.session_scope(commit=True) as session:
                session.delete(session.get(GoogleSyncJob, job_id))
        return True
