#!/usr/bin/env python3
"""Probe HTTP Range support for mediacenter PDF streaming (pdf.js URL mode)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200 /Contents 4 0 R >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 12 Tf 50 100 Td (Range Test) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer<< /Size 5 /Root 1 0 R >>
startxref
297
%%EOF
"""


def _print(title: str) -> None:
    print(f"\n=== {title} ===")


def test_starlette_file_response() -> bool:
    """Same FileResponse class mediacenter uses."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "probe.pdf"
        pdf.write_bytes(MINIMAL_PDF)
        app = FastAPI()

        @app.get("/probe.pdf")
        def _serve() -> FileResponse:
            return FileResponse(
                path=pdf,
                media_type="application/pdf",
                content_disposition_type="inline",
            )

        client = TestClient(app)
        full = client.get("/probe.pdf")
        ranged = client.get("/probe.pdf", headers={"Range": "bytes=0-31"})

        _print("Starlette FileResponse (same as mediacenter /files/...)")
        print(f"GET Accept-Ranges: {full.headers.get('accept-ranges')}")
        print(f"GET full status: {full.status_code}, bytes: {len(full.content)}")
        print(f"GET Range 0-31 status: {ranged.status_code}")
        print(f"Content-Range: {ranged.headers.get('content-range')}")
        print(f"Range body length: {len(ranged.content)}")

        ok = (
            full.status_code == 200
            and (full.headers.get("accept-ranges") or "").lower() == "bytes"
            and ranged.status_code == 206
            and len(ranged.content) == 32
        )
        print("RESULT:", "PASS" if ok else "FAIL")
        return ok


def test_mediacenter_app_route() -> bool:
    from fastapi.testclient import TestClient

    from app.main import app

    ebooks = ROOT / "downloads" / "ebooks"
    ebooks.mkdir(parents=True, exist_ok=True)
    probe = ebooks / "_range_probe.pdf"
    probe.write_bytes(MINIMAL_PDF)
    rel = "ebooks/_range_probe.pdf"

    client = TestClient(app)
    url = f"/files/{rel}"
    full = client.get(url)
    ranged = client.get(url, headers={"Range": "bytes=0-63"})
    cors_get = client.get(
        url,
        headers={
            "Origin": "http://127.0.0.1:18027",
            "Range": "bytes=0-63",
        },
    )
    cors = client.options(
        url,
        headers={
            "Origin": "http://127.0.0.1:18027",
            "Access-Control-Request-Method": "GET",
        },
    )

    _print("family_mediacenter app route GET /files/ebooks/_range_probe.pdf")
    print(f"GET Accept-Ranges: {full.headers.get('accept-ranges')}")
    print(f"GET full: {full.status_code}, {len(full.content)} bytes")
    print(f"GET Range 0-63: {ranged.status_code}, body={len(ranged.content)} bytes")
    print(f"Content-Range: {ranged.headers.get('content-range')}")
    print(f"CORS preflight: {cors.status_code}")
    print(f"Access-Control-Allow-Origin: {cors.headers.get('access-control-allow-origin')}")
    print(
        "Access-Control-Expose-Headers (GET): "
        f"{cors_get.headers.get('access-control-expose-headers')}"
    )

    expose = (cors_get.headers.get("access-control-expose-headers") or "").lower()
    ok = (
        full.status_code == 200
        and (full.headers.get("accept-ranges") or "").lower() == "bytes"
        and ranged.status_code == 206
        and cors.headers.get("access-control-allow-origin") in ("*", "http://127.0.0.1:18027")
        and "accept-ranges" in expose
        and "content-range" in expose
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def test_live_server(base: str = "http://127.0.0.1:18026") -> bool | None:
    try:
        import httpx
    except ImportError:
        print("\n(skip live server: httpx not installed)")
        return None

    rel = "ebooks/_range_probe.pdf"
    url = f"{base.rstrip('/')}/files/{rel}"
    _print(f"Live server {url}")
    try:
        with httpx.Client(timeout=5.0) as client:
            full = client.get(url)
            if full.status_code == 404:
                print("Probe file missing on server; restart mediacenter after probe file created.")
                return None
            ranged = client.get(url, headers={"Range": "bytes=0-31"})
    except httpx.HTTPError as exc:
        print(f"Server not reachable: {exc}")
        return None

    print(f"GET: {full.status_code}, Accept-Ranges: {full.headers.get('accept-ranges')}")
    print(f"Range GET: {ranged.status_code}, Content-Range: {ranged.headers.get('content-range')}")
    ok = full.status_code == 200 and ranged.status_code == 206
    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


def main() -> int:
    print("PDF Range / streaming feasibility probe")
    print(f"Project: {ROOT}")

    results: list[tuple[str, bool | None]] = []
    results.append(("file_response", test_starlette_file_response()))
    results.append(("mediacenter_route", test_mediacenter_app_route()))
    live = test_live_server()
    results.append(("live_18026", live))

    _print("Summary")
    for name, ok in results:
        if ok is None:
            status = "SKIP"
        else:
            status = "PASS" if ok else "FAIL"
        print(f"  {name}: {status}")

    core_ok = results[0][1] and results[1][1]
    print(
        "\nConclusion:",
        "Range streaming is FEASIBLE for mediacenter /files/ + pdf.js URL mode."
        if core_ok
        else "Range streaming blocked — investigate FileResponse / routing.",
    )
    if core_ok:
        print(
            "Next step: Flutter Web PDF reader can use public_url + pdf.js getDocument({url}) "
            "instead of Dio full download + openData."
        )
        print(
            "Reference: family_mediacenter material_reader.js ensurePdfLoaded() "
            "already uses disableRange: false."
        )
    return 0 if core_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
