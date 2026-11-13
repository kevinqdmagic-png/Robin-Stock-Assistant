#!/usr/bin/env python3
"""Resumable, bounded Sina SH/SZ close collector with explicit retry evidence."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_snapshot import STOCK_CODE_RE, validate_snapshot
from sina_snapshot import fetch_close_batch, PROVIDER


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    day = args.date
    data = ROOT / "backend/data"
    target = data / "sina_daily_full" / f"{day}.json"
    progress = data / "sina_daily_full" / f".{day}.progress.json"
    status_path = data / "market_source_status" / f"sina-{day}.json"
    if target.exists():
        old = validate_snapshot(json.loads(target.read_text()), day, PROVIDER)
        print(json.dumps({"status": "already_verified", "coverage": old["coverage"]}, ensure_ascii=False))
        return 0

    prior = json.loads((data / "baostock" / "2026-11-12.json").read_text())
    codes = sorted({x["code"] for x in prior["rows"] + prior["errors"] if STOCK_CODE_RE.fullmatch(x["code"])})
    state = json.loads(progress.read_text()) if progress.exists() else {"rows": [], "attempts": {}}
    rows = {x["code"]: x for x in state.get("rows", [])}
    attempts = state.get("attempts", {})

    pending = [codes[i:i+45] for i in range(0, len(codes), 45) if any(c not in rows for c in codes[i:i+45])]

    def fetch(batch):
        wanted = [c for c in batch if c not in rows]
        last = None
        for n in range(1, 4):
            try:
                result = fetch_close_batch(wanted, day)
                return wanted, result, None, n
            except (OSError, ValueError) as exc:
                last = f"{type(exc).__name__}:{str(exc)[:140]}"
                time.sleep(0.5 * n)
        return wanted, [], last, 3

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 3))) as pool:
        futures = {pool.submit(fetch, batch): batch for batch in pending}
        for future in as_completed(futures):
            wanted, found, error, count = future.result()
            for item in found:
                rows[item["code"]] = item
            for code in wanted:
                attempts[code] = {"attempt_count": count, "last_error": error,
                                  "received": code in rows}
            completed += 1
            if completed % 10 == 0 or completed == len(pending):
                write(progress, {"rows": sorted(rows.values(), key=lambda x: x["code"]),
                                 "attempts": attempts, "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()})
                print(json.dumps({"batches": completed, "total_batches": len(pending), "verified": len(rows)}, ensure_ascii=False), flush=True)

    errors = [{"code": code, "reason": attempts.get(code, {}).get("last_error") or
               "missing_suspended_stale_or_invalid_close"} for code in codes if code not in rows]
    payload = {
        "provider": PROVIDER,
        "trade_date": day,
        "status": "historical_observation_only",
        "exchange_scope": "Shanghai+Shenzhen; Beijing excluded",
        "collection_method": "resumable_timestamped_post_close_sina_quote_batches",
        "collected_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "coverage": {"checked": len(codes), "verified": len(rows), "errors": len(errors),
                     "coverage_ratio": round(len(rows) / len(codes), 6)},
        "rows": sorted(rows.values(), key=lambda x: x["code"]),
        "errors": errors,
    }
    status = {"provider": PROVIDER, "trade_date": day, "coverage": payload["coverage"],
              "retry_policy": "up_to_3_per_batch_sequential_bounded", "progress_path": str(progress.relative_to(ROOT))}
    try:
        validate_snapshot(payload, day, PROVIDER)
        write(target, payload)
        status.update(ok=True, status="verified")
        rc = 0
    except ValueError as exc:
        status.update(ok=False, status="insufficient_coverage", reason=str(exc))
        rc = 1
    write(status_path, status)
    print(json.dumps(status, ensure_ascii=False), flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
