#!/usr/bin/env python3
"""Archive dated public ladders and short, hash-verifiable issuer facts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

from audit_20261016_combined import issuer_notices
from collect_20261015_combined import request_bytes, request_json
from research_evidence_io import load_evidence

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"docs/research/combined-pair-2026-10-16-evidence.json"


def ladder(day):
    url=f"https://lianban.net/days/{day}.html"
    meta=request_json(f"https://lianban.net/opendata/{day}.json",attempts=2)
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://lianban.net/"})
    with urllib.request.urlopen(req,timeout=30) as response:
        html=response.read().decode()
    marker=re.search(r"\b(?:var|let|const)\s+S\s*=\s*",html)
    if not marker:
        return {"date":day,"source":url,"public_metadata":meta,"stocks":{},
                "error":"public_page_stock_table_not_found","html_bytes":len(html),
                "page_title":re.search(r"<title>(.*?)</title>",html,re.S).group(1) if "<title>" in html else None}
    stocks,_=json.JSONDecoder().raw_decode(html[marker.end():])
    return {"date":day,"source":url,"license":"CC BY 4.0；连板网，附原文链接",
            "public_metadata":meta,"stocks":stocks,"retrieved_at":datetime.now(timezone.utc).isoformat()}


def main():
    evidence=load_evidence(PATH)
    contexts={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(ladder,d):d for d in ["2026-10-13","2026-10-14","2026-10-15","2026-10-16"]}
        for f in as_completed(fs):
            try: contexts[fs[f]]=f.result()
            except Exception as exc: contexts[fs[f]]={"error":f"{type(exc).__name__}:{exc}"}
    evidence["limitup_market_contexts"]=contexts
    if "--context-only" in sys.argv:
        PATH.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({d:{"stocks":len(c.get("stocks",{})),"kpi":c.get("public_metadata",{}).get("kpi"),"error":c.get("error")} for d,c in contexts.items()},ensure_ascii=False,indent=2))
        return
    evidence["issuer_notices"]["000887"]=issuer_notices(("000887","中鼎股份"))
    facts=[]
    urls=[
        "https://static.cninfo.com.cn/finalpage/2026-08-13/1225470157.PDF",
        "https://static.cninfo.com.cn/finalpage/2026-10-08/1225591062.PDF",
        "https://static.cninfo.com.cn/finalpage/2026-08-29/1225527759.PDF",
        "https://static.cninfo.com.cn/finalpage/2026-10-13/1225601289.PDF",
        "https://static.cninfo.com.cn/finalpage/2026-10-13/1225601803.PDF",
        "https://static.cninfo.com.cn/finalpage/2026-10-16/1225607741.PDF"]
    for url in urls:
        try:
            data=request_bytes(url,timeout=25)
            text=subprocess.run(["pdftotext","-","-"],input=data,check=True,capture_output=True).stdout.decode()
            facts.append({"source":url,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),
                          "header_and_fact_excerpt":text[:1700],"verified_at":datetime.now(timezone.utc).isoformat()})
        except Exception as exc: facts.append({"source":url,"error":f"{type(exc).__name__}:{exc}"})
    evidence["issuer_primary_pdf_checks"]=facts
    evidence["context_retrieved_at"]=datetime.now(timezone.utc).isoformat()
    PATH.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"contexts":{d:{"stocks":len(c.get("stocks",{})),"kpi":c.get("public_metadata",{}).get("kpi"),"error":c.get("error")} for d,c in contexts.items()},
                      "pdf_checks":[{"url":p["source"],"ok":"error" not in p} for p in facts]},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
