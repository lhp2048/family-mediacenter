"""M3U helpers for exporting playlists to TVBox live channels."""

from __future__ import annotations

from app.models.playlist import PlaylistItemResponse


def playlist_live_m3u_url(playlist_id: int, public_base: str) -> str:
    base = public_base.rstrip("/")
    return f"{base}/api/v1/playlists/{playlist_id}/live.m3u"


def _escape_m3u_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_live_m3u(items: list[PlaylistItemResponse]) -> str:
    lines = ["#EXTM3U"]
    for item in items:
        if not item.exists or not item.public_url:
            continue
        title = (item.title or item.name or item.rel_path).replace("\n", " ").strip()
        if not title:
            title = item.rel_path
        if "," in title or '"' in title:
            escaped = _escape_m3u_attr(title)
            lines.append(f'#EXTINF:-1 tvg-name="{escaped}",{title}')
        else:
            lines.append(f"#EXTINF:-1,{title}")
        lines.append(item.public_url)
    return "\n".join(lines) + "\n"
