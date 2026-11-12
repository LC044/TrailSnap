"""Versioned built-in categories. Shared category names have one identity."""

import json
from pathlib import Path
from functools import lru_cache

CATALOG_PATH = Path(__file__).with_name("clip_catalog.json")


@lru_cache(maxsize=1)
def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
