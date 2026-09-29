from fastapi import HTTPException

from . import database_models
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
                session.delete(obj)
                session.flush()

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
            session.delete(obj)
            session.flush()

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

            return obj

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
