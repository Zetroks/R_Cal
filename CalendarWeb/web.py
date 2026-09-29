"""Веб-клиент календаря (отдельный процесс, vanilla JS без сборки).

Запуск из корня репо:
    .\\.venv\\Scripts\\python.exe -m CalendarWeb.web
Порт: CAL_WEB_PORT (по умолчанию 8002).
URL API вводит пользователь на экране входа (как в десктоп-клиенте),
поэтому здесь только раздача статики. CORS на стороне CalendarServer.
"""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CalendarWeb")


@app.get("/app-version")
def app_version():
    from CalendarService import version as cal_version

    return {"protocol": cal_version.PROTOCOL, "build": cal_version.BUILD}


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main():
    port = int(os.environ.get("CAL_WEB_PORT", "8002"))
    uvicorn.run("CalendarWeb.web:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
