#!/usr/bin/env python3
"""Live, read-only production smoke probe for independent daily K fallback.

This is a provider availability check, not a test of the accumulation model.
It never publishes picks or historical performance.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

def get(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)

def probe(base, sha, code, wait=240):
    deadline = time.monotonic() + wait
    last = None
    while True:
        try:
            health = get(base + "/health")
            active_commit = health.get("build_commit")
            if sha and active_commit and not active_commit.startswith(sha):
                raise RuntimeError("deployment_not_yet_current:" + str(active_commit))
            result = get(base + "/api/stocks/" + code + "/capital-behavior")
            check = {
                "checked_at_utc": datetime.now().astimezone().isoformat(),
                "requested_code": code, "build_commit": active_commit,
                "ok": result.get("ok") is True,
                "status": result.get("status", "ok" if result.get("ok") else "unknown"),
                "source": result.get("source"),
                "provider_errors": result.get("provider_errors", []),
                "completed_bars": result.get("completed_bars", result.get("daily_bars", 0)),
                "as_of": result.get("as_of"),
            }
            if check["ok"] and check["completed_bars"] >= 61 and check["source"]:
                return check
            last = check
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            last = {"ok": False, "error_type": type(exc).__name__,
                    "details": str(exc)[:220]}
        print(json.dumps(last, ensure_ascii=False), flush=True)
        if time.monotonic() >= deadline:
            return last
        time.sleep(12)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base", default="https://robin-stock-api-production.up.railway.app")
    p.add_argument("--sha", default="")
    p.add_argument("--code", default="002068")
    p.add_argument("--wait", type=int, default=240)
    p.add_argument("--output", default="capital-daily-smoke.json")
    args=p.parse_args()
    response=probe(args.base.rstrip("/"), args.sha, args.code, args.wait)
    Path(args.output).write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n",encoding="utf-8")
    print("FINAL "+json.dumps(response, ensure_ascii=False),flush=True)
    return 0 if response.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
