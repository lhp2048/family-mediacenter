#!/usr/bin/env python3
"""读取 family-product.json 单个字段（供 bat 脚本调用）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: read_manifest_field.py <manifest.json> <field> [default]", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    field = sys.argv[2]
    default = sys.argv[3] if len(sys.argv) > 3 else ""
    data = json.loads(path.read_text(encoding="utf-8"))
    print(data.get(field, default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
