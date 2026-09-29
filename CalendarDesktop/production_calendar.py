import json
import os.path
from calendar import monthrange
import requests

from enum import Enum

from .AppStorage import AppStorage


class DayType(str, Enum):
    WORKING = "WORKING"
    SHORT = "SHORT"
    HOLIDAY = "HOLIDAY"


class ProductionCalendar:
    __Calendars__ = {}

    def __init__(self, year: int):
        self.year = year
        self.data = self.get_calendar(year)

    def GetDayData(self, day: int, month: int) -> DayType:
        month = str(month)
        day = str(day)
        if month in self.data:
            if day in self.data[month]:
                return DayType(self.data[month][day])
        return DayType.WORKING

    @classmethod
    def get(cls, year: int):
        cal = cls.__Calendars__.get(year, None)
        if cal is None:
            cal = cls(year)
            cls.__Calendars__[year] = cal
        return cal

    @staticmethod
    def reformat_calendar(calendar):
        ret = {}
        for month in calendar["months"]:
            month_idx = month["month"]
            month["days"] = [v for v in month["days"].split(",")]
            ret[month_idx] = {}
            for day in range(monthrange(calendar["year"], month_idx)[1]):
                day = day + 1
                ret[month_idx][day] = DayType.WORKING.value
                for c_day in month["days"]:
                    if c_day == f"{day}":
                        ret[month_idx][day] = DayType.HOLIDAY.value
                    elif c_day == f"{day}+":
                        ret[month_idx][day] = DayType.HOLIDAY.value
                    elif c_day == f"{day}*":
                        ret[month_idx][day] = DayType.SHORT.value
        return ret

    def get_calendar(self, year: int):
        path = AppStorage().get_calendar_path(year)
        if os.path.isfile(path):
            calendar = json.load(open(path))
            return calendar

        url = "https://xmlcalendar.ru/data/ru/{year}/calendar.json"
        url = url.format(year=year)

        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            data = self.reformat_calendar(data)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, sort_keys=True, ensure_ascii=False)  # type: ignore
            return data
        return {}


def main():
    calendar = ProductionCalendar.get(2026)
    calendar.GetDayData(1, 1)
    pass


if __name__ == '__main__':
    main()
