from fastapi import HTTPException

from . import database_models
from . import google_sync
import logging

from datetime import date
from pathlib import Path
from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from .database_models import AnnualEvent, DailyEvent, EventType, EventTypeAccess
from typing import TypedDict, List, Dict, Set
from CalendarService import dto_models

DailyEvents = TypedDict("DailyEvents", {"annual": List[AnnualEvent], "daily": List[DailyEvent]})
MonthEvents = Dict[int, DailyEvents]
YearEvents = Dict[int, MonthEvents]


def serialize_event(event: database_models.AnyEventModel, restricted: list[int]) -> dict:
    ret = {}
    is_restricted = False
    if isinstance(event, database_models.EventModel):
        if event.type_id in restricted:
            is_restricted = True

    for item in event.__serializable__:  # type: ignore
        if is_restricted and item in event.__restricted__:
            ret[item] = "restricted"
        else:
            attr = getattr(event, item)
            if isinstance(attr, database_models.AnyEventModel):
                ret[item] = serialize_event(attr, restricted)
            else:
                ret[item] = str(attr)
    return ret


def serialize_day(data, restricted: list[int]):
    return {
        "annual": [serialize_event(e, restricted) for e in data["annual"]],
        "daily": [serialize_event(e, restricted) for e in data["daily"]],
    }


class EventRepository:
    DATABASE_URL = f"sqlite:///{(Path(__file__).resolve().parent / 'calendar.db').as_posix()}"
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if hasattr(self, "_ready"):
            return

        self.engine = create_engine(self.DATABASE_URL, echo=False, future=True)
        database_models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self._ready = True

    @contextmanager
    def session_scope(self, commit=False):
        session = self.Session()
        try:
            yield session
            if commit:
                session.commit()
        except:
            session.rollback()
            logging.exception("DB error")
            raise
        finally:
            session.close()

    def get_all_type_colors(self, user: database_models.User) -> dict:
        with self.session_scope() as session:
            if user.is_admin:
                color_types = session.query(EventType).all()
                return {"event_types": [serialize_event(e, []) for e in color_types]}

            access_map = self.get_user_access(user, session=session)
            allowed_type_ids = [type_id for type_id, access in access_map.items() if
                                access in dto_models.available_access_names]
            color_types = session.query(EventType).filter(
                EventType.id.in_(allowed_type_ids)
            ).all()
            return {"event_types": [serialize_event(e, []) for e in color_types]}
            # return color_types

    def get_events_for_day(self, d: date, user: database_models.User) -> dict:
        iso = d.isoformat()
        with self.session_scope() as session:
            if user.is_admin:
                annual = session.query(AnnualEvent).filter(
                    AnnualEvent.start_date <= iso,
                    AnnualEvent.end_date >= iso
                ).all()
                daily = session.query(DailyEvent).filter(
                    DailyEvent.day == d.day,
                    DailyEvent.month == d.month
                ).all()

                return serialize_day({"annual": annual, "daily": daily}, [])
            access_map = self.get_user_access(user, session=session)
            allowed_type_ids = [type_id for type_id, access in access_map.items() if
                                access in dto_models.available_access_names]
            restricted_type_ids = [type_id for type_id, access in access_map.items() if access == "restricted"]

            annual = session.query(AnnualEvent).filter(
                AnnualEvent.start_date <= iso,
                AnnualEvent.end_date >= iso,
                AnnualEvent.type_id.in_(allowed_type_ids)
            ).all()
            daily = session.query(DailyEvent).filter(
                DailyEvent.day == d.day,
                DailyEvent.month == d.month,
                DailyEvent.type_id.in_(allowed_type_ids)
            ).all()

            return serialize_day({"annual": annual, "daily": daily}, restricted_type_ids)

    def get_events_in_range(self, from_date: date, to_date: date, user: database_models.User) -> dict:
        from_iso = from_date.isoformat()
        to_iso = to_date.isoformat()
        with self.session_scope() as session:
            if user.is_admin:
                annual = session.query(AnnualEvent).filter(
                    AnnualEvent.start_date <= to_iso,
                    AnnualEvent.end_date >= from_iso
                ).all()
                daily = session.query(DailyEvent).filter(
                    or_(
                        and_(DailyEvent.month == from_date.month, DailyEvent.day >= from_date.day),
                        and_(DailyEvent.month == to_date.month, DailyEvent.day <= to_date.day),
                        and_(DailyEvent.month > from_date.month, DailyEvent.month < to_date.month),
                    )
                ).all()

                return serialize_day({"annual": annual, "daily": daily}, [])
            access_map = self.get_user_access(user, session=session)
            allowed_type_ids = [type_id for type_id, access in access_map.items() if
                                access in dto_models.available_access_names]
            restricted_type_ids = [type_id for type_id, access in access_map.items() if access == "restricted"]
            annual = session.query(AnnualEvent).filter(
                AnnualEvent.start_date <= to_iso,
                AnnualEvent.end_date >= from_iso,
                AnnualEvent.type_id.in_(allowed_type_ids)
            ).all()
            daily = session.query(DailyEvent).filter(
                or_(
                    and_(DailyEvent.month == from_date.month, DailyEvent.day >= from_date.day),
                    and_(DailyEvent.month == to_date.month, DailyEvent.day <= to_date.day),
                    and_(DailyEvent.month > from_date.month, DailyEvent.month < to_date.month),
                ),
                DailyEvent.type_id.in_(allowed_type_ids)
            ).all()

            return serialize_day({"annual": annual, "daily": daily}, restricted_type_ids)

    def create_event(self, dto: dto_models.EventUpsertDTO, user: database_models.User) -> database_models.EventModel:
        with self.session_scope() as session:
            if not user.is_admin:
                print(user.id)
                user_editable_access = self.get_user_editable(user, session=session)
                print(user_editable_access)
                if dto.type_id not in user_editable_access:
                    raise HTTPException(status_code=403, detail="Not enough access")

            if dto.kind == "annual":
                obj = database_models.AnnualEvent(
                    title=dto.title,
                    start_date=dto.start_date,
                    end_date=dto.end_date,
                    url=dto.url,
                    type_id=dto.type_id,
                    version=dto.version,
                    updated_by=user.login,
                )

            elif dto.kind == "daily":
                obj = database_models.DailyEvent(
                    title=dto.title,
                    day=dto.day,
                    month=dto.month,
                    type_id=dto.type_id,
                    version=dto.version,
                    updated_by=user.login,
                )

            else:
                raise ValueError(f"Unknown kind: {dto.kind}")

            session.add(obj)
            session.commit()
            session.refresh(obj)
            self._google_after_write(dto.kind, obj, session)
            return obj

    def delete_event(self, dto: dto_models.EventUpsertDTO, user: database_models.User) -> dict:
        model = {
            "annual": AnnualEvent,
            "daily": DailyEvent
        }.get(dto.kind)

        if model is None:
            raise ValueError("Unknown event type")

        with (self.session_scope(commit=True) as session):
            if user.is_admin:
                obj = session.query(model).filter(
                    model.id == dto.id,
                    model.version <= dto.version
                ).first()
                if not obj:
                    raise Exception("Version conflict or not found")
                self._track_history_object(obj, session)
                gid, tid = obj.google_event_id, obj.type_id
                session.delete(obj)
                session.flush()
                self._google_after_delete(dto.kind, gid, tid)

                return {"status": "deleted", "id": dto.id}

            user_editable_access = self.get_user_editable(user, session=session)
            if dto.type_id not in user_editable_access:
                raise HTTPException(status_code=403, detail="Not enough access")

            obj = session.query(model).filter(
                model.id == dto.id,
                model.version <= dto.version,
                model.type_id == dto.type_id
            ).first()
            if not obj:
                raise Exception("Version conflict or not found")
            self._track_history_object(obj, session)
            gid, tid = obj.google_event_id, obj.type_id
            session.delete(obj)
            session.flush()
            self._google_after_delete(dto.kind, gid, tid)

            return {"status": "deleted", "id": dto.id}

    def update_event(self, dto: dto_models.EventUpsertDTO, user: database_models.User) -> database_models.EventModel:
        with self.session_scope() as session:
            if dto.kind == "annual":
                obj = session.get(database_models.AnnualEvent, dto.id)
                if not obj:
                    raise ValueError("AnnualEvent not found")
                if not user.is_admin:
                    user_editable_access = self.get_user_editable(user, session=session)
                    if obj.type_id not in user_editable_access:
                        raise HTTPException(status_code=403, detail="Not enough access")
                self._track_history_object(obj, session)

                obj.title = dto.title
                obj.start_date = dto.start_date
                obj.end_date = dto.end_date
                obj.type_id = dto.type_id
                obj.version = dto.version
                obj.updated_by = user.login
                obj.url = dto.url
            elif dto.kind == "daily":
                obj = session.get(database_models.DailyEvent, dto.id)
                if not obj:
                    raise ValueError("DailyEvent not found")
                self._track_history_object(obj, session)

                obj.title = dto.title
                obj.day = dto.day
                obj.month = dto.month
                obj.type_id = dto.type_id
                obj.version = dto.version
                obj.updated_by = user.login

            else:
                raise ValueError(f"Unknown kind: {dto.kind}")

            session.commit()
            session.refresh(obj)
            self._google_after_write(dto.kind, obj, session)

            return obj

    def update_event_type(self, dto, user: database_models.User) -> dict:
        with self.session_scope() as session:
            obj = session.get(EventType, dto.id)
            if not obj:
                raise HTTPException(status_code=404, detail="EventType not found")
            if not user.is_admin:
                editable = self.get_user_editable(user, session=session)
                if dto.id not in editable:
                    raise HTTPException(status_code=403, detail="Not enough access")
            old_enabled = bool(obj.google_sync_enabled)
            old_target = obj.google_calendar_id or ""
            if dto.name is not None:
                obj.name = dto.name
            if dto.color is not None:
                obj.color = dto.color
            if dto.google_calendar_id is not None:
                obj.google_calendar_id = dto.google_calendar_id.strip() or None
            if dto.google_color_id is not None:
                obj.google_color_id = dto.google_color_id.strip() or None
            if dto.google_visibility is not None:
                obj.google_visibility = dto.google_visibility.strip() or None
            if dto.google_sync_enabled is not None:
                obj.google_sync_enabled = dto.google_sync_enabled
            obj.version = (obj.version or 0) + 1
            session.commit()
            session.refresh(obj)
            need_backfill = bool(obj.google_sync_enabled) and (
                not old_enabled or (obj.google_calendar_id or "") != old_target
            )
            type_id = obj.id
        stats = None
        if need_backfill:
            stats = self.sync_group_to_google(type_id, user)
        with self.session_scope() as session:
            obj = session.get(EventType, type_id)
            data = serialize_event(obj, [])
        return {"event_type": data, "sync": stats}

    def sync_group_to_google(self, type_id: int, user: database_models.User) -> dict:
        with self.session_scope() as session:
            event_type = session.get(EventType, type_id)
            if not event_type:
                raise HTTPException(status_code=404, detail="EventType not found")
            if not user.is_admin:
                editable = self.get_user_editable(user, session=session)
                if type_id not in editable:
                    raise HTTPException(status_code=403, detail="Not enough access")
            if not google_sync.is_sync_enabled(event_type):
                return {"target": None, "inserted": 0, "updated": 0, "errors": ["sync not enabled"]}
            target = google_sync.resolve_target_calendar(event_type)
            if not target:
                raise HTTPException(status_code=400, detail="No target Google calendar")
            annual = session.query(AnnualEvent).filter(AnnualEvent.type_id == type_id).all()
            daily = session.query(DailyEvent).filter(DailyEvent.type_id == type_id).all()
            inserted = updated = 0
            errors: list = []
            for kind, obj in [("annual", o) for o in annual] + [("daily", o) for o in daily]:
                try:
                    was = bool(obj.google_event_id)
                    obj.google_event_id = google_sync.push_event(kind, obj, event_type)
                    if was:
                        updated += 1
                    else:
                        inserted += 1
                except Exception as exc:  # noqa: BLE001 - per-event errors must not abort backfill
                    errors.append(f"{kind}:{obj.id}: {exc}")
                    if len(errors) > 20:
                        errors.append("...truncated")
                        break
            session.commit()
            return {"target": target, "inserted": inserted, "updated": updated, "errors": errors}

    @staticmethod
    def get_google_calendars() -> dict:
        try:
            return {"calendars": google_sync.list_calendars()}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Google unavailable: {exc}")

    def get_user(self, username: str, session=None) -> database_models.User | None:
        def get(_session):
            user = _session.query(database_models.User).filter(
                database_models.User.login == username
            ).first()
            return user

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_user_by_telegram_id(self, telegram_id) -> database_models.User | None:
        return None

    def get_user_access(self, user: database_models.User, session=None) -> Dict[int, str]:
        def get(_session):
            access = _session.query(database_models.EventTypeAccess).filter_by(user_id=user.id).all()
            return {a.type_id: a.access_level for a in access}

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_user_editable(self, user: database_models.User, session=None) -> Set[int]:
        def get(_session):
            editable = session.query(EventTypeAccess).filter(
                EventTypeAccess.user_id == user.id,
                EventTypeAccess.access_level.in_(["editor", "owner"])
            ).all()
            return {e.type_id for e in editable}

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_front_user_access(self, user: database_models.User, session=None):
        if user.is_admin:
            return {"IsAdmin": True}

        def get(_session):
            # editable = self.get_user_editable(user, _session)
            # return {"editable": editable, "access": access}
            access = self.get_user_access(user, _session)
            return access

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    @staticmethod
    def _google_after_write(kind: str, obj, session) -> None:
        try:
            event_type = session.get(EventType, obj.type_id)
            if event_type is None or not google_sync.is_sync_enabled(event_type):
                return
            gid = google_sync.push_event(kind, obj, event_type)
            if gid != obj.google_event_id:
                obj.google_event_id = gid
                session.commit()
        except Exception:
            logging.exception("Google sync failed for %s id=%s", kind, getattr(obj, "id", None))

    def _google_after_delete(self, kind: str, google_event_id: str | None, type_id: int) -> None:
        if not google_event_id:
            return
        try:
            with self.session_scope() as session:
                event_type = session.get(EventType, type_id)
                target = google_sync.resolve_target_calendar(event_type) if event_type else None
            if target:
                google_sync.delete_google_event(target, google_event_id)
        except Exception:
            logging.exception("Google unsync failed for %s", google_event_id)

    @staticmethod
    def _track_history_object(obj, session):
        print(f"_track_history_object for {obj}")
        if isinstance(obj, database_models.DailyEvent):
            history = database_models.DailyEventHistory(
                event_id=obj.id,
                title=obj.title,
                day=obj.day,
                month=obj.month,
                version=obj.version,
                updated_at=obj.updated_at,
                updated_by=obj.updated_by,
            )
            session.add(history)
        elif isinstance(obj, database_models.AnnualEvent):
            history = database_models.AnnualEventHistory(
                event_id=obj.id,
                title=obj.title,
                start_date=obj.start_date,
                end_date=obj.end_date,
                url=obj.url,
                version=obj.version,
                updated_at=obj.updated_at,
                updated_by=obj.updated_by,
            )
            session.add(history)
