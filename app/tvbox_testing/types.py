from enum import Enum
from typing import Any, Literal

LayerId = Literal["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
LayerStatus = Literal["pass", "fail", "skip", "partial", "pending"]
Availability = Literal["full", "partial", "failed", "unknown"]
Grade = Literal["excellent", "available", "partial", "failed", "unknown"]


class TestMode(str, Enum):
    QUICK = "quick"
    FULL = "full"


class UnitType(str, Enum):
    SOURCE = "source"
    CONFIG = "config"
    SUB_CONFIG = "sub_config"
    SITE = "site"
    LIVE_GROUP = "live_group"
    LIVE_CHANNEL = "live_channel"


def layer_result(
    layer: LayerId,
    status: LayerStatus,
    *,
    message: str = "",
    score: int = 0,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "layer": layer,
        "status": status,
        "message": message,
        "score": score,
        "detail": detail or {},
    }
