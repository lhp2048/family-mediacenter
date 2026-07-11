"""Offline smoke test for cms_probe helpers."""

from app.tvbox_testing.cms_probe import (
    _aggregate_layer,
    classify_site,
    cms_response_ok,
    extract_play_signal,
    extract_vod_id,
    normalize_api_base,
    parse_cms_json,
)


def main() -> None:
    body = (
        '{"code":1,"class":[{"type_id":1,"type_name":"movie"}],'
        '"list":[{"vod_id":123,"vod_name":"test",'
        '"vod_play_url":"ep1$https://cdn.example.com/a.m3u8"}]}'
    )
    data, err = parse_cms_json(body)
    assert err == "" and data is not None
    assert cms_response_ok(data)
    assert extract_vod_id(data["list"][0]) == "123"
    assert extract_play_signal(data["list"][0])

    assert classify_site({"api": "csp_Bili", "type": 3}) == "spider"
    assert classify_site({"api": "https://x.com/api.php/provide/vod/", "type": 0}) == "cms"

    base = normalize_api_base("https://x.com/api.php/provide/vod/?ac=list")
    assert base.endswith("/provide/vod/")

    layer = _aggregate_layer(
        "L3",
        max_score=15,
        results=[
            {"site": "A", "status": "pass", "score": 15, "message": "ok"},
            {"site": "B", "status": "fail", "score": 0, "message": "bad"},
        ],
        skip_message="skip",
    )
    assert layer["status"] == "partial"
    assert layer["score"] == 15
    print("cms_probe offline ok")


if __name__ == "__main__":
    main()
