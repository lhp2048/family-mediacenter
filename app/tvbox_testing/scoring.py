"""Score aggregation for TVBox test reports."""

from __future__ import annotations

from typing import Any

from app.tvbox_testing.types import Availability, Grade


def grade_from_score(score: int) -> Grade:
    if score >= 85:
        return "excellent"
    if score >= 60:
        return "available"
    if score >= 40:
        return "partial"
    if score > 0:
        return "failed"
    return "unknown"


def availability_from_layers(
    layers: list[dict[str, Any]],
    *,
    child_probe: dict[str, Any] | None = None,
) -> Availability:
    l1 = _layer(layers, "L1")
    if l1 and l1.get("status") == "fail":
        return "failed"
    if child_probe and child_probe.get("probed", 0) > 0:
        ok_n = child_probe.get("ok", 0)
        probed = child_probe["probed"]
        if ok_n <= 0:
            return "partial"
        if ok_n < probed:
            return "partial"
    for layer in layers:
        if layer.get("status") == "partial":
            return "partial"
    l2 = _layer(layers, "L2")
    if l2 and l2.get("status") == "fail":
        return "failed"
    if l1 and l1.get("status") == "pass":
        return "full"
    return "unknown"


def compute_total_score(layers: list[dict[str, Any]]) -> int:
    max_by_layer = {"L1": 15, "L2": 15, "L3": 15, "L4": 10, "L5": 20, "L6": 5, "L7": 5}
    active_max = sum(max_by_layer.values())
    best_by_layer: dict[str, int] = {}

    for layer in layers:
        lid = layer.get("layer")
        if lid not in max_by_layer:
            continue
        score = min(max_by_layer[lid], max(0, int(layer.get("score") or 0)))
        best_by_layer[lid] = max(best_by_layer.get(lid, 0), score)

    total = sum(best_by_layer.values())

    skipped = [layer for layer in layers if layer.get("status") == "skip"]
    if skipped:
        redistributable = sum(
            max_by_layer.get(str(layer.get("layer")), 0) for layer in skipped
        )
        if redistributable and active_max > redistributable:
            boost = int(total * (redistributable / (active_max - redistributable + 1)) * 0.15)
            total = min(100, total + boost)

    return min(100, total)


def _layer(layers: list[dict[str, Any]], layer_id: str) -> dict[str, Any] | None:
    for layer in layers:
        if layer.get("layer") == layer_id:
            return layer
    return None
