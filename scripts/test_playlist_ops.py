"""Name matching for MCP playlist tools. No running server required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))

from playlist_ops import matching_rows, mutation_targets, resolve_playlist


PLAYLISTS = [
    {"id": 1, "name": "全部下载", "is_default": True},
    {"id": 2, "name": "睡前故事"},
    {"id": 3, "name": "故事会"},
]

FILES = [
    {"name": "小熊.mp4", "title": "小熊.mp4", "rel_path": "stories/小熊.mp4"},
    {"name": "小熊2.mp4", "title": "小熊2.mp4", "rel_path": "stories/小熊2.mp4"},
    {"name": "钢琴练习.mp4", "title": "钢琴练习.mp4", "rel_path": "music/钢琴练习.mp4"},
]


def main() -> None:
    assert resolve_playlist(PLAYLISTS, "睡前故事")["id"] == 2
    assert resolve_playlist(PLAYLISTS, "睡前")["id"] == 2
    try:
        resolve_playlist(PLAYLISTS, "故事")
        raise SystemExit("ambiguous playlist name should fail")
    except ValueError as exc:
        assert "睡前故事" in str(exc) and "故事会" in str(exc)

    matched = matching_rows("小熊,钢琴", FILES, ("name", "rel_path"))
    assert [row["rel_path"] for row in matched] == [
        "stories/小熊.mp4",
        "stories/小熊2.mp4",
        "music/钢琴练习.mp4",
    ]
    wild = matching_rows("stories/*", FILES, ("name", "rel_path"))
    assert len(wild) == 2

    one, err = mutation_targets("钢琴练习.mp4", FILES, ("name", "rel_path"))
    assert err == "" and one[0]["rel_path"] == "music/钢琴练习.mp4"

    unique, err = mutation_targets("钢琴", FILES, ("name", "rel_path"))
    assert err == "" and len(unique) == 1

    many, err = mutation_targets("小熊", FILES, ("name", "rel_path"))
    assert many == [] and "小熊2.mp4" in err

    exact, err = mutation_targets("小熊.mp4", FILES, ("name", "rel_path"))
    assert err == "" and [row["name"] for row in exact] == ["小熊.mp4"]

    batch, err = mutation_targets("小熊*", FILES, ("name", "rel_path"))
    assert err == "" and len(batch) == 2

    print("ok")


if __name__ == "__main__":
    main()
