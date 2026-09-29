# Calendar/MultiFields/loader.py
import importlib
import pkgutil
from ... import MultiFields


def load_all_fields():
    package = MultiFields

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_"):
            continue

        importlib.import_module(f"{package.__name__}.{module_name}")