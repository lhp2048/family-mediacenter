import json
from functools import lru_cache

from app.config import PROJECT_ROOT

MANIFEST_PATH = PROJECT_ROOT / "family-product.json"


@lru_cache(maxsize=1)
def get_product_version() -> str:
    if not MANIFEST_PATH.is_file():
        return "dev"
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "dev"
    return str(data.get("version") or "dev")
