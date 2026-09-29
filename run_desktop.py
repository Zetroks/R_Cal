"""Точка входа для PyInstaller (анализ видит только абсолютные импорты)."""

import sys

from CalendarDesktop.main import run

if __name__ == "__main__":
    sys.exit(run())
