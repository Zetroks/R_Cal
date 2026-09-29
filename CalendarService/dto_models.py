from datetime import datetime
from enum import StrEnum, Enum
from pydantic import BaseModel
from typing import Literal

from CalendarService.AccessEnum import AccessEnum


class EventUpsertDTO(BaseModel):
    action      : Literal["upsert", "delete"]
    id          : int | None                = None
    kind        : Literal["annual", "daily"]
    title       : str
    start_date  : datetime | None           = None
    end_date    : datetime | None           = None
    day         : int | None                = None
    month       : int | None                = None
    url         : str | None                = None
    type_id     : int
    version     : int
    is_deleted  : bool                      = False




class GROUP_ACCESS(AccessEnum):
    OWNER = ("owner", 5)
    EDITOR = ("editor", 4)
    MEMBER = ("member", 3)
    VIEWER = ("viewer", 2)
    RESTRICTED = ("restricted", 1)
    NONE = ("none", 0)
    # "none" - has no access to type or any events with this type
    # "restricted" - has VIEW access to events with this type, but some fields not available
    # "viewer" - has VIEW access to events with this type
    # "member" - has EDIT access to events with this type
    # "editor" - has full access + access to edit type. aka name and color
    # "owner" - has editor access and can set other roles for that type


available_access_names = [k.value for k in GROUP_ACCESS if k != GROUP_ACCESS.NONE]


class EventTypeUpsertDTO(BaseModel):
    id                  : int
    name                : str | None    = None
    color               : str | None    = None
    google_calendar_id  : str | None    = None
    google_color_id     : str | None    = None
    google_visibility   : str | None    = None
    google_sync_enabled : bool | None   = None


class SyncGroupDTO(BaseModel):
    type_id: int

