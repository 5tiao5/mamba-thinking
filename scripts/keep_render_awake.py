from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


DEFAULT_URL = "https://product-agent-api.onrender.com/health"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ping(url: str, timeout: float) -> tuple[bool, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "product-agent-keepalive/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200).decode("utf-8", errors="replace").strip()
            return 200 <= response.status < 300, f"HTTP {response.status} {body}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {exc.reason}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ping a Render health endpoint periodically to reduce free-instance spin-down during demos."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Health URL to ping. Default: {DEFAULT_URL}",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="Seconds between pings. Default: 600 (10 minutes).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds. Default: 30.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ping once and exit.",
    )
    args = parser.parse_args()

    if args.interval < 60 and not args.once:
        print("Refusing to ping more often than once per minute.", file=sys.stderr)
        return 2

    while True:
        ok, message = ping(args.url, args.timeout)
        status = "ok" if ok else "fail"
        print(f"[{now_iso()}] {status}: {message}", flush=True)
        if args.once:
            return 0 if ok else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
