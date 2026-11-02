#!/usr/bin/env python3
"""Independent source recovery of missing exact Nov2 daily bars, no backfilled trades."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from recover_all_market_20261102 import prior_universe
CN=ZoneInfo("Asia/Shanghai")
T="2026-10-30"; D="2026-11-02"
BASE=ROOT/"docs/research/nov02-retrospective-market.json"
DEST=ROOT/"docs/research/nov02-missing-daybar-fallback.json"


def request_json(url,params):
    full=url+"?"+urlencode(params)
    with urlopen(Request(full,headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"}),timeout=12) as rsp:
        obj=json.load(rsp)
    return obj,full


def symbol(c):
    return ("bj" if c.startswith(("4","8","92")) else "sh" if c.startswith(("5","6","9")) else "sz")+c


def normalize(rows,code,anchor,source):
    bars={}
    for raw in rows:
        try:
            if isinstance(raw,list):
                d,o,cl,hi,lo,v=raw[:6]
            else:
                d=raw.get("day") or raw.get("date")
                o=raw.get("open");cl=raw.get("close");hi=raw.get("high")
                lo=raw.get("low");v=raw.get("volume")
            d=str(d)[:10]
            if d not in (T,D) and d>D:continue
            b={"date":d,"open":float(o),"close":float(cl),
               "high":float(hi),"low":float(lo),"volume":float(v)}
            if b["close"]<=0 or b["low"]<=0 or b["low"]>min(b["open"],b["close"]) or b["high"]<max(b["open"],b["close"]) or b["volume"]<0:
                continue
            bars[d]=b
        except (TypeError,ValueError,IndexError):
            continue
    if T not in bars or D not in bars:
        raise ValueError("missing_exact_T_or_D")
    prev,latest=bars[T],bars[D]
    if abs(prev["close"]-anchor["anchor_close"])>0.03:
        raise ValueError("prior_close_anchor_mismatch")
    old=[bars[k] for k in sorted(bars) if k<D][-20:]
    rv=(latest["volume"]/(sum(b["volume"] for b in old)/len(old))) if len(old)==20 and sum(b["volume"] for b in old)>0 else None
    return {"code":code,"name":anchor["name"],"T_close":prev["close"],"D_open":latest["open"],
            "D_high":latest["high"],"D_low":latest["low"],"D_close":latest["close"],
            "D_volume_source_units":latest["volume"],
            "D_pct":round((latest["close"]/prev["close"]-1)*100,5),
            "D_RVOL20":round(rv,5) if rv is not None else None,
            "D_CLV":round((latest["close"]-latest["low"])/(latest["high"]-latest["low"]),5) if latest["high"]>latest["low"] else None,
            "provider":source,"data_date_verified":True}


def collect_one(code,anchor):
    errors={}
    sym=symbol(code)
    methods=[
      ("tencent_legacy","https://web.ifzq.gtimg.cn/appstock/app/kline/kline",{"param":sym+",day,,,90"}),
      ("sina_historical","https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData",
        {"symbol":sym,"scale":240,"ma":"no","datalen":90}),
    ]
    for name,url,params in methods:
        try:
            raw,real=request_json(url,params)
            if name=="tencent_legacy":
                dayrows=(raw.get("data") or {}).get(sym,{}).get("day") or []
            else:
                dayrows=raw if isinstance(raw,list) else []
            result=normalize(dayrows,code,anchor,name)
            result["source_url"]=real
            return result,errors
        except Exception as exc:
            errors[name]=f"{type(exc).__name__}:{str(exc)[:100]}"
            time.sleep(.15)
    return None,errors


def main():
    before=json.loads(BASE.read_text(encoding="utf-8"))
    universe,_,_=prior_universe()
    failed=before.get("all_missing_with_reason")
    if not isinstance(failed,dict) or not (300<len(failed)<1000):
        raise ValueError("original_universe_missing_list_invalid")
    codes=sorted(failed)
    rows=[];errors={}
    with ThreadPoolExecutor(max_workers=7) as pool:
        jobs={pool.submit(collect_one,code,universe[code]):code for code in codes}
        for fut in as_completed(jobs):
            code=jobs[fut]
            try:
                row,fails=fut.result()
                if row:rows.append(row)
                else:errors[code]=fails
            except Exception as exc:errors[code]={"collector_error":str(exc)}
    rows.sort(key=lambda r:r["code"])
    result={"schema_version":1,"D":D,"T":T,
            "retrieved_at_cn":datetime.now(CN).isoformat(timespec="seconds"),
            "first_provider_file":"docs/research/nov02-retrospective-market.json",
            "attempted_original_missing":len(codes),
            "recovered_secondary_daybars":len(rows),"still_missing":len(errors),
            "unrecovered_source_errors":errors,"rows":rows,
            "original_universe_count":before["prior_universe_count"],
            "combined_verified_if_nonoverlap":before["D_bars_verified"]+len(rows),
            "evidence_scope":"historical prior-day quote universe only; not new Nov2 live full-market selection",
            "not_original_full_study":True,"analysis_completed":False,
            "eligible_for_integrated_research":False,
            "order_fills_verified":0,
            "not_backfill_minute_data":True}
    DEST.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("attempted_original_missing","recovered_secondary_daybars","still_missing","combined_verified_if_nonoverlap")}))
    # Data recovered even in partial if >0, and results visibly include all errors.
    return 0 if result["recovered_secondary_daybars"]>=25 else 2

if __name__=="__main__":
    raise SystemExit(main())
