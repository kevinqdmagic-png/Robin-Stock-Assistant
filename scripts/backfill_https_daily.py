"""HTTPS full-universe daily shard; deterministic frozen historical universe."""
import argparse
from collections import Counter
from http.client import HTTPException
import json
import time
from datetime import date, timedelta
from pathlib import Path
from eastmoney_daily_https import fetch_daily_https
from daily_snapshot import validate_snapshot, SOURCES


def frozen_universe(day, root=Path("backend/data")):
    candidates = []
    for provider, folder in SOURCES:
        candidates.extend((p, provider) for p in (root / folder).glob("20??-??-??.json"))
    for file, provider in sorted(candidates, key=lambda item: item[0].stem, reverse=True):
        if not ((date.fromisoformat(day) - timedelta(days=10)).isoformat() <= file.stem < day):
            continue
        try:
            doc = validate_snapshot(json.loads(file.read_text()), file.stem, provider)
            codes = sorted({r["code"] for r in doc["rows"] + doc["errors"]})
            return codes, file.stem
        except (OSError, ValueError, TypeError, KeyError):
            continue
    raise RuntimeError("No recent verified >=5000-stock frozen SH/SZ universe")


def collect_rows(selected, day, fetch=fetch_daily_https, pause=time.sleep):
    rows, errors, consecutive_failures, attempted = [], [], 0, 0
    for index, code in enumerate(selected):
        attempted += 1
        try:
            rows.append(fetch(code, day))
            consecutive_failures = 0
        except (OSError, HTTPException) as exc:
            consecutive_failures += 1
            errors.append({"code": code, "reason": type(exc).__name__})
        except Exception as exc:
            consecutive_failures = 0
            errors.append({"code": code, "reason": str(exc)[:120]})
        if consecutive_failures >= 5:
            errors.extend({"code": c, "reason": "not_attempted_after_transport_failure"}
                          for c in selected[index + 1:])
            break
        pause(.04)
    return rows, errors, attempted

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    if args.shards != 8 or not 0 <= args.shard < 8:
        raise ValueError("requires eight disjoint shards")
    codes, source_day = frozen_universe(day)
    selected = codes[args.shard::8]
    rows, errors, attempted = collect_rows(selected, day)
    result = {"provider": "eastmoney_https_unofficial", "trade_date": day,
              "universe_source_date": source_day, "universe_candidate_count": len(codes),
              "shard": args.shard, "shards": 8, "checked_count": len(selected),
              "attempted_count": attempted,
              "verified_count": len(rows), "rows": rows, "errors": errors,
              "coverage_ratio": round(len(rows)/len(selected),6)}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False)+"\n")
    print(json.dumps({"shard":args.shard,"checked":len(selected),"verified":len(rows),
                      "errors":len(errors),"universe":len(codes), "attempted": attempted,
                      "error_reasons": dict(Counter(e["reason"] for e in errors))}))
    return 0 if len(rows)/len(selected) >= .90 else 1

if __name__ == "__main__":
    raise SystemExit(main())
