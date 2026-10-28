"""Offline checks for Bilibili QR cookie extraction."""

import httpx

from app.engines.ytdlp import default_cookies_for_url
from app.services.bilibili_login import (
    cookies_from_login_payload,
    cookies_from_set_cookie_headers,
    login_status_code,
    merge_login_cookies,
)


def main() -> None:
    body = {
        "code": 0,
        "data": {
            "url": (
                "https://passport.bilibili.com/x/passport-login/web/crossDomain"
                "?DedeUserID=100&DedeUserID__ckMd5=abcd"
                "&SESSDATA=abc%2C123&bili_jct=jct&gourl=https%3A%2F%2Fwww.bilibili.com"
            )
        },
    }
    parsed = cookies_from_login_payload(body)
    assert parsed["SESSDATA"] == "abc,123", parsed
    assert parsed["bili_jct"] == "jct"
    assert parsed["DedeUserID"] == "100"
    assert parsed["DedeUserID__ckMd5"] == "abcd"

    headers = httpx.Headers(
        [
            ("set-cookie", "sid=session-1; Path=/; Domain=.bilibili.com"),
            (
                "set-cookie",
                "SESSDATA=from-header; Expires=Thu, 31 Dec 2030 23:59:59 GMT; Path=/",
            ),
        ]
    )
    header_cookies = cookies_from_set_cookie_headers(headers)
    assert header_cookies["sid"] == "session-1"
    assert header_cookies["SESSDATA"] == "from-header"

    merged = merge_login_cookies({}, header_cookies, body)
    assert merged["SESSDATA"] == "abc,123"
    assert merged["sid"] == "session-1"

    info_body = {
        "data": {
            "cookie_info": {
                "cookies": [{"name": "SESSDATA", "value": "from-info"}],
            }
        }
    }
    assert cookies_from_login_payload(info_body)["SESSDATA"] == "from-info"

    assert default_cookies_for_url("https://www.bilibili.com/video/BV1") == (
        "data/bilibili_cookies.txt"
    )
    assert default_cookies_for_url("https://b23.tv/abc") == "data/bilibili_cookies.txt"
    assert default_cookies_for_url("https://www.youtube.com/watch?v=1") == ""

    waiting = {"code": 0, "message": "0", "data": {"url": "", "code": 86101, "message": ""}}
    scanned = {"code": 0, "data": {"url": "", "code": 86090}}
    success = {
        "code": 0,
        "data": {
            "code": 0,
            "url": "https://passport.biligame.com/crossDomain?SESSDATA=ok",
        },
    }
    assert login_status_code(waiting) == 86101
    assert login_status_code(scanned) == 86090
    assert login_status_code(success) == 0

    escaped = {
        "data": {
            "url": "https://passport.biligame.com/crossDomain?DedeUserID=1\\u0026SESSDATA=abc%2C9\\u0026bili_jct=jct"
        }
    }
    assert cookies_from_login_payload(escaped)["SESSDATA"] == "abc,9"
    print("bilibili cookie extraction ok")


if __name__ == "__main__":
    main()
