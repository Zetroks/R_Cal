"""OAuth2 для Google Calendar API (installed app).

Первичная авторизация выполняется человеком в браузере:
    .\\.venv\\Scripts\\python.exe -m CalendarServer.google_auth
Откроется Google consent screen, после согласия токен сохранится в
CalendarServer/.google_token.json (в git не попадает, см. .gitignore).

Файл client_secret получается в Google Cloud Console
(APIs & Services -> Credentials -> OAuth client ID -> Desktop app).
Путь к нему по умолчанию CalendarServer/.google_client_secret.json,
переопределяется env GOOGLE_CLIENT_SECRET_FILE.
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",  # calendarList/discovery
    "https://www.googleapis.com/auth/calendar.events",  # CRUD событий
]

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRET_FILE", str(BASE_DIR / ".google_client_secret.json")
)
TOKEN_FILE = os.environ.get(
    "GOOGLE_TOKEN_FILE", str(BASE_DIR / ".google_token.json")
)


def get_credentials() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def get_service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=get_credentials())


def main():
    service = get_service()
    cal_list = service.calendarList().list().execute()
    print("CALENDARS:")
    for c in cal_list.get("items", []):
        print(f"  {c.get('summary')} id={c.get('id')} primary={c.get('primary', False)}")


if __name__ == "__main__":
    main()
