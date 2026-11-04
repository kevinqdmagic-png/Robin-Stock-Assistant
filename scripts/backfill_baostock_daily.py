"""Bounded historical A-share backfill; research input only, never a trading signal."""
import argparse
import json
import math
from datetime import date
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-11-03")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="artifacts/baostock-2026-11-03.json")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    if not 1 <= args.limit <= 6000:
        raise ValueError("limit must be 1..6000")
    if args.shards < 1 or not 0 <= args.shard < args.shards:
        raise ValueError("invalid shard configuration")
    import baostock as bs
    output = {"provider": "baostock", "trade_date": day, "scope": "shanghai_shenzhen_shard", "requested_limit": args.limit, "rows": [], "errors": [], "ok": False}
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError("BaoStock login failed: " + login.error_msg)
    try:
        universe = bs.query_all_stock(day=day)
        if universe.error_code != "0":
            raise RuntimeError("universe error: " + universe.error_msg)
        codes = []
        while universe.next():
            row = dict(zip(universe.fields, universe.get_row_data()))
            code = row.get("code", "")
            if (code.startswith("sh.6") or code.startswith("sz.0") or code.startswith("sz.3")) and len(code) == 9:
                codes.append(code)
        codes = sorted(set(codes))
        output["universe_candidate_count"] = len(codes)
        output["excluded_beijing_exchange"] = True
        output["shard"] = args.shard
        output["shards"] = args.shards
        # Spread the bounded sample deterministically across the full ordered universe.
        selected = codes[args.shard::args.shards]
        if len(selected) > args.limit:
            selected = [selected[i * len(selected) // args.limit] for i in range(args.limit)]
        for code in selected:
            try:
                rs = bs.query_history_k_data_plus(code, "date,code,open,high,low,close,volume,amount,tradestatus", start_date=day, end_date=day, frequency="d", adjustflag="3")
                if rs.error_code != "0":
                    output["errors"].append({"code": code, "reason": "query_failed", "error_code": rs.error_code})
                    continue
                bars = []
                while rs.next():
                    bars.append(dict(zip(rs.fields, rs.get_row_data())))
                if not bars:
                    output["errors"].append({"code": code, "reason": "missing_or_suspended"})
                    continue
                bar = bars[-1]
                values = [float(bar[k]) for k in ("open", "high", "low", "close", "volume", "amount")]
                o,h,l,c,v,a = values
                if bar["date"] != day or not all(map(math.isfinite, values)) or not (0 < l <= min(o,c) <= max(o,c) <= h and v >= 0 and a >= 0):
                    output["errors"].append({"code": code, "reason": "invalid_ohlcv"})
                    continue
                output["rows"].append({"code": code, "date": day, "open": o, "high": h, "low": l, "close": c, "volume": v, "amount": a, "adjustment": "none", "provider": "baostock"})
            except Exception as exc:
                output["errors"].append({"code": code, "reason": type(exc).__name__, "detail": str(exc)[:120]})
        output["checked_count"] = len(selected)
        output["verified_count"] = len(output["rows"])
        output["coverage_ratio"] = round(len(output["rows"]) / len(selected), 6) if selected else 0.0
        output["ok"] = bool(output["rows"]) and len(output["rows"]) + len(output["errors"]) == len(selected)
        output["warning"] = "Shard only; merge and verify all shards before claiming full-market coverage. No recommendations computed."
    finally:
        bs.logout()
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k:v for k,v in output.items() if k not in ("rows","errors")}, ensure_ascii=False))
    return 0 if output["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
