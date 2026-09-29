import re
import webbrowser
from typing import Tuple
from urllib.parse import urlparse

from .BaseField import BaseField


class UrlField(BaseField):
    type_name = "URL"
    action = "open web page"
    icon = "browser.png"
    @staticmethod
    def perform_type_check(value) -> Tuple[bool, int]:
        if not isinstance(value, str):
            return False, 0

        v = value.strip()

        if not v:
            return False, 0
        score = 0

        # ----------------------------
        # 1. full URL with scheme
        # ----------------------------
        if re.match(r"^https?://", v):
            return True, 100

        # ----------------------------
        # 2. www.*
        # ----------------------------
        if re.match(r"^www\.", v):
            return True, 90

        # ----------------------------
        # 3. domain-like (example.com, sub.domain.com)
        # ----------------------------
        domain_pattern = r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(/[^\s]*)?$"
        if re.match(domain_pattern, v):
            return True, 85

        # ----------------------------
        # 4. weak hints
        # ----------------------------
        url_keywords = ["http", "www", ".com", ".net", ".org", ".io"]
        if any(k in v.lower() for k in url_keywords):
            score = 40

        return False, score

    def on_action(self):
        url = self.get_value()
        if url:
            webbrowser.open(url)