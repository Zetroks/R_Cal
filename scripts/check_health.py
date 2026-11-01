"""Validate the running API and web after an update; exit nonzero on failure."""
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from CalendarService.version import BUILD, PROTOCOL


def check_once(api_port, web_port):
    def read(url):
        with urlopen(url, timeout=3) as response:
            return json.load(response)
    base = f"http://127.0.0.1:{api_port}"
    if read(base + "/").get("status") != "ok":
        raise RuntimeError("API status is not ok")
    for url in (base + "/version", f"http://127.0.0.1:{web_port}/app-version"):
        info = read(url)
        if info.get("build") != BUILD or info.get("protocol") != PROTOCOL:
            raise RuntimeError(f"Unexpected version at {url}: {info}")


def main():
    load_dotenv(ROOT / ".env")
    api_port = int(os.environ.get("CAL_SERVER_PORT", "8001"))
    web_port = int(os.environ.get("CAL_WEB_PORT", "8002"))
    for attempt in range(15):
        try:
            check_once(api_port, web_port)
        except Exception as exc:
            print(f"Health check {attempt + 1}/15 failed: {exc}", flush=True)
            if attempt < 14:
                time.sleep(2)
        else:
            print(f"API and web OK, build {BUILD}")
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
