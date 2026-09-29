import copy
from typing import Dict, List, Iterator, Set
from CalendarService import dto_models
from enum import Enum
from CalendarService import models
from CalendarService.dto_models import GROUP_ACCESS
from CalendarService.models import EventGroup, YearEvents


class cache:
    __instance__ = None
    year_data: Dict[int, models.YearEvents] = {}
    _original_year_data_: Dict[int, models.YearEvents] = {}
    groups: List[models.EventGroup]
    group_id2groups = Dict[int, models.EventGroup]
    # _editable_types: List[int] = []
    _group_access: Dict[int, dto_models.GROUP_ACCESS] = {}
    __reference_year__:models.YearEvents = None
    _is_admin: bool = False

    @classmethod
    def get(cls):
        if cls.__instance__ is None:
            cls.__instance__ = cls()
        return cls.__instance__

    def SetGroups(self, types: List[models.EventGroup]):
        self.groups = types
        self.group_id2groups = {v.id: v for v in types}

    def SetAccess(self, access: dict):
        if access.get("IsAdmin", False):
            self._is_admin = True
            return
        for k, v in access.items():
            self._group_access[int(k)] = dto_models.GROUP_ACCESS(v)

    # resolver for models
    def GetEventAccess(self, event: models.BaseEvent) -> dto_models.GROUP_ACCESS:
        if self._is_admin:
            return dto_models.GROUP_ACCESS.OWNER
        return self._group_access[event.type_id]

    # resolver for models
    def GetGroupAccess(self, group: models.EventGroup) -> dto_models.GROUP_ACCESS:
        if self._is_admin:
            return dto_models.GROUP_ACCESS.OWNER
        return self._group_access[group.id]

    def has_editable_groups(self) -> bool:
        for group in self.groups_iterator():
            if group.get_access() >= GROUP_ACCESS.EDITOR:
                return True
        return False

    def groups_iterator(self) -> Iterator[models.EventGroup]:
        for group in self.groups:
            yield group

    def get_event_group(self, event: models.BaseEvent) -> models.EventGroup:
        return self.group_id2groups.get(event.type_id)

    def set_year_data(self, year: int, year_data:YearEvents) -> None:
        if self.__reference_year__ is None:
            self.__reference_year__ = year_data
        else:
            for event_day, event in self.__reference_year__.Events.items():
                target = year_data.Events.get(event_day)
                if target is None:
                    continue
                target.daily = event.daily
                month = year_data.Months.get(event_day.month)
                if month is not None and event_day.day in month.Days:
                    month.Days[event_day.day].daily = event.daily

        self.year_data[year] = year_data
        self._original_year_data_[year] = copy.deepcopy(year_data)
