#!/usr/bin/env python3
"""Append the corrected 600567 trigger sequence without rewriting v1/v2."""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
now=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
b=json.loads((ROOT/"research_backfills/linked-volume-price-20261113-v2.json").read_text())
r={**b["research"][0]}
r.update(id="volume-price-20261113-close-v3",run_id="volume-price-20261113-scheduled-close-v3",
         title="量价研究｜11月13日沪深5216只、120广池、28深池与全样本分钟验证（触发顺序修正）",published_at=now,recorded_at=now)
r["body"]=r["body"].replace("发布时间：北京时间 2026-11-13 18:49",f"发布时间：北京时间 {now[:16].replace('T',' ')}",1).replace(
    "回踩守住1.15且板块同步，随后放量站稳1.30","先重新站回1.15且板块同步，之后缩量回踩不破1.15，再观察放量站稳1.30")
r["research_shadow_candidates"]=[dict(x) for x in r["research_shadow_candidates"]]
for c in r["research_shadow_candidates"]:
    c["reviewed_at"]=now
    if c["code"]=="600567":
        c["trigger_condition"]="2026-11-16先重新站回1.15且板块同步，之后缩量回踩不破1.15，再观察放量站稳1.30"
        c["abandon_condition"]="不能重新站回1.15，或站回后放量跌破1.15、板块不同步，即放弃"
receipt={"id":"volume-price-20261113-scheduled-close-v3-completed","run_id":"volume-price-20261113-scheduled-close-v3","task_id":"volume_price","date":"2026-11-13","trigger":"manual_backfill","started_at":now,"recorded_at":now,"completed_at":now,"status":"completed","summary":"修正600567观察顺序为先重新站回1.15、再回踩确认；行情、样本与其余冻结内容不变。","report_ids":[r["id"]],"recommendation_ids":[],"analysis_completed":True,"eligible_for_integrated_research":True,"sources":r["sources"],"blocked_modules":[]}
(ROOT/"research_backfills/linked-volume-price-20261113-v3.json").write_text(json.dumps({"research":[r],"task_runs":[receipt]},ensure_ascii=False,indent=2)+"\n")
print(now)
