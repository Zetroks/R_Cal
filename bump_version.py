"""Ручной бамп версий. Запуск из корня репо:
    .\\.venv\\Scripts\\python.exe bump_version.py          # новая сборка
    .\\.venv\\Scripts\\python.exe bump_version.py --protocol  # + ломающий контракт
"""

import re
import sys
from datetime import date
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent / "CalendarService" / "version.py"


def main():
    bump_protocol = "--protocol" in sys.argv
    text = VERSION_FILE.read_text(encoding="utf-8")
    today = date.today().strftime("%Y.%m.%d")

    def get(name):
        m = re.search(rf'^{name}\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else ""

    def set_ver(name, value):
        nonlocal text
        text = re.sub(rf'^{name}\s*=\s*"[^"]+"', f'{name} = "{value}"', text, flags=re.M)

    if bump_protocol:
        set_ver("PROTOCOL", today)
        print(f"PROTOCOL -> {today} (ломающий контракт, клиенты старше отвалятся)")

    build = get("BUILD")
    m = re.match(r"^(\d{4}\.\d{2}\.\d{2})(?:\.(\d+))?$", build)
    if m and m.group(1) == today:
        new_build = f"{today}.{int(m.group(2) or 0) + 1}"
    else:
        new_build = f"{today}.1"
    set_ver("BUILD", new_build)
    VERSION_FILE.write_text(text, encoding="utf-8")
    print(f"BUILD -> {new_build}")


if __name__ == "__main__":
    main()
