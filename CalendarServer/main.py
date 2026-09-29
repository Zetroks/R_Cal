import os

import uvicorn


def main():
    host = os.environ.get("CAL_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("CAL_SERVER_PORT", "8001"))
    reload = os.environ.get("CAL_SERVER_RELOAD", "1") == "1"

    uvicorn.run(
        "CalendarServer.server:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=["CalendarServer", "CalendarService"],
        log_config="CalendarServer/log.ini",
    )


if __name__ == "__main__":
    main()
