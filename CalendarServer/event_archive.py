"""Append-only event snapshots for delivery by the remote Telegram bot."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, update

from .database_models import ArchiveRecord, AnnualEvent, DailyEvent, EventType


def record(session, kind, obj, action, actor):
    session.flush()
    group = session.get(EventType, obj.type_id)
    fields = {column.name: getattr(obj, column.name) for column in obj.__table__.columns}
    for key, value in fields.items():
        if isinstance(value, datetime):
            fields[key] = value.isoformat()
    group_fields = ({column.name: getattr(group, column.name) for column in group.__table__.columns}
                    if group else None)
    archive_id = uuid4().hex
    session.add(ArchiveRecord(archive_id=archive_id, payload={
        "schema": "r_cal.event_archive.v1", "archive_id": archive_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "action": action, "kind": kind, "actor": actor,
        "event": fields, "group": group_fields,
    }))


def pending(repository):
    with repository.session_scope() as session:
        rows = session.scalars(select(ArchiveRecord).where(
            ArchiveRecord.delivered.is_(False)).order_by(ArchiveRecord.id).limit(10)).all()
        return {"records": [{"sequence": row.id, **row.payload} for row in rows]}


def acknowledge(repository, ids):
    with repository.session_scope(commit=True) as session:
        session.execute(update(ArchiveRecord).where(ArchiveRecord.archive_id.in_(ids)).values(delivered=True))
    return {"status": "ok"}


def snapshot(repository, actor):
    with repository.session_scope(commit=True) as session:
        count = 0
        for kind, model in (("annual", AnnualEvent), ("daily", DailyEvent)):
            for obj in session.scalars(select(model).order_by(model.id)):
                record(session, kind, obj, "snapshot", actor)
                count += 1
    return {"queued": count}
