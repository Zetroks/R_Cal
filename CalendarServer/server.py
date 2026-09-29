# server.py

import calendar
import os
from datetime import date
from .database import EventRepository
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import HTTPException
from fastapi import Depends
from .authorization import authenticate_user, create_access_token, get_current_user
from CalendarService import dto_models

app = FastAPI()

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CAL_CORS_ORIGINS", "http://127.0.0.1:8002,http://localhost:8002"
    ).split(",")
    if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

repo = EventRepository.get()


def date_from_iso(s: str):
    from datetime import date
    return date.fromisoformat(s)


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.login})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user.login
    }


@app.get("/me")
def read_me(current_user: dict = Depends(get_current_user)):
    return current_user


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/day")
def get_day(date: str, current_user=Depends(get_current_user)):
    try:
        d = date_from_iso(date)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    data = repo.get_events_for_day(d, current_user)

    return data


@app.get("/month")
def get_month(month: int, year: int, current_user=Depends(get_current_user)):
    try:
        start = date(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        end = date(year, month, days_in_month)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    data = repo.get_events_in_range(start, end, current_user)

    return data


@app.get("/year")
def get_year(year: int, current_user=Depends(get_current_user)):
    try:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    data = repo.get_events_in_range(start, end, current_user)

    return data


@app.get("/event_types")
def get_types(current_user=Depends(get_current_user)):
    data = repo.get_all_type_colors(current_user)
    return data


@app.get("/my_access")
def get_my_access(current_user=Depends(get_current_user)):
    data = repo.get_front_user_access(current_user)
    return data


@app.post("/event")
def upsert_event(dto: dto_models.EventUpsertDTO, current_user=Depends(get_current_user)):
    if dto.is_deleted:
        return repo.delete_event(dto, current_user)
    else:
        if dto.id is None:
            return repo.create_event(dto, current_user)
        else:
            return repo.update_event(dto, current_user)


@app.post("/event_type")
def upsert_event_type(dto: dto_models.EventTypeUpsertDTO, current_user=Depends(get_current_user)):
    return repo.update_event_type(dto, current_user)


@app.post("/sync_group")
def sync_group(dto: dto_models.SyncGroupDTO, current_user=Depends(get_current_user)):
    return repo.sync_group_to_google(dto.type_id, current_user)


@app.get("/google_calendars")
def google_calendars(current_user=Depends(get_current_user)):
    return repo.get_google_calendars()


@app.get("/updates")
def get_updates(since: str = "", year: int = 0, current_user=Depends(get_current_user)):
    return repo.get_updates(since, year, current_user)
