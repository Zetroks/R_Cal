from fastapi import HTTPException

from . import database_models
from . import google_sync
import logging
import secrets

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import create_engine, and_, or_, func
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
            session.add(database_models.EventChangeLog(
                kind=dto.kind, event_id=obj.id, action="upsert"))
            session.commit()
            self._google_after_write(dto.kind, obj, session)
            return {"status": "created", "id": obj.id, "version": obj.version,
                    "google_event_id": obj.google_event_id}

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
                session.add(database_models.EventChangeLog(
                    kind=dto.kind, event_id=dto.id, action="delete"))
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
            session.add(database_models.EventChangeLog(
                kind=dto.kind, event_id=dto.id, action="delete"))
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
            session.add(database_models.EventChangeLog(
                kind=dto.kind, event_id=obj.id, action="upsert"))
            session.commit()
            self._google_after_write(dto.kind, obj, session)

            return {"status": "updated", "id": obj.id, "version": obj.version,
                    "google_event_id": obj.google_event_id}

    def update_event_type(self, dto, user: database_models.User) -> dict:
        with self.session_scope() as session:
            obj = session.get(EventType, dto.id)
            if not obj:
                raise HTTPException(status_code=404, detail="EventType not found")
            role = self._type_role(user, dto.id, session)
            rank = dto_models.GROUP_ACCESS[role.upper()]
            wants_type_edit = dto.name is not None or dto.color is not None
            wants_google = (dto.google_calendar_id is not None
                            or dto.google_color_id is not None
                            or dto.google_visibility is not None
                            or dto.google_sync_enabled is not None)
            if wants_type_edit and rank < dto_models.GROUP_ACCESS.EDITOR:
                raise HTTPException(status_code=403, detail="Not enough access")
            if wants_google and role != "owner":
                raise HTTPException(status_code=403, detail="Google settings: owner only")
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
            logging.info(
                "Google backfill type=%s target=%s inserted=%s updated=%s errors=%d",
                type_id, target, inserted, updated, len(errors),
            )
            if errors:
                logging.warning("Google backfill errors: %s", errors[:10])
            return {"target": target, "inserted": inserted, "updated": updated, "errors": errors}

    @staticmethod
    def get_google_calendars() -> dict:
        try:
            return {"calendars": google_sync.list_calendars()}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Google unavailable: {exc}")

    def get_updates(self, since: str, year: int, user: database_models.User) -> dict:
        # Всё время — UTC, чтобы не зависеть от часового пояса клиента.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_s = now.strftime("%Y-%m-%d %H:%M:%S")
        if not since:
            return {"updates": [], "server_time": now_s, "full_reload": True}
        with self.session_scope(commit=True) as session:
            cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            session.query(database_models.EventChangeLog).filter(
                database_models.EventChangeLog.created_at < cutoff
            ).delete(synchronize_session=False)
            over = session.query(database_models.EventChangeLog.id).order_by(
                database_models.EventChangeLog.id.desc()).offset(5000).all()
            if over:
                session.query(database_models.EventChangeLog).filter(
                    database_models.EventChangeLog.id.in_([r[0] for r in over])
                ).delete(synchronize_session=False)
            oldest = session.query(database_models.EventChangeLog.created_at).order_by(
                database_models.EventChangeLog.id.asc()).first()
            if oldest and oldest[0] and str(oldest[0]) > since:
                return {"updates": [], "server_time": now_s, "full_reload": True}
            rows = session.query(database_models.EventChangeLog).filter(
                database_models.EventChangeLog.created_at >= since
            ).order_by(database_models.EventChangeLog.id.asc()).limit(500).all()

            if user.is_admin:
                allowed = restricted = None
            else:
                access_map = self.get_user_access(user, session=session)
                allowed = {tid for tid, a in access_map.items()
                           if a in dto_models.available_access_names}
                restricted = {tid for tid, a in access_map.items() if a == "restricted"}

            jan1 = date(year, 1, 1) if year else None
            dec31 = date(year, 12, 31) if year else None
            updates = []
            for row in rows:
                ts = str(row.created_at)
                if row.action == "delete":
                    updates.append({"kind": row.kind, "id": row.event_id,
                                    "deleted": True, "ts": ts})
                    continue
                model = AnnualEvent if row.kind == "annual" else DailyEvent
                obj = session.get(model, row.event_id)
                if obj is None:
                    updates.append({"kind": row.kind, "id": row.event_id,
                                    "deleted": True, "ts": ts})
                    continue
                if allowed is not None and obj.type_id not in allowed:
                    updates.append({"kind": row.kind, "id": row.event_id,
                                    "deleted": True, "ts": ts})
                    continue
                if year and row.kind == "annual":
                    if obj.end_date.date() < jan1 or obj.start_date.date() > dec31:
                        continue
                mask = restricted if (restricted is not None and obj.type_id in restricted) else []
                updates.append({"kind": row.kind, "id": row.event_id,
                                "data": serialize_event(obj, mask), "ts": ts})
            return {"updates": updates, "server_time": now_s, "full_reload": False}

    def grant_access(self, type_id: int, target_user_id: int, level: str,
                       granter: database_models.User) -> dict:
        try:
            new_rank = dto_models.GROUP_ACCESS[level.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail="Unknown access level")
        with self.session_scope(commit=True) as session:
            if target_user_id == granter.id:
                raise HTTPException(status_code=400, detail="Cannot change own role")
            target = session.get(database_models.User, target_user_id)
            if not target:
                raise HTTPException(status_code=404, detail="User not found")
            if not session.get(EventType, type_id):
                raise HTTPException(status_code=404, detail="EventType not found")
            my_role = self._type_role(granter, type_id, session)
            my_rank = dto_models.GROUP_ACCESS[my_role.upper()]
            if my_rank < dto_models.GROUP_ACCESS.MANAGER:
                raise HTTPException(status_code=403, detail="Not enough access")
            if not (new_rank < my_rank or (my_role == "owner" and level == "owner")):
                raise HTTPException(status_code=403, detail="Cannot grant this level")
            if not granter.is_admin and not self._are_linked(granter.id, target_user_id, session):
                raise HTTPException(status_code=403, detail="User is not linked with you")
            row = session.get(database_models.EventTypeAccess, (target_user_id, type_id))
            if level == "none":
                if row:
                    session.delete(row)
            elif row:
                row.access_level = level
            else:
                session.add(database_models.EventTypeAccess(
                    user_id=target_user_id, type_id=type_id, access_level=level))
            return {"type_id": type_id, "user_id": target_user_id, "access_level": level}

    @staticmethod
    def _are_linked(a: int, b: int, session) -> bool:
        if a == b:
            return True
        return session.query(database_models.UserLink).filter(
            database_models.UserLink.user_id == a,
            database_models.UserLink.linked_user_id == b,
            database_models.UserLink.status == "accepted",
        ).first() is not None

    def link_request(self, target_login: str, user: database_models.User) -> dict:
        with self.session_scope(commit=True) as session:
            target = session.query(database_models.User).filter(
                database_models.User.login == target_login).first()
            if not target:
                raise HTTPException(status_code=404, detail="User not found")
            if target.id == user.id:
                raise HTTPException(status_code=400, detail="Cannot link yourself")
            existing = session.get(database_models.UserLink, (user.id, target.id))
            if existing:
                return {"status": existing.status}
            session.add(database_models.UserLink(
                user_id=user.id, linked_user_id=target.id, status="pending"))
            return {"status": "pending"}

    def link_answer(self, requester_id: int, accept: bool, user: database_models.User) -> dict:
        with self.session_scope(commit=True) as session:
            row = session.get(database_models.UserLink, (requester_id, user.id))
            if not row or row.status != "pending":
                raise HTTPException(status_code=404, detail="No pending request")
            if accept:
                row.status = "accepted"
                rev = session.get(database_models.UserLink, (user.id, requester_id))
                if rev:
                    rev.status = "accepted"
                else:
                    session.add(database_models.UserLink(
                        user_id=user.id, linked_user_id=requester_id, status="accepted"))
                return {"status": "accepted"}
            session.delete(row)
            return {"status": "declined"}

    def my_links(self, user: database_models.User) -> dict:
        with self.session_scope() as session:
            rows = session.query(database_models.UserLink).filter(
                database_models.UserLink.user_id == user.id).all()
            out = []
            for r in rows:
                u = session.get(database_models.User, r.linked_user_id)
                out.append({"user_id": r.linked_user_id,
                            "login": u.login if u else "?",
                            "status": r.status})
            return {"links": out}

    def register_request(self, telegram_id: int, login: str, name: str | None) -> dict:
        login = (login or "").strip()
        if not login or not telegram_id:
            raise HTTPException(status_code=400, detail="login and telegram_id required")
        with self.session_scope(commit=True) as session:
            if session.query(database_models.User).filter(
                    database_models.User.login == login).first():
                raise HTTPException(status_code=409, detail="Login taken")
            if session.query(database_models.User).filter(
                    database_models.User.telegram_id == telegram_id).first():
                raise HTTPException(status_code=409, detail="Telegram already registered")
            dupe = session.query(database_models.PendingUser).filter(
                database_models.PendingUser.telegram_id == telegram_id).first()
            if dupe and dupe.status == "pending":
                return {"id": dupe.id, "status": "pending"}
            if session.query(database_models.PendingUser).filter(
                    database_models.PendingUser.login == login,
                    database_models.PendingUser.status == "pending").first():
                raise HTTPException(status_code=409, detail="Login requested already")
            row = database_models.PendingUser(telegram_id=telegram_id, login=login, name=name)
            session.add(row)
            session.flush()
            return {"id": row.id, "status": "pending"}

    def pending_registrations(self) -> dict:
        with self.session_scope() as session:
            rows = session.query(database_models.PendingUser).filter(
                database_models.PendingUser.status == "pending").order_by(
                database_models.PendingUser.id.asc()).all()
            return {"pending": [
                {"id": r.id, "telegram_id": r.telegram_id, "login": r.login,
                 "name": r.name, "created_at": str(r.created_at)} for r in rows]}

    def approve_registration(self, pending_id: int, approve: bool) -> dict:
        with self.session_scope(commit=True) as session:
            row = session.get(database_models.PendingUser, pending_id)
            if not row or row.status != "pending":
                raise HTTPException(status_code=404, detail="No pending request")
            if not approve:
                row.status = "declined"
                return {"id": row.id, "status": "declined",
                        "telegram_id": row.telegram_id, "login": row.login}
            if session.query(database_models.User).filter(
                    database_models.User.login == row.login).first():
                raise HTTPException(status_code=409, detail="Login taken")
            # NOTE: plaintext, как и остальные пароли. Отдельная задача: argon2 + миграция.
            password = secrets.token_urlsafe(12)
            user = database_models.User(login=row.login, password=password,
                                        telegram_id=row.telegram_id,
                                        is_admin=False, approved=True)
            session.add(user)
            row.status = "approved"
            session.flush()
            return {"id": row.id, "status": "approved", "user_id": user.id,
                    "telegram_id": row.telegram_id, "login": row.login,
                    "password": password}

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

    def get_user_by_telegram_id(self, telegram_id, session=None) -> database_models.User | None:
        def get(_session):
            return _session.query(database_models.User).filter(
                database_models.User.telegram_id == telegram_id).first()

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_admin(self, session=None) -> database_models.User | None:
        def get(_session):
            return _session.query(database_models.User).filter(
                database_models.User.is_admin == True).first()  # noqa: E712

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_user_access(self, user: database_models.User, session=None) -> Dict[int, str]:
        def get(_session):
            access = _session.query(database_models.EventTypeAccess).filter_by(user_id=user.id).all()
            return {a.type_id: a.access_level for a in access}

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_user_editable(self, user: database_models.User, session=None) -> Set[int]:
        """Типы, в которых можно править СОБЫТИЯ: member и выше."""
        def get(_session):
            editable = session.query(EventTypeAccess).filter(
                EventTypeAccess.user_id == user.id,
                EventTypeAccess.access_level.in_(["member", "editor", "manager", "owner"])
            ).all()
            return {e.type_id for e in editable}

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def get_user_type_editable(self, user: database_models.User, session=None) -> Set[int]:
        """Типы, у которых можно править НАСТРОЙКИ (имя/цвет): editor и выше."""
        def get(_session):
            editable = session.query(EventTypeAccess).filter(
                EventTypeAccess.user_id == user.id,
                EventTypeAccess.access_level.in_(["editor", "manager", "owner"])
            ).all()
            return {e.type_id for e in editable}

        if session is None:
            with self.session_scope() as session:
                return get(session)
        return get(session)

    def _type_role(self, user: database_models.User, type_id: int, session) -> str:
        if user.is_admin:
            return "owner"
        return self.get_user_access(user, session=session).get(type_id, "none")

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
