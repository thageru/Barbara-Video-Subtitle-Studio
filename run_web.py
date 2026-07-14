#!/usr/bin/env python3
from __future__ import annotations

import argparse

from video_tool.web import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Barbara-Video-Subtitle-Studio web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="bind host; keep 127.0.0.1 for local-only use")
    parser.add_argument("--port", default=8876, type=int, help="bind port")
    parser.add_argument("--open", action="store_true", help="open the default browser")
    args = parser.parse_args()
    run(host=args.host, port=args.port, open_browser=args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
