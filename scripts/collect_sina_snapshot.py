"""Collect a separate, date-verified whole SH/SZ close snapshot in bounded batches."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_snapshot import SOURCES, STOCK_CODE_RE, validate_snapshot
from sina_snapshot import fetch_close_batch, PROVIDER
from trading_calendar import session_state


def collect(day, codes, *, fetch=fetch_close_batch, workers=4):
    codes = sorted(set(code for code in codes if STOCK_CODE_RE.fullmatch(code)))
    if len(codes) < 5000:
        raise ValueError("full_scope_requires_5000_frozen_stock_codes")
    rows, failures = {}, {}
    batches = [codes[i:i + 45] for i in range(0, len(codes), 45)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(fetch, batch, day): batch for batch in batches}
        for job in as_completed(jobs):
            batch = jobs[job]
            try:
                for row in job.result():
                    if row["code"] not in batch or row["code"] in rows:
                        raise ValueError("unexpected_or_duplicate_batch_code")
                    rows[row["code"]] = row
            except (OSError, ValueError) as exc:
                failures.update({code: type(exc).__name__ for code in batch})
    errors = [{"code": code, "reason": failures.get(code, "missing_suspended_stale_or_invalid_close")}
              for code in codes if code not in rows]
    return {"provider": PROVIDER, "trade_date": day, "status": "historical_observation_only",
            "exchange_scope": "Shanghai+Shenzhen; Beijing excluded",
            "collection_method": "timestamped_post_close_sina_quote_batches",
            "collected_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "coverage": {"checked": len(codes), "verified": len(rows), "errors": len(errors),
                         "coverage_ratio": round(len(rows) / len(codes), 6)},
            "rows": sorted(rows.values(), key=lambda r: r["code"]), "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    state = session_state(datetime.combine(day, datetime.min.time().replace(hour=16), now.tzinfo))
    if day > now.date() or (day == now.date() and (now.hour, now.minute) < (15, 30)) or state["code"] != "after_close":
        raise ValueError("verified_completed_session_required")
    root = ROOT / "backend/data"
    target = Path(args.output) if args.output else root / "sina_daily_full" / (args.date + ".json")
    if target.exists():
        old = json.loads(target.read_text())
        validate_snapshot(old, args.date, PROVIDER)
        print(json.dumps({"status": "already_verified", "coverage": old["coverage"]}))
        return 0
    files = [(p, provider) for provider, folder in SOURCES
             for p in (root / folder).glob("20??-??-??.json") if p.stem <= args.date
             and (day - datetime.strptime(p.stem, "%Y-%m-%d").date()).days <= 10]
    universe = None
    for path, provider in sorted(files, key=lambda pair: pair[0].stem, reverse=True):
        try:
            snapshot = validate_snapshot(json.loads(path.read_text()), path.stem, provider)
            universe = [row["code"] for row in snapshot["rows"] + snapshot["errors"]]
            break
        except (ValueError, TypeError, KeyError):
            continue
    if universe is None:
        raise ValueError("no_recent_frozen_stock_universe")
    payload = collect(args.date, universe)
    # Save diagnostics on failure, but only a validated snapshot enters readers.
    status = {"provider": PROVIDER, "trade_date": args.date, "coverage": payload["coverage"]}
    try:
        validate_snapshot(payload, args.date, PROVIDER)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
        status.update(ok=True, status="verified")
        code = 0
    except ValueError as exc:
        status.update(ok=False, status="insufficient_coverage", reason=str(exc))
        code = 1
    location = root / "market_source_status" / ("sina-" + args.date + ".json")
    location.parent.mkdir(exist_ok=True)
    location.write_text(json.dumps(status, ensure_ascii=False) + "\n")
    print(json.dumps(status, ensure_ascii=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
