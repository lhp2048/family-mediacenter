"""Sign Douyin web detail requests.

Official yt-dlp still calls /aweme/v1/web/aweme/detail/ without
x-secsdk-web-signature, and Douyin answers 403. The hash used here is the
one described for yt-dlp PR 17826: md5(uifid_timestamp_salt_query).
"""

from __future__ import annotations

import hashlib
import urllib.parse

SEC_SALT = "A96D855A08C0A9707F8BEF0D9A527E4E"
AID = 6383


def sign_query(query: dict, uifid: str, timestamp: str) -> dict:
    merged = {**query, "uifid": uifid, "timestamp": timestamp}
    encoded = urllib.parse.urlencode(merged)
    digest = hashlib.md5(f"{uifid}_{timestamp}_{SEC_SALT}_{encoded}".encode()).hexdigest()
    return {**merged, "x-secsdk-web-signature": digest}
