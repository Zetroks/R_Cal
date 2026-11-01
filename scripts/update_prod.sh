#!/bin/sh
# Обновление прод-сервера. Выполняется ботом (/update) или руками на VDS.
# Каталог репо = родитель scripts/. Нужны user-юниты calendar-server/calendar-web.
set -e
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus
cd "$(dirname "$0")/.."

echo "== git pull =="
BEFORE=$(git rev-parse --short HEAD)
git pull --ff-only
AFTER=$(git rev-parse --short HEAD)
echo "was $BEFORE now $AFTER"

if [ "$BEFORE" != "$AFTER" ] && git diff --name-only "$BEFORE" "$AFTER" | grep -q requirements; then
    echo "== pip install =="
    ./.venv/bin/python -m pip install -r requirements-server.txt
fi

for svc in calendar-server calendar-web; do
    echo "== restart $svc =="
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart "$svc"
done

echo "== health check =="
./.venv/bin/python scripts/check_health.py

echo UPDATE_DONE
