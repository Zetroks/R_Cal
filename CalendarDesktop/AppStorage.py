from pathlib import Path


class AppStorage:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, app_name="Calendar"):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.app_name = app_name

        # базовая папка приложения (рядом с кодом или в user folder)
        self.base_dir = self._get_base_dir()

        self.data_dir = self.base_dir / "data"
        self.calendars_dir = self.data_dir / "calendars"
        # self.cache_dir = self.data_dir / "cache"
        # self.db_path = self.data_dir / "calendar.db"
        self.icons_dir = self.data_dir / "icons"

        self._ensure_dirs()

    # noinspection PyMethodMayBeStatic
    def _get_base_dir(self) -> Path:
        return Path(__file__).resolve().parent
        # after install:
        # return Path.home() / f".{self.app_name.lower()}"

    def _ensure_dirs(self):
        self.data_dir.mkdir(exist_ok=True, parents=True)
        self.calendars_dir.mkdir(exist_ok=True, parents=True)
        # self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.icons_dir.mkdir(exist_ok=True, parents=True)


    def get_calendar_path(self, year: int) -> Path:
        return self.calendars_dir / f"calendar_{year}.json"

    # def save_calendar(self, year: int, data: dict):
    #     path = self.get_calendar_path(year)
    #     path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    #
    # def load_calendar(self, year: int) -> dict:
    #     path = self.get_calendar_path(year)
    #     if not path.exists():
    #         return {}
    #     return json.loads(path.read_text(encoding="utf-8"))

    def get_icon_path(self, icon: str) -> Path:
        return self.icons_dir / icon

    # def get_db_path(self) -> Path:
    #     return self.db_path