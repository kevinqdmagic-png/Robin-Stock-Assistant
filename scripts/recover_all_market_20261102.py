#!/usr/bin/env python3
"""Retrospective T2026-11-02 full PRIOR-SESSION A-share universe daybar recovery.

Source of universe is immutable T2026-10-30 full quote dump; never select from
11/02 winners. This cannot recreate a new Nov2 contemporaneous screener.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import gzip
import json
from pathlib import Path
import statistics
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from daily_providers import tencent_daily
from quote_providers import stock_symbol

T = "2026-10-30"
D = "2026-11-02"
ARCHIVE = ROOT / "docs/research/combined-pair-20261030-evidence.json.gz"
DEST = ROOT / "docs/research/nov02-retrospective-market.json"
CN = ZoneInfo("Asia/Shanghai")


def prior_universe(archive=ARCHIVE):
    j = json.loads(gzip.decompress(Path(archive).read_bytes()))
    if j.get("market_date") != T:
        raise ValueError("prior_source_date_mismatch")
    quotes = j.get("quotes")
    if not isinstance(quotes, dict):
        pages = j.get("sina_pages")
        if not isinstance(pages, dict):
            raise ValueError("original_full_quote_universe_not_available")
        quotes = {r["code"]: r for p in pages.values() for r in p.get("payload", [])
                  if isinstance(r, dict) and r.get("code")}
    eligible = {}
    invalid = []
    for code, r in quotes.items():
        if not (isinstance(code, str) and len(code) == 6 and code.isdecimal()):
            continue
        if code.startswith(("200", "900")):
            continue
        try:
            close = float(r.get("trade") or 0)
            prior = float(r.get("settlement") or 0)
        except (ValueError, TypeError):
            close, prior = 0.0, 0.0
        if close > 0 and prior > 0:
            eligible[code] = {"code": code, "name": r.get("name"), "anchor_close": close}
        else:
            invalid.append(code)
    if len(eligible) < 5000:
        raise ValueError(f"prior_universe_too_small:{len(eligible)}")
    return dict(sorted(eligible.items())), invalid, len(quotes)


def collect_stock(code, anchor, day_provider=tencent_daily):
    """Exact date unadjusted 20-day RVOL using preceding 20 complete bars."""
    error = None
    for attempt in range(2):
        try:
            hist = day_provider(code, limit=90, adjust="0")
            indexed = {b["date"]: b for b in hist}
            if T not in indexed or D not in indexed:
                raise ValueError("missing_exact_T_or_D_daily_bar")
            prev, current = indexed[T], indexed[D]
            if abs(prev["close"] - anchor["anchor_close"]) > 0.03:
                raise ValueError("T_close_anchor_mismatch")
            old = [b for b in hist if b["date"] < D][-20:]
            rvol = current["volume"] / (sum(b["volume"] for b in old) / 20) if len(old) == 20 and sum(b["volume"] for b in old) > 0 else None
            if current["close"] <= 0 or prev["close"] <= 0:
                raise ValueError("bad_closing_price")
            return {
                "code": code, "name": anchor["name"], "T_close": prev["close"],
                "D_open": current["open"], "D_high": current["high"],
                "D_low": current["low"], "D_close": current["close"],
                "D_volume_source_units": current["volume"],
                "D_pct": round((current["close"] / prev["close"] - 1)*100, 5),
                "D_RVOL20": round(rvol, 5) if rvol is not None else None,
                "D_CLV": round((current["close"]-current["low"])/(current["high"]-current["low"]),5)
                         if current["high"] > current["low"] else None,
                "data_date_verified": True,
                "provider": "Tencent unadjusted historical day K",
                "symbol": stock_symbol(code),
            }
        except Exception as exc:
            error = f"{type(exc).__name__}:{str(exc)[:85]}"
            if attempt == 0:
                time.sleep(.15)
    raise ValueError(error)


def partition(codes, part, parts):
    return [code for index, code in enumerate(codes) if index % parts == part]


def fetch_shard(part, parts, workers=5):
    originals, excluded, all_quotes = prior_universe()
    subset = partition(list(originals), part, parts)
    rows, errors = [], {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(collect_stock, code, originals[code]): code for code in subset}
        for fut in as_completed(jobs):
            code = jobs[fut]
            try:
                rows.append(fut.result())
            except Exception as exc:
                errors[code] = str(exc)[:130]
    out = {
        "schema_version": 1, "T": T, "D": D, "part": part, "parts": parts,
        "collected_at_cn": datetime.now(CN).isoformat(timespec="seconds"),
        "prior_universe_n": len(originals), "original_source_quotes_n": all_quotes,
        "original_excluded_count": len(excluded),
        "requested": len(subset), "retrieved": len(rows), "failed": len(errors),
        "rows": sorted(rows, key=lambda r:r["code"]), "errors": errors,
        "source": str(ARCHIVE.relative_to(ROOT)),
        "not_contemporaneous": True, "not_all_listed_on_D": True,
        "intraday_fill_verified": False
    }
    folder = ROOT / "tmp" / "nov02-market-shards"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/f"shard-{part:02d}.json").write_text(json.dumps(out,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:out[k] for k in ("part","parts","requested","retrieved","failed","prior_universe_n")}))
    # Source-specific failed securities stay visible, not filled by interpolation.
    return 0 if len(rows) >= int(len(subset)*.85) else 2


def merge_shards(parts, folder):
    shards = [json.loads((folder/f"shard-{p:02d}.json").read_text()) for p in range(parts)]
    universe, excluded, raw_count = prior_universe()
    if any(s["T"]!=T or s["D"]!=D or s["part"]!=i or s["parts"]!=parts for i,s in enumerate(shards)):
        raise ValueError("shard_mismatch")
    allrows = [r for s in shards for r in s["rows"]]
    codes = [r["code"] for r in allrows]
    if len(codes)!=len(set(codes)) or sum(s["requested"] for s in shards)!=len(universe):
        raise ValueError("duplicate_or_incomplete_universe_partition")
    errors={c:e for s in shards for c,e in s["errors"].items()}
    if len(allrows)+len(errors)!=len(universe):
        raise ValueError("unaccounted_code")
    scores = [r["D_pct"] for r in allrows]
    advanced=sum(n>0 for n in scores); declined=sum(n<0 for n in scores)
    # T before D, so this is an after-the-fact statistical pool, not a real Nov2 freeze.
    result={
        "schema_version":1,"source_session":T,"target_session":D,
        "actual_compilation_time_cn":datetime.now(CN).isoformat(timespec="seconds"),
        "source_archive":str(ARCHIVE.relative_to(ROOT)),
        "source_provider":"Tencent unadjusted daily K",
        "scope":"prior_session_full_positive_price_quote_universe_only",
        "is_full_current_day_stock_universe":False,
        "prior_universe_count":len(universe),
        "all_prior_raw_quotes_count":raw_count,
        "excluded_untradeable_or_invalid_prior_quotes":len(excluded),
        "D_bars_verified":len(allrows),"D_bars_missing":len(errors),
        "all_missing_with_reason":errors,
        "stat":{"advanced":advanced,"declined":declined,
                "unchanged":len(scores)-advanced-declined,
                "median_pct":round(statistics.median(scores),5) if scores else None,
                "mean_pct":round(statistics.mean(scores),5) if scores else None,
                "D_rvol20_available":sum(r["D_RVOL20"] is not None for r in allrows)},
        "rows":sorted(allrows,key=lambda r:r["code"]),
        "provider_url_template":"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "analysis_completed":False,
        "eligible_for_integrated_research":False,
        "retroactive_evidence_only":True,
        "not_full_market_T20261102_new_admissions":True,
        "not_full_formal_candidate_screen":True,
        "no_retroactive_trading_signals":True,
        "verified_order_fills":0,
        "missing":["2026-11-02 new listed or price-zero changes","exact price-limit state",
                   "full minute/auction/order data","contemporaneous Nov2 freeze",
                   "complete Nov2 exchange disclosure seats"],
    }
    DEST.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("prior_universe_count","D_bars_verified","D_bars_missing","stat")},ensure_ascii=False))
    return 0 if len(allrows)>int(len(universe)*.85) else 2


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--part",type=int)
    p.add_argument("--parts",type=int,default=8)
    p.add_argument("--merge",action="store_true")
    a=p.parse_args()
    if a.merge:
        return merge_shards(a.parts,ROOT/"tmp/nov02-market-shards")
    if a.part is None or not 0<=a.part<a.parts:
        p.error("valid --part required")
    return fetch_shard(a.part,a.parts)


if __name__=="__main__":
    raise SystemExit(main())
