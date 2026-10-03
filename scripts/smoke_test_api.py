#!/usr/bin/env python3
"""End-to-end smoke test for the LogiFlow API.

Usage:
    python3 scripts/smoke_test_api.py https://<backend-host>
    python3 scripts/smoke_test_api.py http://localhost:9000 --max-seconds 30

Flags any endpoint that errors or exceeds --max-seconds (AppSail hard-caps requests at 30s).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

CORRIDOR = {"source": "Delhi", "destination": "Mumbai"}

CHECKS: list[tuple[str, str, dict | None]] = [
    ("GET", "/health", None),
    ("GET", "/locations/resolve?place=Delhi", None),
    ("GET", "/railway/search/stations?query=Delhi", None),
    ("GET", "/railway/cargo-types", None),
    ("GET", "/railway/model-info", None),
    ("GET", "/water/ports/search?query=Mumbai", None),
    ("POST", "/intent/parse", {"user_brief": "Ship 500 kg electronics from Delhi to Mumbai, cheapest"}),
    ("POST", "/road/optimize", {**CORRIDOR, "priority": "balanced"}),
    ("POST", "/railway/optimize", {"origin_city": "Delhi", "destination_city": "Mumbai", "cargo_weight_kg": 100, "cargo_type": "General", "priority": "cost"}),
    ("POST", "/air/optimize", {**CORRIDOR, "weight_kg": 100, "cargo_type": "general", "priority": "balanced"}),
    ("POST", "/water/optimize", {"source": "Mumbai", "destination": "Chennai", "weight_kg": 1000, "priority": "balanced"}),
    ("POST", "/optimize", {**CORRIDOR, "priority": "balanced"}),
    ("POST", "/compose", {**CORRIDOR, "priority": "balanced", "compose_options": {"max_hubs": 2, "budget_seconds": 150}}),
    ("SSE", "/compose/stream", {"source": "Jaipur", "destination": "Kolkata", "priority": "cheap", "compose_options": {"max_hubs": 2, "budget_seconds": 150}}),
]


def _summarize(body: object) -> str:
    if isinstance(body, dict):
        for key in ("status", "recommended_mode", "error", "detail"):
            if key in body:
                return f"{key}={str(body[key])[:60]}"
        return "keys=" + ",".join(list(body)[:5])
    if isinstance(body, list):
        return f"list[{len(body)}]"
    return str(body)[:60]


def run_check(base: str, method: str, path: str, payload: dict | None, timeout: float) -> tuple[int | str, float, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method="GET" if method == "GET" else "POST",
        headers={"Content-Type": "application/json", "User-Agent": "logiflow-smoke"},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if method == "SSE":
                events, final = 0, None
                for raw in resp:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        events += 1
                        final = json.loads(line[6:])
                elapsed = time.monotonic() - start
                final = final or {}
                done = bool(final.get("done"))
                routes = (1 if final.get("recommended") else 0) + len(final.get("alternatives") or [])
                return resp.status, elapsed, f"events={events} done={done} routes={routes} err={final.get('error')}"
            body = json.loads(resp.read() or b"null")
            return resp.status, time.monotonic() - start, _summarize(body)
    except urllib.error.HTTPError as exc:
        return exc.code, time.monotonic() - start, exc.read()[:120].decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return "ERR", time.monotonic() - start, f"{type(exc).__name__}: {exc}"[:120]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--max-seconds", type=float, default=30.0)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    failures = 0
    print(f"{'endpoint':<40} {'code':>5} {'secs':>6}  result")
    for method, path, payload in CHECKS:
        code, secs, info = run_check(base, method, path, payload, timeout=args.max_seconds + 30)
        ok = code == 200 and secs <= args.max_seconds
        failures += 0 if ok else 1
        flag = "" if ok else ("  <-- SLOW" if code == 200 else "  <-- FAIL")
        print(f"{method + ' ' + path.split('?')[0]:<40} {code!s:>5} {secs:6.1f}  {info}{flag}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} passed (limit {args.max_seconds:.0f}s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
