#!/usr/bin/env python3
"""Recover date-exact public Eastmoney Choice LHB list and disclosed branch rows.

The source is a public vendor reprint of disclosures, NOT verified original
exchange-seat PDFs; absence of rows is never evidence of no institutional sales.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-02"
EM = "https://datacenter-web.eastmoney.com/api/data/v1/get"
CN = ZoneInfo("Asia/Shanghai")
DEST = ROOT / "docs/research/nov02-lhb-historical-seats.json"


def query(report_name, filters, page=1, page_size=500):
    params = {"reportName": report_name, "columns":"ALL", "filter": filters,
              "pageSize":page_size, "pageNumber":page, "source":"WEB","client":"WEB"}
    if report_name=="RPT_DAILYBILLBOARD_DETAILS":
        params["sortColumns"]="SECURITY_CODE"
        params["sortTypes"]=1
    url=EM+"?"+urlencode(params)
    last=None
    for attempt in range(3):
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://data.eastmoney.com/"})
            with urlopen(req,timeout=18) as rsp:
                obj=json.load(rsp)
            if obj.get("success") is not True:
                raise ValueError("source_returned_not_success:"+str(obj.get("message"))[:80])
            result=obj.get("result") or {}
            rows=result.get("data")
            if not isinstance(rows,list):
                raise ValueError("no_list_rows")
            return {"ok":True,"retrieved_at":datetime.now(CN).isoformat(timespec="seconds"),
                    "source":url,"total":result.get("count"),"pages":result.get("pages"),
                    "rows":rows}
        except Exception as e:
            last=f"{type(e).__name__}:{str(e)[:140]}"
            if attempt<2:
                time.sleep(0.75*(attempt+1))
    return {"ok":False,"source":url,"error":last,"rows":[]}


def collect():
    first=query("RPT_DAILYBILLBOARD_DETAILS",f"(TRADE_DATE='{DAY}')")
    result={"schema_version":1,"trade_date":DAY,
            "actual_collected_at":datetime.now(CN).isoformat(timespec="seconds"),
            "source":"Eastmoney data center, public copy of exchange disclosure",
            "primary_exchange_originals_verified":False,
            "sector_specific_rules_verified":False,
            "verified_account_identity":False,
            "not_real_time_orderflow":True,
            "not_full_original_daily_research":True,
            "analysis_completed":False,"eligible_for_integrated_research":False,
            "main_list":first,"other_list_pages":[],"seat_queries":{},
            "unique_codes":0,"seat_covered_codes":0,"failed_codes":{},
            "raw_entry_reason_count":0,
            "missing":["original exchange PDFs / trade reason reconciliation",
                       "historical order/auction/fill evidence",
                       "cross-provider exact disclosures and original securities status"]}
    if first.get("ok"):
        data=list(first["rows"])
        pages=int(first.get("pages") or 1)
        if not 1<=pages<=30:
            raise ValueError("unexpected_lhb_pagination")
        for p in range(2,pages+1):
            page=query("RPT_DAILYBILLBOARD_DETAILS",f"(TRADE_DATE='{DAY}')",page=p)
            result["other_list_pages"].append(page)
            if page["ok"]: data.extend(page["rows"])
        codes=sorted({str(r.get("SECURITY_CODE")) for r in data
                      if str(r.get("SECURITY_CODE","")).isdigit()
                      and len(str(r.get("SECURITY_CODE")))==6
                      and not str(r.get("SECURITY_CODE")).startswith(("200","900"))})
        result["unique_codes"]=len(codes)
        result["raw_entry_reason_count"]=len(data)
        seat_requests=[(c,side) for c in codes for side in ("BUY","SELL")]
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures={pool.submit(query,"RPT_BILLBOARD_DAILYDETAILS"+side,
                        f"(TRADE_DATE='{DAY}')(SECURITY_CODE=\"{code}\")",1,100):(code,side)
                     for code,side in seat_requests}
            for fut in as_completed(futures):
                code,side=futures[fut]
                value=fut.result()
                result["seat_queries"].setdefault(code,{})[side]=value
        good=[]
        for code,parts in result["seat_queries"].items():
            failures={side:rs.get("error") for side,rs in parts.items() if not rs["ok"]}
            if failures:result["failed_codes"][code]=failures
            elif all(rs.get("ok") for rs in parts.values()):good.append(code)
        result["seat_covered_codes"]=len(good)
        result["returned_rows"]=len(data)
        result["list_missing_pages"]=[p+2 for p,v in enumerate(result["other_list_pages"]) if not v["ok"]]
    result["seat_coverage_status"]="vendor_copy_only_not_original_exchange"
    result["trigger_or_fill_verification"]=False
    DEST.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("trade_date","unique_codes","seat_covered_codes","raw_entry_reason_count","failed_codes")},ensure_ascii=False))
    if not first["ok"]:return 2
    # If external provider fails majority, retain audit but do not publish as a source-complete record.
    return 0 if result["unique_codes"]>=55 and result["seat_covered_codes"]>=int(result["unique_codes"]*.8) else 2


if __name__=="__main__":
    raise SystemExit(collect())
