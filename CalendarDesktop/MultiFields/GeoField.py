import re
from typing import Tuple

from .BaseField import BaseField
import webbrowser

class GeoField(BaseField):
    type_name = "GEO"
    action = "open map"
    icon = "maps.png"
    @staticmethod
    def perform_type_check(value) -> Tuple[bool, int]:
        if not isinstance(value, str):
            return False, 0

        v = value.strip().lower()

        score = 0

        # ----------------------------
        # 1. lat/lon style
        # ----------------------------
        if "lat" in v and "lon" in v:
            if re.search(r"lat\s*[:=]\s*-?\d", v) and re.search(r"lon\s*[:=]\s*-?\d", v):
                return True, 90

        # ----------------------------
        # 2. decimal pair (comma)
        # ----------------------------
        match = re.match(r"^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$", v)
        if match:
            return True, 95

        # ----------------------------
        # 3. decimal pair (space separated)
        # ----------------------------
        match = re.match(r"^\s*-?\d+(\.\d+)?\s+-?\d+(\.\d+)?\s*$", v)
        if match:
            return True, 80

        # ----------------------------
        # 4. weak geo hints
        # ----------------------------
        geo_keywords = ["coord", "coordinates", "lat", "lon", "lng"]
        if any(k in v for k in geo_keywords):
            score = 40

        return False, score

    def on_action(self):
        geo = self.get_value()
        self.open_yandex_maps(geo)
        return
        url = f"https://maps.google.com/?q={geo}"
        url = f"https://yandex.com/maps/?ll={geo}"
        webbrowser.open(url)

    def open_yandex_maps(self, coords: str):
        lat, lon = [x.strip() for x in coords.split(",")]

        url = (
            f"https://yandex.ru/maps/"
            f"?ll={lon},{lat}"
            f"&pt={lon},{lat},pm2rdm"
            f"&z=16"
        )
        webbrowser.open(url)