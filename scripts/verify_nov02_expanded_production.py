#!/usr/bin/env python3
"""Exact-SHA production verification for Nov2 new full-source partial research."""
import json
import os
import time
from urllib.request import urlopen
from urllib.parse import urlencode

BASE="https://robin-stock-api-production.up.railway.app"
DAY="2026-11-02"
TASKS=("market_review","volume_price","low_position")
PREFIX="nov02-combined-source-20261103"
OLDER="nov02-real-source-recovery-20261103"

def get(path,**qs):
    url=BASE+path+("?" + urlencode(qs) if qs else "")
    with urlopen(url,timeout=15) as response:j=json.load(response)
    if j.get("ok") is not True:raise AssertionError("bad_api_response:"+path)
    return j

def run(expected):
    health=get("/health")
    if health.get("build_commit")!=expected:raise AssertionError("not_deployed:"+str(health.get("build_commit")))
    archive=get("/api/research",date=DAY,limit=100)
    byid={r.get("id"):r for r in archive.get("items",[])}
    verified={}
    for task in TASKS:
        reportid=PREFIX+"-"+task+"-report"
        row=byid.get(reportid)
        if not row or row.get("status")!="partial" or row.get("analysis_completed") is not False or row.get("eligible_for_integrated_research") is not False:
            raise AssertionError("report_absent_or_false_complete:"+reportid)
        receipts=get("/api/task-runs",task=task,limit=100)
        receiptid=PREFIX+"-"+task+"-receipt"
        original=next((r for r in receipts.get("items",[]) if r.get("id")==receiptid),None)
        if not original or original.get("status")!="partial" or reportid not in original.get("report_ids",[]):
            raise AssertionError("receipt_missing_or_false_complete:"+receiptid)
        verified[task]=reportid
    for task in ("dragon_tiger","volume_price"):
        rid=OLDER+"-"+task+"-report"
        row=byid.get(rid)
        if not row or row.get("status")!="partial":
            raise AssertionError("previous_LHB_or_minute_partial_missing:"+rid)
    matrix=get("/api/operations/delivery")
    if matrix.get("date_cn")!=DAY or matrix.get("verified_count")!=0:
        raise AssertionError("delivery_matrix_improper_full_claim")
    if set(matrix.get("unverified_task_ids",[]))!=set(("market_review","volume_price","low_position","dragon_tiger","combined_pair","limitup_single")):
        raise AssertionError("delivery_matrix_wrong_unfulfilled")
    return {"status":"VERIFIED_SOURCE_REPORTS_LIVE","build_sha":expected,
            "partial_report_ids":list(verified.values()),"verified_full_studies":0,
            "full_studies_required":6,"LHB_and_minute_partial_present":True}

if __name__=="__main__":
    expected=os.environ["GITHUB_SHA"]
    for attempt in range(12):
        try:
            print(json.dumps(run(expected),ensure_ascii=False))
            raise SystemExit(0)
        except Exception as exc:
            print("retry",attempt+1,type(exc).__name__,str(exc)[:240],flush=True)
            if attempt==11:raise
            time.sleep(12)
