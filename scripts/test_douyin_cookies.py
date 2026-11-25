"""Offline checks for Douyin QR cookie extraction and site cookie priority."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.engines.ytdlp as ytdlp  # noqa: E402
from app.config import settings  # noqa: E402
from app.engines.ytdlp import (  # noqa: E402
    YtDlpEngine,
    cookie_file_candidates,
    default_cookies_for_url,
    select_cookies_file,
)
from app.services.douyin_login import (  # noqa: E402
    cookies_from_browser_list,
    cookies_to_netscape,
    devtools_port,
    login_page_state,
    netscape_has_cookie,
)


def main() -> None:
    browser_cookies = cookies_from_browser_list(
        [
            {"domain": ".douyin.com", "name": "sessionid", "value": "sid"},
            {"domain": ".bilibili.com", "name": "SESSDATA", "value": "nope"},
            {"domain": "www.douyin.com", "name": "ttwid", "value": "tw"},
        ]
    )
    assert browser_cookies == {"sessionid": "sid", "ttwid": "tw"}
    assert login_page_state("扫码登录", set()) == "waiting"
    assert login_page_state("请在手机上确认登录", set()) == "scanned"
    assert login_page_state("二维码已过期", set()) == "expired"
    assert login_page_state("请刷新二维码", set(), has_qr=True) == "waiting"
    assert login_page_state("首页", {"sessionid"}) == "success"
    assert login_page_state("首页", {"sessionid_ss"}) == "success"
    assert devtools_port(
        "DevTools listening on ws://127.0.0.1:50765/devtools/browser/abc"
    ) == 50765
    assert devtools_port("no chrome") is None

    text = cookies_to_netscape(
        {"sessionid": "sid", "uid_tt": "100", "ttwid": "tw", "extra": "1"}
    )
    assert netscape_has_cookie(text, "sessionid")
    assert ".douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\tsid" in text
    assert "uid_tt" in text and "extra" in text
    try:
        cookies_to_netscape({"ttwid": "only"})
        raise AssertionError("missing sessionid should fail")
    except ValueError:
        pass

    assert default_cookies_for_url("https://v.douyin.com/abc/") == "data/douyin_cookies.txt"
    assert default_cookies_for_url("https://www.iesdouyin.com/share/video/1") == (
        "data/douyin_cookies.txt"
    )
    assert default_cookies_for_url("https://www.bilibili.com/video/BV1") == (
        "data/bilibili_cookies.txt"
    )
    assert (
        cookie_file_candidates(
            "https://v.douyin.com/abc/",
            {"cookies_file": "custom.txt"},
            "data/bilibili_cookies.txt",
        )
        == ["custom.txt", "data/douyin_cookies.txt", "data/bilibili_cookies.txt"]
    )
    assert cookie_file_candidates(
        "https://www.youtube.com/watch?v=1",
        {},
        "data/bilibili_cookies.txt",
    ) == ["data/bilibili_cookies.txt"]

    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / "douyin.txt"
        shared = Path(tmp) / "shared.txt"
        site.write_text("site", encoding="utf-8")
        shared.write_text("shared", encoding="utf-8")
        chosen = select_cookies_file(
            "https://www.youtube.com/watch?v=1",
            {"cookies_file": str(site)},
            str(shared),
        )
        assert chosen == str(site.resolve())
        missing = select_cookies_file(
            "https://www.youtube.com/watch?v=1",
            {"cookies_file": str(Path(tmp) / "missing.txt")},
            str(shared),
        )
        assert missing == str(shared.resolve())

        old = settings.engines.ytdlp.cookies_file
        original_default = ytdlp.default_cookies_for_url
        settings.engines.ytdlp.cookies_file = str(shared)
        ytdlp.default_cookies_for_url = lambda url: str(site) if "douyin.com" in url else ""
        try:
            cmd = YtDlpEngine()._build_cmd("https://v.douyin.com/abc/", tmp, 4, {})
            other = YtDlpEngine()._build_cmd("https://www.youtube.com/watch?v=1", tmp, 5, {})
        finally:
            settings.engines.ytdlp.cookies_file = old
            ytdlp.default_cookies_for_url = original_default
        assert cmd[cmd.index("--cookies") + 1] == str(site.resolve())
        assert other[other.index("--cookies") + 1] == str(shared.resolve())
        assert "--plugin-dirs" in cmd

    from app.services.douyin_sign import sign_query

    signed = sign_query({"aweme_id": "7408754391605398820", "aid": 6383}, "abc", "1700000000")
    assert signed["uifid"] == "abc"
    assert signed["x-secsdk-web-signature"] == "4863aad5b615f68ee4189c2c24c44c4f"

    print("douyin cookie extraction ok")


if __name__ == "__main__":
    main()
