import os

import requests
from CalendarService import models

from datetime import date
from typing import List


def get_server_url() -> str:
    return os.environ.get("CAL_SERVER_URL", "http://127.0.0.1:8001").rstrip("/")


class EventRepository:
    DATABASE_URL = get_server_url()
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if hasattr(self, "_ready"):
            return
        self.access_token = None
        self.session = requests.Session()
        self._ready = True
        self.username = None
        self.password = None

        user = "Roksi"
        self.username = {
            "TestUser": "TestUser",
            "Roksi": "Roksi",
            "guest": "guest"
        }.get(user)
        self.password = {
            "TestUser": "TestUser",
            "Roksi": "***REMOVED***",
            "guest": "guest"
        }.get(user)

    def login(self, username, password):
        self.username = username
        self.password = password

        res = self.session.post(
            f"{self.DATABASE_URL}/login",
            data={
                "username": username,
                "password": password
            }
        )
        res.raise_for_status()
        self.access_token = res.json()["access_token"]

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}"
        }

    def _handle_401(self, method, path, **kwargs):
        print("Token expired → relogin")

        self.login(self.username, self.password)

        return self.session.request(
            method,
            f"{self.DATABASE_URL}{path}",
            headers=self._headers(),
            **kwargs
        )

    def GET(self, endpoint, **args) -> dict:
        response = self.session.get(self.DATABASE_URL + endpoint, params=args, headers=self._headers())
        if response.status_code == 401:
            return self._handle_401("GET", endpoint, **args).json()
        return response.json()

    def POST(self, endpoint, **args) -> dict:
        response = self.session.post(
            self.DATABASE_URL + endpoint,
            headers=self._headers(),
            **args
        )
        if response.status_code == 401:
            return self._handle_401("POST", endpoint, **args).json()
        if response.status_code == 403:  # Not enough access
            return {"status": "403"}
        return response.json()

    def day(self, _date: date) -> models.DayEvents:
        return models.DayEvents(**self.GET("/day", date=_date.isoformat()))

    def year(self, year: int) -> models.DayEvents:
        return models.DayEvents(**self.GET("/year", year=year))

    def event_types(self) -> List[models.EventGroup]:
        return [models.EventGroup(**v) for v in self.GET("/event_types").get("event_types", [])]

    def get_events_for_day(self, d: date) -> models.DayEvents:
        return self.day(d)

    def get_events_for_year(self, year: int) -> models.YearEvents:
        events = self.year(year)
        ret = models.YearEvents(Year=year)
        for event in events.daily:
            ret.Months[event.month].Days[event.day].daily.append(event)
        for event in events.annual:
            for d in models.date_iterator(event.start_date, event.end_date):
                ret.Months[d.month].Days[d.day].annual.append(event)
        return ret

    def get_all_type_colors(self) -> List[models.EventGroup]:
        return self.event_types()

    def get_my_access(self) -> dict:
        return self.GET("/my_access")
