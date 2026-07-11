"""Discover datacenter via portal and register home cards."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import IntegrationSettings, load_settings

logger = logging.getLogger(__name__)

OWNER_SERVICE = "mediacenter"

# mediacenter 可向 datacenter 注册的首页卡片（扩展时在此追加）。
MEDIACENTER_REGISTERABLE_HOME_CARDS: list[dict[str, Any]] = [
    {
        "cardId": "ebook",
        "title": "电子图书",
        "subtitle": "家庭书库 · 在线阅读",
        "ownerService": OWNER_SERVICE,
        "discoveryKey": OWNER_SERVICE,
        "previewPath": "/api/v1/home/cards/ebook",
        "detailRoute": "/ebook",
        "sortOrder": 9,
        "enabled": True,
        "registeredBy": OWNER_SERVICE,
    },
]


def list_registerable_home_cards() -> list[dict[str, Any]]:
    return [dict(item) for item in MEDIACENTER_REGISTERABLE_HOME_CARDS]


def get_registerable_home_card(card_id: str) -> dict[str, Any] | None:
    cid = (card_id or "").strip().lower()
    for item in MEDIACENTER_REGISTERABLE_HOME_CARDS:
        if item["cardId"] == cid:
            return dict(item)
    return None


def _normalize_api_v1_base(raw: str) -> str:
    base = (raw or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def _portal_origin(portal_url: str) -> str:
    raw = (portal_url or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


async def discover_datacenter_api_base(integration: IntegrationSettings) -> str | None:
    direct = _normalize_api_v1_base(integration.datacenter_api_base)
    if direct:
        return direct
    origin = _portal_origin(integration.portal_url)
    if not origin:
        return None
    url = f"{origin}/api/v1/portal/services"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            res.raise_for_status()
            body = res.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("portal discovery failed: %s", e)
        return None
    if not isinstance(body, dict) or body.get("ok") is not True:
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    services = data.get("services")
    if not isinstance(services, dict):
        return None
    dc = services.get("datacenter")
    if not isinstance(dc, dict):
        return None
    api_base = dc.get("apiBaseUrl")
    if not isinstance(api_base, str) or not api_base.strip():
        return None
    return _normalize_api_v1_base(api_base)


async def _datacenter_request_headers(
    integration: IntegrationSettings,
) -> tuple[str | None, dict[str, str]]:
    _strip_integration(integration)
    api_base = await discover_datacenter_api_base(integration)
    if not api_base:
        return None, {}
    key = integration.datacenter_api_key
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    return api_base, headers


def _strip_integration(integration: IntegrationSettings) -> None:
    integration.portal_url = (integration.portal_url or "").strip()
    integration.datacenter_api_base = (integration.datacenter_api_base or "").strip()
    integration.datacenter_api_key = (integration.datacenter_api_key or "").strip()


def _extract_error_detail(res: httpx.Response) -> str:
    detail = (res.text or "").strip()
    try:
        payload = res.json()
        if isinstance(payload, dict):
            msg = payload.get("message") or payload.get("detail")
            if isinstance(msg, list):
                parts: list[str] = []
                for item in msg:
                    if not isinstance(item, dict):
                        continue
                    loc = ".".join(str(x) for x in item.get("loc", []))
                    text = item.get("msg") or item.get("message") or ""
                    parts.append(f"{loc}: {text}".strip(": "))
                msg = "; ".join(p for p in parts if p)
            if msg:
                detail = str(msg).strip()
    except ValueError:
        pass
    if detail:
        return f"HTTP {res.status_code}: {detail}"
    return f"HTTP {res.status_code}"


def _build_subsystem_register_payload(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardId": card["cardId"],
        "title": card.get("title") or card["cardId"],
        "subtitle": card.get("subtitle") or "",
        "ownerService": card.get("ownerService") or OWNER_SERVICE,
        "discoveryKey": card.get("discoveryKey") or card.get("ownerService") or OWNER_SERVICE,
        "previewPath": card.get("previewPath") or "",
        "detailRoute": card.get("detailRoute") or "",
        "sortOrder": int(card.get("sortOrder", 0)),
        "enabled": bool(card.get("enabled", True)),
        "registeredBy": card.get("registeredBy") or OWNER_SERVICE,
    }


def _unwrap_datacenter_data(body: Any) -> dict[str, Any]:
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    if isinstance(body, dict):
        return body
    return {}


def _friendly_status_error(status_code: int, detail: str) -> str:
    text = detail or f"HTTP {status_code}"
    if status_code == 401:
        return (
            f"{text}。"
            "请确认使用的是 Datacenter Admin 中 mediacenter 客户端的 Key（subsystem.register）。"
            "若注册已成功但刷新仍 401，请升级 datacenter 至最新版，"
            "或在 Admin 为 mediacenter 密钥临时勾选 read 权限。"
        )
    return text


async def _probe_datacenter_register_scope(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
) -> bool:
    """旧版 datacenter 的 status GET 可能要求 read；用 ping 验证 register 密钥是否有效。"""
    try:
        res = await client.get(f"{api_base}/subsystems/ping", headers=headers)
        return res.status_code < 400
    except httpx.HTTPError:
        return False


async def fetch_home_card_registration_status(
    integration: IntegrationSettings,
    card_id: str,
) -> dict[str, Any]:
    card = get_registerable_home_card(card_id)
    if not card:
        return {"ok": False, "error": f"未知卡片: {card_id}"}

    api_base, headers = await _datacenter_request_headers(integration)
    if not api_base:
        return {"ok": False, "error": "无法发现 datacenter 地址"}

    owner = card.get("ownerService") or OWNER_SERVICE
    url = f"{api_base}/subsystems/home-cards/{card['cardId']}/status"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url, params={"ownerService": owner}, headers=headers)
    if res.status_code >= 400:
        return {
            "ok": False,
            "error": f"查询状态失败: {_extract_error_detail(res)}",
            "statusCode": res.status_code,
        }
    try:
        data = _unwrap_datacenter_data(res.json())
    except ValueError:
        data = {}
    return {"ok": True, "status": data}


async def list_home_card_registry(integration: IntegrationSettings) -> dict[str, Any]:
    api_base, headers = await _datacenter_request_headers(integration)
    if not api_base:
        return {
            "ok": False,
            "error": "请先配置门户地址或 Datacenter 直连，并填写 API Key",
        }

    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for card in MEDIACENTER_REGISTERABLE_HOME_CARDS:
            card_id = card["cardId"]
            owner = card.get("ownerService") or OWNER_SERVICE
            url = f"{api_base}/subsystems/home-cards/{card_id}/status"
            registered = False
            registered_at = None
            owned_by = None
            status_error = None
            try:
                res = await client.get(
                    url, params={"ownerService": owner}, headers=headers
                )
                if res.status_code >= 400:
                    detail = _extract_error_detail(res)
                    status_error = _friendly_status_error(res.status_code, detail)
                    if res.status_code == 401 and await _probe_datacenter_register_scope(
                        client, api_base, headers
                    ):
                        status_error = (
                            "无法查询注册状态（Datacenter 版本过旧，status 接口需 read 权限）。"
                            "密钥有效，可点击「注册」；成功后 Apps 下拉刷新即可。"
                        )
                else:
                    data = _unwrap_datacenter_data(res.json())
                    registered = bool(data.get("registered"))
                    registered_at = data.get("registeredAt")
                    owned_by = data.get("ownedBy")
            except httpx.HTTPError as e:
                status_error = str(e)

            items.append(
                {
                    "cardId": card_id,
                    "title": card.get("title") or card_id,
                    "subtitle": card.get("subtitle") or "",
                    "ownerService": owner,
                    "registered": registered,
                    "registeredAt": registered_at,
                    "ownedBy": owned_by,
                    "statusError": status_error,
                }
            )

    return {"ok": True, "list": items}


async def register_home_card(
    integration: IntegrationSettings,
    card_id: str,
) -> dict[str, Any]:
    card = get_registerable_home_card(card_id)
    if not card:
        return {"ok": False, "error": f"未知卡片: {card_id}"}

    api_base, headers = await _datacenter_request_headers(integration)
    if not api_base:
        return {"ok": False, "error": "无法发现 datacenter 地址"}

    if not headers.get("X-API-Key"):
        return {
            "ok": False,
            "error": "未配置 Datacenter API Key（需 subsystem.register 权限）",
        }

    payload = _build_subsystem_register_payload(card)
    url = f"{api_base}/subsystems/home-cards"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"注册 {card_id} 失败: 无法连接 datacenter ({e})"}
    if res.status_code >= 400:
        return {
            "ok": False,
            "error": f"注册 {card_id} 失败: {_extract_error_detail(res)}",
            "statusCode": res.status_code,
        }
    try:
        data = _unwrap_datacenter_data(res.json())
    except ValueError:
        data = {"cardId": card_id}
    return {"ok": True, "registered": data}


async def unregister_home_card(
    integration: IntegrationSettings,
    card_id: str,
) -> dict[str, Any]:
    card = get_registerable_home_card(card_id)
    if not card:
        return {"ok": False, "error": f"未知卡片: {card_id}"}

    api_base, headers = await _datacenter_request_headers(integration)
    if not api_base:
        return {"ok": False, "error": "无法发现 datacenter 地址"}

    owner = card.get("ownerService") or OWNER_SERVICE
    url = f"{api_base}/subsystems/home-cards/{card_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.delete(
            url, params={"ownerService": owner}, headers=headers
        )
    if res.status_code >= 400:
        return {
            "ok": False,
            "error": f"注销 {card_id} 失败: {_extract_error_detail(res)}",
            "statusCode": res.status_code,
        }
    try:
        data = _unwrap_datacenter_data(res.json())
    except ValueError:
        data = {"cardId": card_id}
    return {"ok": True, "unregistered": data}
