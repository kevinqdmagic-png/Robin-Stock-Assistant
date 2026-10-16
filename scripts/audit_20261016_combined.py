#!/usr/bin/env python3
"""Resolve seat identity/date/period joins and capture current issuer notices."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

import collect_20261016_combined as collect
import collect_20261015_combined as helper
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/research/combined-pair-2026-10-16-evidence.json"


def issuer_notices(pair):
    code, name = pair
    params = {"pageNum":1,"pageSize":50,"column":"szse" if code.startswith(("00","30")) else "sse",
              "tabName":"fulltext","seDate":"2026-08-01~2026-10-16","sortName":"time",
              "sortType":"desc","isHLtitle":"true","searchkey":name}
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    req = urllib.request.Request(url,data=urllib.parse.urlencode(params).encode(),headers={
        "User-Agent":"Mozilla/5.0","Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload = json.load(response)
    return {"code":code,"name":name,"source":url,"query":params,
            "retrieved_at":datetime.now(timezone.utc).isoformat(),
            "total_query_hits":payload.get("totalAnnouncement"),
            "announcements":[{k:r.get(k) for k in ("secCode","announcementTitle","announcementTime","adjunctUrl")}
                             for r in payload.get("announcements",[]) if r.get("secCode")==code]}


def fetch_seats(key):
    code, side = key
    params={"reportName":"RPT_BILLBOARD_DAILYDETAILS"+side,"columns":"ALL",
            "filter":f'''(TRADE_DATE='2026-10-16')(SECURITY_CODE="{code}")''',
            "pageNumber":1,"pageSize":500,"sortTypes":"-1","sortColumns":side,
            "source":"WEB","client":"WEB"}
    data=helper.request_json(helper.LHB_EM,params=params,attempts=2)
    if not data.get("success"):
        raise ValueError(data.get("message"))
    rows=(data.get("result") or {}).get("data") or []
    assert all(r.get("SECURITY_CODE")==code and r.get("TRADE_DATE","").startswith("2026-10-16") for r in rows)
    return {"code":code,"side":side,"source_url":helper.LHB_EM+"?"+urllib.parse.urlencode(params),"rows":rows}


def main():
    evidence=load_evidence(PATH)
    # The first fetch was already in flight when the board-aware audit was added.
    # Rebuild only unpublished derived fields; original published history is untouched.
    helper.T="2026-10-16"
    for s in evidence["volume_price"]["deep_samples"]:
        bars=evidence["qfq_daily_histories"][s["code"]]
        s["distance_ma20_pct"]=helper.pct(s["close"],s["ma"]["20"])
        s["prior5_high"]=max(r["high"] for r in bars[-6:-1])
        rate=Decimal("0.20") if s["code"].startswith(("30","68")) else Decimal("0.10")
        s["board_limit_regime"]="20%" if rate==Decimal(".20") else "10%"
        upper=float((Decimal(str(s["previous_close"]))*(1+rate)).quantize(Decimal(".01"),rounding=ROUND_HALF_UP))
        s["calculated_upper_reference"]=upper
        s["calculated_upper_verified_exchange_quote"]=False
        if abs(s["close"]-upper)<.011:
            s["structure"]="封板观察/次日普通成交待核验"
        elif s["clv"]<.65 or s["tail_return_1400_to_1500_pct"] < -1.5:
            s["structure"]="放量冲高回落/承接不足"
        elif s["distance_ma20_pct"]>20 and s["rvol"]["20"]>=3:
            s["structure"]="高乖离高量/分歧风险"
        elif s["range_position_pct"]["120"]<=55:
            s["structure"]="低中位放量推进/待次日承接"
        else:
            s["structure"]="放量推进/待次日承接"
    evidence["volume_price"]["rule_version"]="volume_price_close_v4"
    evidence["volume_price"]["rule_change"]={"date":"2026-10-16","reason":"涨停标签按10%/20%制度和前收舍入计算分开；MA距离统一按含T收盘的MA20，旧版本不回改。计算上限仍不是交易所核验的D日涨停价。"}
    evidence["low_position"]["new_candidates"]=helper.choose_new_low(
        evidence["volume_price"]["deep_samples"],
        {s["code"] for s in json.loads((ROOT/"backend/data/low_position_samples.json").read_text())["items"]})

    offline="--offline" in sys.argv
    notices=evidence.get("issuer_notices",{}) if offline else {}
    errors={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(issuer_notices,p):p[0] for p in ([] if offline else [
            ("600853","龙建股份"),("300719","安达维尔"),("603193","润本股份"),
            ("603334","丰倍生物"),("002437","誉衡药业"),("600825","新华传媒")])}
        for f in as_completed(fs):
            try: notices[fs[f]]=f.result()
            except Exception as exc: errors[fs[f]]=f"{type(exc).__name__}:{exc}"
    evidence["issuer_notices"]=notices
    evidence["issuer_notice_errors"]=errors
    keys=[(r["code"],side) for r in evidence["dragon_tiger"]["selected_observations"] for side in ("BUY","SELL")]
    seats={(r["code"],r["side"]):r for r in evidence["dragon_tiger"].get("raw_seat_queries",[])} if offline else {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(fetch_seats,k):k for k in ([] if offline else keys)}
        for f in as_completed(fs):
            k=fs[f]
            try: seats[k]=f.result()
            except Exception as exc: errors[f"seats_{k[0]}_{k[1]}"]=f"{type(exc).__name__}:{exc}"
    audits=[]
    for s in evidence["dragon_tiger"]["selected_observations"]:
        code=s["code"]
        raw=next(r for r in evidence["dragon_tiger"]["raw_reason_rows_data"] if r["SECURITY_CODE"]==code)
        trade_id=str(raw["TRADE_ID"])
        b=seats.get((code,"BUY"),{}).get("rows",[])
        v=seats.get((code,"SELL"),{}).get("rows",[])
        exact_b=[r for r in b if str(r.get("TRADE_ID"))==trade_id]
        exact_s=[r for r in v if str(r.get("TRADE_ID"))==trade_id]
        if "buy_seats" in s:
            s["unverified_ths_seats"]={"buy":s.pop("buy_seats"),"sell":s.pop("sell_seats"),
                                       "status":"rejected_unmatched_table_period_no_scoring"}
        s["buy_seats_em"]=exact_b
        s["sell_seats_em"]=exact_s
        s["selected_trade_id"]=trade_id
        s["selected_period_reason"]=raw["EXPLANATION"]
        buy_sum=sum(float(r["BUY"]) for r in exact_b)
        sell_sum=sum(float(r["SELL"]) for r in exact_s)
        # SZ summary includes buy/sell amounts on the union of both top-five
        # lists. Deduplicate identical disclosed rows, never all rows sharing
        # the generic label "institution" (which can be different accounts).
        union={ (str(r.get("OPERATEDEPT_CODE")),float(r.get("BUY") or 0),float(r.get("SELL") or 0),str(r.get("TRADE_ID"))):r
                for r in exact_b+exact_s }
        union_buy=sum(float(r.get("BUY") or 0) for r in union.values())
        union_sell=sum(float(r.get("SELL") or 0) for r in union.values())
        s["seat_reconciliation"]={"buy_count":len(exact_b),"sell_count":len(exact_s),
                                  "top5_buy_sum_cny":buy_sum,"top5_sell_sum_cny":sell_sum,
                                  "aggregate_buy_cny":s["buy_cny"],"aggregate_sell_cny":s["sell_cny"],
                                  "buy_difference_cny":round(buy_sum-s["buy_cny"],2),
                                  "sell_difference_cny":round(sell_sum-s["sell_cny"],2),
                                  "union_disclosed_row_count":len(union),"union_buy_cny":union_buy,
                                  "union_sell_cny":union_sell,"union_net_cny":union_buy-union_sell}
        top5_match=abs(buy_sum-s["buy_cny"])<1 and abs(sell_sum-s["sell_cny"])<1
        union_match=abs(union_buy-s["buy_cny"])<1 and abs(union_sell-s["sell_cny"])<1
        s["seat_reconciliation"]["matched"]=len(exact_b)>0 and len(exact_s)>0 and (top5_match or union_match)
        s["seat_reconciliation"]["aggregate_basis"]="union_of_top5_buy_and_sell_rows" if union_match and not top5_match else "top5_each_side"
        s["buy_concentration_top1_pct"]=round(max([float(r["BUY"]) for r in exact_b],default=0)/buy_sum*100,3) if buy_sum else None
        s["sell_concentration_top1_pct"]=round(max([float(r["SELL"]) for r in exact_s],default=0)/sell_sum*100,3) if sell_sum else None
        audits.append({"code":code,"trade_id":trade_id,"reconciliation":s["seat_reconciliation"]})
    evidence["dragon_tiger"]["raw_seat_queries"]=list(seats.values())
    evidence["dragon_tiger"]["seat_period_audit"]=audits
    evidence["audit_completed_at_utc"]=datetime.now(timezone.utc).isoformat()
    PATH.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"audit":audits,"notices":{k:len(v["announcements"]) for k,v in notices.items()},"errors":errors},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
