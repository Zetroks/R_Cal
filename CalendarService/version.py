"""Версии протокола и сборок. Формат ГГГГ.ММ.ДД[.N], сравнение строками.

PROTOCOL — контракт API. Меняется ТОЛЬКО при ломающих изменениях
(руками через bump_version.py --protocol).
BUILD — дата+счётчик каждой сборки (bump_version.py).
"""

PROTOCOL = "2026.09.29"
BUILD = "2026.09.29.1"


def is_compatible(client_protocol: str, min_protocol: str) -> bool:
    """Клиент совместим, если его протокол не старше минимального."""
    return (client_protocol or "") >= (min_protocol or "")
