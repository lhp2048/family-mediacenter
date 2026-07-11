"""TVBox layered test orchestrator."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select

from app.config import load_settings
from app.db import async_session
from app.models.tvbox_source import TvboxSourceORM, TvboxSourceTestResult
from app.models.tvbox_test_report import TvboxTestReportORM, TvboxTestRunORM
from app.tvbox_testing.config_parse import (
    extract_sub_urls,
    format_summary_text,
    resolve_availability,
)
from app.tvbox_testing.cms_probe import run_aggregated_cms_layers
from app.tvbox_testing.http_client import DEFAULT_HEADERS, fetch_url
from app.tvbox_testing.layers import (
    run_l1_from_fetch,
    run_l2_from_fetch,
    run_l6_metrics,
    run_l7_live,
)
from app.tvbox_testing.normalizer import build_unit_tree
from app.tvbox_testing.scoring import (
    availability_from_layers,
    compute_total_score,
    grade_from_score,
)
from app.tvbox_testing.types import TestMode


def _testing_config() -> dict[str, Any]:
    tvbox = load_settings().tvbox
    return {
        "timeout": float(tvbox.test_timeout),
        "concurrency": int(tvbox.test_concurrency),
        "max_body": int(tvbox.test_max_body_mb) * 1024 * 1024,
        "probe_children": int(tvbox.test_probe_children),
        "live_sample": int(getattr(tvbox, "test_live_sample", 3) or 3),
        "probe_sites": int(getattr(tvbox, "test_probe_sites", 3) or 3),
        "cms_search_keyword": getattr(tvbox, "test_cms_search_keyword", "电影") or "电影",
        "spider_timeout": float(getattr(tvbox, "spider_sidecar_timeout", 25) or 25),
    }


def _build_steps(layers: list[dict[str, Any]], message: str, ok: bool) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for layer in layers:
        status = layer.get("status")
        step_ok: bool | None
        if status == "pass":
            step_ok = True
        elif status in ("fail",):
            step_ok = False
        elif status == "partial":
            step_ok = None
        else:
            step_ok = None
        steps.append(
            {
                "name": layer.get("layer", "?"),
                "ok": step_ok,
                "detail": layer.get("message") or "",
                "sub": False,
            }
        )
        failed_items = (layer.get("detail") or {}).get("failed")
        if not isinstance(failed_items, list):
            failed_items = []
        for item in failed_items:
            if isinstance(item, dict):
                steps.append(
                    {
                        "name": "子源",
                        "ok": False,
                        "detail": f"{item.get('url', '')} — {item.get('message', '')}",
                        "sub": True,
                    }
                )
        for site_item in (layer.get("detail") or {}).get("sites") or []:
            if isinstance(site_item, dict) and site_item.get("status") == "fail":
                steps.append(
                    {
                        "name": site_item.get("site") or "站点",
                        "ok": False,
                        "detail": site_item.get("message") or "",
                        "sub": True,
                    }
                )
    steps.append({"name": "测试结论", "ok": ok, "detail": message, "sub": False})
    return steps


def _build_detail_payload(
    *,
    ok: bool,
    message: str,
    summary: dict[str, Any],
    layers: list[dict[str, Any]],
    units: dict[str, Any],
    score: int,
    grade: str,
    availability: str,
    mode: TestMode,
) -> dict[str, Any]:
    enriched = dict(summary)
    enriched["availability"] = availability
    enriched["score"] = score
    enriched["grade"] = grade
    enriched["mode"] = mode.value
    return {
        "steps": _build_steps(layers, message, ok),
        "layers": layers,
        "units": units,
        "summary": enriched,
    }


async def _probe_one_sub_config(
    sub_url: str,
    *,
    client: httpx.AsyncClient,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    fetch = await fetch_url(
        sub_url,
        client=client,
        timeout=cfg["timeout"],
        max_body=cfg["max_body"],
    )
    entry: dict[str, Any] = {
        "url": sub_url,
        "ok": fetch.ok,
        "message": fetch.message,
        "http_status": fetch.http_status,
        "latency_ms": fetch.latency_ms,
    }
    if fetch.ok:
        l2, sub_config, summary = await run_l2_from_fetch(fetch, sub_url)
        entry["l2_status"] = l2.get("status")
        entry["config_type"] = (summary or {}).get("type")
        entry["ok"] = l2.get("status") == "pass"
        if not entry["ok"]:
            entry["message"] = l2.get("message", fetch.message)
        elif isinstance(sub_config, dict) and (summary or {}).get("type") == "sites":
            sites = sub_config.get("sites") or sub_config.get("apis") or []
            if isinstance(sites, list):
                entry["sites"] = sites
                entry["sites_count"] = len(sites)
            spider = sub_config.get("spider")
            if spider:
                entry["spider_jar"] = str(spider)
    return entry


def _child_probe_result(
    results: list[dict[str, Any]], *, total: int
) -> dict[str, Any]:
    ok_count = sum(1 for item in results if item.get("ok"))
    failed = [
        {"url": item["url"], "message": item.get("message", "")}
        for item in results
        if not item.get("ok")
    ]
    return {
        "probed": len(results),
        "total": total,
        "ok": ok_count,
        "exhausted": len(results) >= total,
        "failed": failed[:5],
        "results": results,
    }


async def _probe_sub_configs(
    config: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    cfg: dict[str, Any],
    max_probe: int,
) -> dict[str, Any]:
    urls = extract_sub_urls(config)
    if not urls:
        return _child_probe_result([], total=0)

    batch_size = max(1, max_probe)
    results: list[dict[str, Any]] = []
    index = 0

    while index < len(urls):
        chunk = urls[index : index + batch_size]
        chunk_results = await asyncio.gather(
            *[
                _probe_one_sub_config(sub_url, client=client, cfg=cfg)
                for sub_url in chunk
            ]
        )
        results.extend(chunk_results)
        if any(item.get("ok") for item in chunk_results):
            break
        index += len(chunk)

    return _child_probe_result(results, total=len(urls))


def _apply_child_probe_to_l2(
    l2_layer: dict[str, Any], child_probe: dict[str, Any]
) -> None:
    probed = int(child_probe.get("probed") or 0)
    if probed <= 0:
        return

    ok_n = int(child_probe.get("ok") or 0)
    total = int(child_probe.get("total") or probed)
    exhausted = bool(child_probe.get("exhausted"))

    if ok_n <= 0:
        l2_layer["status"] = "partial"
        if exhausted:
            l2_layer["message"] = f"多仓根配置可用，子源均不可用（0/{total}）"
        else:
            l2_layer["message"] = f"多仓根配置可用，子源均不可用（0/{probed}）"
        l2_layer["score"] = 8
    elif ok_n < probed:
        l2_layer["status"] = "partial"
        l2_layer["message"] = f"部分子源可用（{ok_n}/{probed}）"
        l2_layer["score"] = 10
    else:
        l2_layer["status"] = "pass"
        l2_layer["message"] = f"多仓子源可用（{ok_n}/{probed}）"
        l2_layer["score"] = 15


async def _run_site_layers(
    sites: list[Any],
    *,
    client: httpx.AsyncClient,
    mode: TestMode,
    cfg: dict[str, Any],
    spider_jar: str = "",
) -> list[dict[str, Any]]:
    return await run_aggregated_cms_layers(
        sites,
        client=client,
        mode=mode,
        timeout=cfg["timeout"],
        max_body=cfg["max_body"],
        max_sites=cfg["probe_sites"],
        search_keyword=cfg["cms_search_keyword"],
        spider_jar=spider_jar,
        spider_timeout=cfg["spider_timeout"],
    )


def _merge_sites_from_child_probe(
    child_probe: dict[str, Any] | None,
    *,
    root_spider_jar: str = "",
) -> tuple[list[dict[str, Any]], str]:
    """Collect sites from successful multi-warehouse child configs."""
    if not child_probe:
        return [], root_spider_jar

    merged: list[dict[str, Any]] = []
    spider_jar = root_spider_jar
    for entry in child_probe.get("results") or []:
        if not isinstance(entry, dict) or not entry.get("ok"):
            continue
        if not spider_jar and entry.get("spider_jar"):
            spider_jar = str(entry["spider_jar"])
        for site in entry.get("sites") or []:
            if isinstance(site, dict):
                merged.append(site)
    return merged, spider_jar


async def run_source_test(
    source_id: int,
    *,
    mode: TestMode = TestMode.QUICK,
    persist: bool = True,
    run_id: Optional[int] = None,
) -> TvboxSourceTestResult:
    cfg = _testing_config()

    async with async_session() as session:
        row = await session.get(TvboxSourceORM, source_id)
        if not row:
            raise ValueError("源不存在")

        layers: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}

        async with httpx.AsyncClient(
            timeout=cfg["timeout"],
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            fetch = await fetch_url(
                row.url,
                client=client,
                timeout=cfg["timeout"],
                max_body=cfg["max_body"],
            )
            layers.append(run_l1_from_fetch(fetch))

            l2_layer, config, config_summary = await run_l2_from_fetch(fetch, row.url)
            layers.append(l2_layer)

            child_probe: dict[str, Any] | None = None
            if config and config_summary and config_summary.get("type") == "multi_warehouse":
                child_probe = await _probe_sub_configs(
                    config,
                    client=client,
                    cfg=cfg,
                    max_probe=cfg["probe_children"],
                )
                summary["child_probe"] = child_probe
                l2_detail = dict(l2_layer.get("detail") or {})
                l2_detail["child_probe"] = child_probe
                l2_layer["detail"] = l2_detail
                _apply_child_probe_to_l2(l2_layer, child_probe)
                layers[1] = l2_layer

            if config_summary:
                summary.update(config_summary)
            summary.update(fetch.to_summary())

            if config and config_summary and config_summary.get("type") == "sites":
                sites = config.get("sites") or config.get("apis") or []
                if isinstance(sites, list):
                    root_spider_jar = str(config.get("spider") or "")
                    layers.extend(
                        await _run_site_layers(
                            sites,
                            client=client,
                            mode=mode,
                            cfg=cfg,
                            spider_jar=root_spider_jar,
                        )
                    )
            elif (
                mode == TestMode.FULL
                and config
                and config_summary
                and config_summary.get("type") == "multi_warehouse"
                and child_probe
            ):
                root_spider_jar = str(config.get("spider") or "")
                merged_sites, spider_jar = _merge_sites_from_child_probe(
                    child_probe,
                    root_spider_jar=root_spider_jar,
                )
                if merged_sites:
                    summary["child_sites_count"] = len(merged_sites)
                    layers.extend(
                        await _run_site_layers(
                            merged_sites,
                            client=client,
                            mode=mode,
                            cfg=cfg,
                            spider_jar=spider_jar,
                        )
                    )

            l7 = await run_l7_live(
                config,
                fetch,
                row.url,
                client=client,
                timeout=cfg["timeout"],
                max_body=cfg["max_body"],
                sample_channels=cfg["live_sample"],
            )
            layers.append(l7)

            layers.append(run_l6_metrics(fetch, layers))

        units = build_unit_tree(row.name, row.url, config, config_summary=config_summary)

        l1_fail = layers[0].get("status") == "fail"
        l2_fail = layers[1].get("status") == "fail"
        ok = not l1_fail and not l2_fail
        message = layers[1].get("message") if not ok else format_summary_text(summary) or "可用"

        if child_probe and child_probe.get("probed", 0) > 0:
            message = layers[1].get("message") or message

        score = compute_total_score(layers)
        availability = availability_from_layers(layers, child_probe=child_probe)
        if availability == "unknown" and ok:
            availability = resolve_availability(ok, summary)  # type: ignore[assignment]
        grade = grade_from_score(score)

        detail = _build_detail_payload(
            ok=ok,
            message=message,
            summary=summary,
            layers=layers,
            units=units,
            score=score,
            grade=grade,
            availability=availability,
            mode=mode,
        )

        result = TvboxSourceTestResult(
            id=row.id,
            name=row.name,
            url=row.url,
            ok=ok,
            http_status=fetch.http_status,
            latency_ms=fetch.latency_ms,
            message=message if not ok else (format_summary_text(summary) or message),
            summary=summary,
            detail=detail,
            last_test_at=datetime.now(),
            last_test_summary=format_summary_text(summary),
        )

        if persist:
            row.last_test_at = result.last_test_at
            row.last_test_ok = ok
            row.last_test_message = message
            row.last_test_latency_ms = fetch.latency_ms
            row.last_test_summary = result.last_test_summary or ""
            row.last_test_detail = json.dumps(detail, ensure_ascii=False)
            row.last_test_score = score
            row.last_test_grade = grade

            report = TvboxTestReportORM(
                run_id=run_id,
                source_id=row.id,
                mode=mode.value,
                ok=ok,
                score=score,
                grade=grade,
                availability=availability,
                message=result.message,
                report_json=json.dumps(detail, ensure_ascii=False),
            )
            session.add(report)
            await session.commit()
            await session.refresh(row)

        return result


async def run_all_source_tests(
    *,
    mode: TestMode = TestMode.QUICK,
) -> list[TvboxSourceTestResult]:
    cfg = _testing_config()

    async with async_session() as session:
        result = await session.execute(
            select(TvboxSourceORM).order_by(TvboxSourceORM.sort_order, TvboxSourceORM.id)
        )
        rows = list(result.scalars().all())

        run = TvboxTestRunORM(mode=mode.value, source_count=len(rows), status="running")
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    if not rows:
        async with async_session() as session:
            run_row = await session.get(TvboxTestRunORM, run_id)
            if run_row:
                run_row.status = "completed"
                run_row.finished_at = datetime.now()
                await session.commit()
        return []

    sem = asyncio.Semaphore(max(1, cfg["concurrency"]))

    async def _one(source_id: int) -> TvboxSourceTestResult:
        async with sem:
            return await run_source_test(
                source_id, mode=mode, persist=True, run_id=run_id
            )

    results = await asyncio.gather(*[_one(row.id) for row in rows])

    async with async_session() as session:
        run_row = await session.get(TvboxTestRunORM, run_id)
        if run_row:
            run_row.status = "completed"
            run_row.finished_at = datetime.now()
            run_row.ok_count = sum(1 for item in results if item.ok)
            await session.commit()

    return list(results)
