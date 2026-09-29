from pydantic import BaseModel, Field, PrivateAttr
from typing import List, Dict, Iterator, Any, TypeAlias, Callable, Tuple
from calendar import monthrange
from datetime import timedelta, date, datetime

from CalendarService.dto_models import GROUP_ACCESS

AccessResolver = Callable[["BaseEvent"], GROUP_ACCESS]
GroupAccessResolver = Callable[["EventType"], GROUP_ACCESS]

def date_iterator_iso(start_iso: str, end_iso: str) -> Iterator[date]:
    return date_iterator(date.fromisoformat(start_iso), date.fromisoformat(end_iso))

def date_iterator(start_date: date, end_date: date) -> Iterator[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


class EventGroup(BaseModel):
    __access_resolver__ : GroupAccessResolver | None = None
    _access_cache       :GROUP_ACCESS | None    = PrivateAttr(default=None)
    id          :int | None     = None
    name        :str
    color       :str
    version     :int            = -1
    google_calendar_id  :str | None  = None
    google_color_id     :str | None  = None
    google_visibility   :str | None  = None
    google_sync_enabled :bool        = False

    @classmethod
    def set_access_resolver(cls, resolver: GroupAccessResolver) -> None:
        cls.__access_resolver__ = resolver

    def get_access(self) -> GROUP_ACCESS:
        if self._access_cache is not None:
            return self._access_cache

        if self.__class__.__access_resolver__ is None:
            raise RuntimeError("Access resolver is not set")

        self._access_cache = self.__class__.__access_resolver__(self)
        return self._access_cache

class BaseEvent(BaseModel):
    __access_resolver__ : AccessResolver | None = None
    _access_cache       :GROUP_ACCESS | None    = PrivateAttr(default=None)
    event_type          :str                    = "invalid"
    id                  :int | None             = None
    version             :int                    = -1
    sync_id             :int | None             = None  # immutable
    is_deleted          :bool                   = False
    title               :str
    type_id             :int

    @classmethod
    def set_access_resolver(cls, resolver: AccessResolver) -> None:
        cls.__access_resolver__ = resolver

    def get_access(self) -> GROUP_ACCESS:
        if self._access_cache is not None:
            return self._access_cache

        if self.__class__.__access_resolver__ is None:
            raise RuntimeError("Access resolver is not set")

        self._access_cache = self.__class__.__access_resolver__(self)
        return self._access_cache

    def invalidate_access(self):
        self._access_cache = None

    # noinspection PyMethodMayBeStatic
    def getDatetimeRange(self, current:date) -> Tuple[datetime, datetime]:
        raise NotImplementedError

    def __eq__(self, other) -> bool:
        if isinstance(other, BaseEvent):
            return self.__class__ == other.__class__ and self.id == other.id
        return False

class AnnualEvent(BaseEvent):
    event_type  :str        = "annual"
    url         :str | None = None
    start_date  :datetime
    end_date    :datetime

    def getDatetimeRange(self, current:date) -> Tuple[datetime, datetime]:
        # st =  self.start_date < current
        return self.start_date, self.end_date




class DailyEvent(BaseEvent):
    event_type  :str        = "daily"
    day         :int
    month       :int

    def getDatetimeRange(self, current:date) -> Tuple[datetime, datetime]:
        return  (
            datetime(current.year, self.month, self.day, 0),
            datetime(current.year, self.month, self.day, 23)
        )


class DayEvents(BaseModel):
    daily       :List[DailyEvent]  = Field(default_factory=list)
    annual      :List[AnnualEvent] = Field(default_factory=list)

class MonthEvents(BaseModel):
    Days        :Dict[int, DayEvents] = Field(default_factory=dict)
    Year        :int
    Month       :int

    def model_post_init(self, context: Any, /) -> None:
        _, num_days = monthrange(self.Year, self.Month)
        for i in range(num_days):
            day = self.Days.get(i+1, None)
            if day is None:
                self.Days[i+1] = DayEvents()

class YearEvents(BaseModel):
    Months      :Dict[int, MonthEvents] = Field(default_factory=dict)
    Events      :Dict[date, DayEvents] = Field(default_factory=dict)
    Year        :int

    def model_post_init(self, context: Any, /) -> None:
        for i in range(12):
            month = self.Months.get(i+1, None)
            if month is None:
                self.Months[i+1] = MonthEvents(Year = self.Year, Month = i + 1)

        for d in date_iterator(date(self.Year, 1, 1), date(self.Year, 12, 31)):
            day = self.Events.get(d, None)
            if day is None:
                self.Events[d] = self.Months[d.month].Days[d.day]


EventModel: TypeAlias = DailyEvent | AnnualEvent