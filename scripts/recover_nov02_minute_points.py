#!/usr/bin/env python3
"""Collect previous-session date-verified *minute PRICE POINTS* for frozen T30 pool.

No auction, OHLC inside each minute, actual orderbook or fill is inferred.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CN=ZoneInfo("Asia/Shanghai")
DAY="2026-11-02"
DOC=ROOT/"docs/research/shadow-experiments-20261102-v1.json"
POOL=ROOT/"docs/research/market-review-2026-10-30-evidence.json"
DEST=ROOT/"docs/research/nov02-frozen-minute-points.json"


def symbol(code):
    return ("bj" if code.startswith(("4","8","92")) else "sh" if code.startswith(("5","6","9")) else "sz")+code


def query(code):
    s=symbol(code)
    url="https://web.ifzq.gtimg.cn/appstock/app/minute/query?"+urlencode({"code":s})
    last=None
    for attempt in range(2):
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://gu.qq.com/"}),timeout=14) as rsp:
                payload=json.load(rsp)
            d=(payload.get("data") or {}).get(s,{})
            content=d.get("data") or {}
            provider_date=str(content.get("date") or "")
            if provider_date.replace("-","") != DAY.replace("-",""):
                raise ValueError("wrong_provider_minute_date:"+provider_date)
            points=[]
            for item in content.get("data") or []:
                fields=str(item).split()
                if len(fields)<3:continue
                clock=fields[0]
                if not clock.isdigit() or len(clock)!=4:continue
                price=float(fields[1])
                volume=float(fields[2])
                amount=float(fields[3]) if len(fields)>3 else None
                if price<=0 or volume<0:continue
                # Tencent cumulative lots; VWAP is a derived proxy when amount valid.
                vwap=(amount/volume/100) if volume>0 and amount is not None else None
                points.append({"clock":clock,"price":price,
                               "cumulative_volume_lots":volume,
                               "cumulative_amount_cny":amount,
                               "cumulative_vwap_proxy":round(vwap,5) if vwap else None})
            if len(points)<150:raise ValueError("incomplete_intraday_price_points")
            points.sort(key=lambda r:r["clock"])
            if points[-1]["clock"]<"1450":raise ValueError("missing_late_session")
            return {"code":code,"source":url,"date_verified":True,"provider_date":provider_date,
                    "retrieved_at_cn":datetime.now(CN).isoformat(timespec="seconds"),
                    "point_count":len(points),"points":points,"verified_orderbook":False,
                    "auction_0925":None,"minute_ohlc":False,"order_fills":[]}
        except Exception as exc:
            last=f"{type(exc).__name__}: {str(exc)[:100]}"
            if attempt==0:time.sleep(.3)
    raise ValueError(last)


def main():
    sh=json.loads(DOC.read_text())
    pool=json.loads(POOL.read_text())
    assert sh["T"]=="2026-10-30" and sh["planned_D"]==DAY
    shadow={s["code"]:s for s in sh["signals"]}
    controls={s["code"] for s in sh.get("controls",[])}
    deep={s["code"] for s in pool["deep_pool"]}
    codes=sorted(deep|controls|set(shadow))
    got,errors={},{}
    with ThreadPoolExecutor(max_workers=5) as workers:
        jobs={workers.submit(query,code):code for code in codes}
        for fut in as_completed(jobs):
            c=jobs[fut]
            try:got[c]=fut.result()
            except Exception as exc:errors[c]=str(exc)
    frozen_checks=[]
    for c,signal in shadow.items():
        record=got.get(c)
        checkpoints={}
        if record:
            points={p["clock"]:p for p in record["points"]}
            for t in ("0925","0930","0945","0950","1030","1130","1400","1430","1440","1500"):
                point=points.get(t)
                checkpoints[t]=({"price":point["price"],"vwap_proxy":point["cumulative_vwap_proxy"],
                                 "above_cumulative_vwap_proxy":point["price"]>=point["cumulative_vwap_proxy"]
                                 if point["cumulative_vwap_proxy"] is not None else None} if point else None)
        frozen_checks.append({
          "code":c,"original_signal_id":signal.get("id"),"original_frozen_at":signal.get("signal_frozen_at"),
          "trigger":signal.get("trigger"),"invalid":signal.get("invalid"),
          "original_minute_price_checkpoints":checkpoints,
          "all_trigger_conditions_met":None,
          "all_invalid_conditions_met":None,
          "why_not_definitive":"Auction 09:25 and actual bid/ask queue order missing; price points not confirmed trade execution",
          "verified_fill":False})
    out={"schema_version":1,"target_session":DAY,"prior_session":"2026-10-30",
         "actual_retrieved_at_cn":datetime.now(CN).isoformat(timespec="seconds"),
         "universe_predefined_by":"docs/research/market-review-2026-10-30-evidence.json and shadow-experiments-20261102-v1.json",
         "requested_count":len(codes),"verified_count":len(got),"errors":errors,
         "deep_count":len(deep),"shadow_count":len(shadow),
         "source_provider":"Tencent public most-recent trading-session minute price points",
         "source_date_explicitly_verified":True,"is_minute_OHLC":False,
         "is_real_order_fill_evidence":False,"historical_source_not_contemporaneous_capture":True,
         "all_A_share_coverage":False,"analysis_completed":False,
         "eligible_for_integrated_research":False,"sample_series":got,
         "frozen_shadow_conditions":frozen_checks,
         "missing":["09:25 auction","per-minute OHLC","bid/ask queue","real order fills","full market price paths"]}
    DEST.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({"requested":out["requested_count"],"verified":out["verified_count"],
                      "errors":out["errors"],"frozen_shadow_conditions":frozen_checks},ensure_ascii=False))
    return 0 if len(got)>=int(len(codes)*.8) else 2

if __name__=="__main__":
    raise SystemExit(main())
