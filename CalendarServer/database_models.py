from sqlalchemy import (
    Column, Integer, String, ForeignKey, Boolean, DateTime
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from typing import TypeAlias

Base = declarative_base()


class EventType(Base):
    __tablename__ = "event_types"
    __serializable__ = ["id", "name", "color", "version"]
    __restricted__ = []
    id = Column(Integer, primary_key=True)
    name = Column(String)
    color = Column(String)
    version = Column(Integer, default=0, server_default="0", nullable=False)
    updated_by = Column(String)
    # --- Google Calendar sync (per-category settings) ---
    google_calendar_id = Column(String, nullable=True)
    google_color_id = Column(String, nullable=True)
    google_visibility = Column(String, nullable=True)  # default/public/private
    google_sync_enabled = Column(Boolean, default=False, server_default="0", nullable=False)


class AnnualEvent(Base):
    __tablename__ = "annual_events_new"
    __serializable__ = ["id", "title", "start_date", "end_date", "url", "version", "type_id"]
    __restricted__ = ["title", "url"]
    id = Column(Integer, primary_key=True)
    title = Column(String)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    url = Column(String)
    type_id = Column(Integer, ForeignKey("event_types.id"))

    type = relationship("EventType")
    version = Column(Integer, default=0, server_default="0", nullable=False)
    updated_by = Column(String)
    updated_at = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now()
    )
    google_event_id = Column(String, nullable=True, index=True)


class DailyEvent(Base):
    __tablename__ = "daily_events"
    __serializable__ = ["id", "title", "day", "month", "version", "type_id"]
    __restricted__ = ["title"]
    id = Column(Integer, primary_key=True)
    title = Column(String)
    day = Column(Integer)
    month = Column(Integer)
    type_id = Column(Integer, ForeignKey("event_types.id"))

    type = relationship("EventType")
    version = Column(Integer, default=0, server_default="0", nullable=False)
    updated_by = Column(String)
    updated_at = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now()
    )
    google_event_id = Column(String, nullable=True, index=True)


class DailyEventHistory(Base):
    __tablename__ = "daily_event_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, index=True)  # связь с оригиналом
    title = Column(String)
    day = Column(Integer)
    month = Column(Integer)
    version = Column(Integer)
    updated_at = Column(DateTime)
    updated_by = Column(String)


class AnnualEventHistory(Base):
    __tablename__ = "annual_event_history_new"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, index=True)  # связь с оригиналом
    title = Column(String)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    url = Column(String)
    version = Column(Integer, default=0, server_default="0", nullable=False)
    updated_at = Column(DateTime)
    updated_by = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)
    password = Column(String)

    is_admin = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)


class EventTypeAccess(Base):
    __tablename__ = "user_event_type_access"
    __serializable__ = ["type_id", "access_level"]
    __restricted__ = []

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    type_id = Column(Integer, ForeignKey("event_types.id"), primary_key=True)

    access_level = Column(String)  # "none", "restricted", "full", "editor", "owner"
    # "none" - has no access to type or any events with this type
    # "restricted" - has access to events with this type, but some fields not available
    # "full" - has full access to events with this type
    # "editor" - has full access + access to edit type. aka name and color
    # "owner" - has editor access and can set other roles for that type


class UserCanEdit(Base):
    __tablename__ = "user_can_edit_types"
    __serializable__ = ["type_id"]
    __restricted__ = []

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    type_id = Column(Integer, ForeignKey("event_types.id"), primary_key=True)


EventModel: TypeAlias = DailyEvent | AnnualEvent
AnyEventModel: TypeAlias = DailyEvent | AnnualEvent | EventType | UserCanEdit | EventTypeAccess
