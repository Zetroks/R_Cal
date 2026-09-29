#!/bin/sh
# Linux VDS: run from repo root. Configure via .env (see .env.example).
cd "$(dirname "$0")"
exec ./.venv/bin/python -m CalendarServer.main
