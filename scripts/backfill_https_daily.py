"""HTTPS full-universe daily shard; deterministic frozen historical universe."""
import argparse
import json
import time
from datetime import date
from pathlib import Path
from eastmoney_daily_https import fetch_daily_https

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
    snapshots = sorted(Path("data/baostock").glob("20??-??-??.json"), reverse=True)
    codes = None
    source_day = None
    for file in snapshots:
        if file.stem >= day:
            continue
        try:
            doc = json.loads(file.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("provider") != "baostock" or doc.get("coverage", {}).get("checked", 0) < 5000:
            continue
        found = {r["code"] for r in doc.get("rows", [])}
        found.update(r["code"] for r in doc.get("errors", []))
        found = sorted(c for c in found if len(c) == 9 and c.startswith(("sh.6", "sz.0", "sz.3")))
        if len(found) >= 5000:
            codes, source_day = found, file.stem
            break
    if codes is None:
        raise RuntimeError("No prior verified >=5000-code frozen SH/SZ universe")
    selected = codes[args.shard::8]
    rows, errors = [], []
    for code in selected:
        try:
            rows.append(fetch_daily_https(code, day))
        except Exception as exc:
            errors.append({"code": code, "reason": str(exc)[:120]})
        time.sleep(0.04)
    result = {"provider": "eastmoney_https_unofficial", "trade_date": day,
              "universe_source_date": source_day, "universe_candidate_count": len(codes),
              "shard": args.shard, "shards": 8, "checked_count": len(selected),
              "verified_count": len(rows), "rows": rows, "errors": errors,
              "coverage_ratio": round(len(rows)/len(selected),6)}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False)+"\n")
    print(json.dumps({"shard":args.shard,"checked":len(selected),"verified":len(rows),
                      "errors":len(errors),"universe":len(codes)}))
    return 0 if len(rows)/len(selected) >= .90 else 1

if __name__ == "__main__":
    raise SystemExit(main())
