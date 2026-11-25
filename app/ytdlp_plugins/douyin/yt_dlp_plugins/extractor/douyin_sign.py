"""Teach the installed Douyin extractor to sign the web detail request."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from yt_dlp.extractor.tiktok import DouyinIE
from yt_dlp.utils import ExtractorError, traverse_obj

from app.services.douyin_sign import AID, sign_query

_REQUIRED_COOKIES = ("passport_csrf_token", "ttwid")
_UIFID_NAMES = ("uifid", "uifid_temp", "uifidtemp", "UIFID", "UIFID_TEMP", "UIFIDTEMP")


def _get_ttwid(self):
    self._request_webpage(
        f"{self._WEBPAGE_HOST}ttwid/register",
        None,
        data=json.dumps({"aid": AID, "service": "www.douyin.com"}).encode(),
        headers={"content-type": "application/json"},
    )
    cookie = self._get_cookies(self._WEBPAGE_HOST).get("ttwid")
    return cookie.value if cookie else None


def _ensure_cookies(self) -> None:
    for name in _REQUIRED_COOKIES:
        if self._get_cookies(self._WEBPAGE_HOST).get(name):
            continue
        value = _get_ttwid(self) if name == "ttwid" else DouyinIE._family_csrf
        if not value:
            raise ExtractorError("无法准备抖音请求")
        self._set_cookie(".douyin.com", name, value)


def _uifid(self) -> str:
    found = traverse_obj(self._get_cookies(self._WEBPAGE_HOST), (_UIFID_NAMES, "value"), get_all=False)
    if found:
        return str(found)
    page = self._request_webpage(self._WEBPAGE_HOST, None)
    trace = page.headers.get("x-tt-trace-host")
    if not trace:
        raise ExtractorError("抖音没有返回签名所需的 uifid")
    return trace


def _aweme_detail(self, video_id: str):
    query = sign_query({"aweme_id": video_id, "aid": AID}, _uifid(self), str(int(time.time())))
    return traverse_obj(
        self._download_json(
            "https://www.douyin.com/aweme/v1/web/aweme/detail/",
            video_id,
            "Downloading web detail JSON",
            "Failed to download web detail JSON",
            query=query,
            fatal=False,
        ),
        ("aweme_detail", {dict}),
    )


def _real_extract(self, url):
    video_id = self._match_id(url)
    _ensure_cookies(self)
    detail = _aweme_detail(self, video_id)
    if not detail:
        raise ExtractorError(
            "Fresh cookies (not necessarily logged in) are needed",
            expected=not self._get_cookies(self._WEBPAGE_HOST).get("s_v_web_id"),
        )
    parsed = self._parse_aweme_video_app(detail)
    parsed["http_headers"] = {"Referer": self._WEBPAGE_HOST}
    return parsed


if not getattr(DouyinIE, "_family_signed", False):
    DouyinIE._family_csrf = uuid.uuid4().hex
    DouyinIE._real_extract = _real_extract
    DouyinIE._family_signed = True
