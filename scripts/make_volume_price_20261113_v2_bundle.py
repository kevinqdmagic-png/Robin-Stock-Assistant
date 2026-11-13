#!/usr/bin/env python3
"""Append a schema-correct v2 without rewriting the frozen v1 research."""
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
now=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
items=json.loads((ROOT/"backend/data/research.json").read_text())["items"]
old=next(x for x in items if x.get("id")=="volume-price-20261113-close-v1")
body=old["body"].replace("研究交易日：2026-11-13｜发布时间：北京时间 2026-11-13 18:41（UTC+8）",f"研究交易日：2026-11-13｜发布时间：北京时间 {now[:16].replace('T',' ')}（UTC+8）",1)
pair=[]
for c in old["research_shadow_candidates"]:
    pair.append({
        "task_id":"volume_price","code":c["code"],"name":c["name"],
        "candidate_status":"module_research_observation","qualification":"待综合观察；非最终双标、非正式买点",
        "reference_price":c["reference_price"],"reference_as_of":c["reference_time"],
        "actual_frozen_at":old["published_at"],"reviewed_at":now,"planned_observation_date":"2026-11-16",
        "hypothesis":"量价分歧后承接与再转强代理需在观察日继续前推验证",
        "trigger_condition":c["trigger"],"abandon_condition":c["invalid"],
        "risk":"盘后量价相对优选不等于正式买点；高开、板块背离、跌停/停牌及T+1当日不可卖风险保留。",
        "formal_buy_signal":False,"buy_order_allowed":False,
        "earliest_legal_exit_if_entered":"2026-11-17"
    })
report={**old,"id":"volume-price-20261113-close-v2","run_id":"volume-price-20261113-scheduled-close-v2","title":"量价研究｜11月13日沪深5216只、120广池、28深池与全样本分钟验证（契约修正版）","body":body,
        "report_type":"full_daily_research","published_at":now,"recorded_at":now,"research_shadow_candidates":pair,
        "sources":[s.replace("backend/data/sina_daily_full/2026-11-13.json","backend/data/sina_daily_full/2026-11-13.json.gz") for s in old["sources"]]}
receipt={"id":"volume-price-20261113-scheduled-close-v2-completed","run_id":"volume-price-20261113-scheduled-close-v2","task_id":"volume_price","date":"2026-11-13","trigger":"manual_backfill",
         "started_at":now,"recorded_at":now,"completed_at":now,"status":"completed",
         "summary":"追加契约修正版：同一已完成研究使用full_daily_research与APP候选字段；不改写v1和原冻结。","report_ids":[report["id"]],"recommendation_ids":[],
         "analysis_completed":True,"eligible_for_integrated_research":True,"sources":report["sources"],"blocked_modules":[]}
target=ROOT/"research_backfills/linked-volume-price-20261113-v2.json"
target.write_text(json.dumps({"research":[report],"task_runs":[receipt]},ensure_ascii=False,indent=2)+"\n")
print(now,target)
