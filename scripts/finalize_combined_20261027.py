"""Append a separately timed official-notice review; keep the full reports frozen."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import copy
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
T = "2026-10-27"
D = "2026-10-28"
EVIDENCE = "docs/research/combined-pair-20261027-overnight-evidence.json"
MANIFEST = "docs/research/combined-pair-20261027-publication-manifest.json"


def load(path):
    return json.loads((ROOT / path).read_text())


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def main():
    started = "2026-10-27T17:35:14+00:00"
    stamp = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    reports = load("backend/data/research.json")
    runs = load("backend/data/task_runs.json")
    stocks = load("backend/data/research_stocks.json")
    manifest = load(MANIFEST)
    assert not manifest.get("evidence_addendum_report_ids"), "already finalized"
    queries = load("tmp/T27-prepublication-announcement-recheck.json")
    files = load("tmp/T27-overnight-official-files.json")
    assert len(files) == 10 and all(r["ok"] for r in files.values())
    assert all(r["ok"] and r["payload"].get("hasMore") is False for r in queries["items"].values())
    facts = [
        {"code": "001219", "files": ["1225632089"], "fact": "青岛食品公告：华通集团筹划向青啤集团转让5701.7609万股、占29.24%，若完成将涉及控制权变化；尚未签协议，价格等条款仍在磋商，并需国资报批、交易所合规审核及过户。不是已经完成的收购。", "impact": "增加事件催化也增加不确定性。原T26低中位样本的模型、13.08初始失效及所有失败记录不改，新增事件单列；不将隔夜首次核验的信息倒用于T26选样或解释T27盘中已知。不能因事件直接升格为D28打板/综合候选。"},
        {"code": "600838", "files": ["1225632505", "1225632499", "1225632481", "1225632492"], "fact": "上海九百未经审计Q3营收1987.91万元(+7.33%)、归母403.57万元(-12.93%)、扣非471.18万元(-4.37%)；前三季营收6310.44万元(-0.74%)、归母2911.0万元(+2.41%)、扣非2821.32万元(+2.05%)、经营现金流-1414.30万元。每10股拟派0.19元含税，具体权益登记日未公布。公告确认五个交易日涨停累计+61.14%，提示估值和炒作风险；控股股东回函称无应披露未披露重大事项及异动期买卖。", "impact": "单季利润下降、现金流为负与股价加速并存；每股0.019元是分红方案而非既得交易收益。维持高位缩量接力否决，不把分红或最高板当作隔夜安全保证。"},
        {"code": "603528", "files": ["1225631556", "1225631559"], "fact": "多伦科技未经审计前三季营收2.9995亿元(-3.94%)、归母-2771.07万元、扣非-4246.09万元、经营现金流-837.83万元；Q3归母854.96万元但扣非-2354.72万元，单季金融资产公允价值/处置损益3629.02万元。风险公告称10月22—27日累计上涨48.10%，机器人相关业务收入利润占比极小，不涉及人形机器人核心本体、部件研发生产销售。", "impact": "Q3归母转正不是主营盈利反转，非经常性项目不能重复加到利润；负市盈率不与行业正市盈率直接比高低。维持四板高位跟随风险否决。"},
        {"code": "000678", "files": ["1225632038"], "fact": "襄阳轴承公告引用10月26日数据：市净率8.60、汽车制造业1.82；披露2023—2025连续亏损、2026半年亏损2061.23万元。可用于谐波/RV减速器的部分精密轴承累计营收仅16.11万元，占半年营业收入0.023%，尚未盈利。公告称计划10月29日披露三季报。", "impact": "机构/股通同向净买仍不能覆盖高位乖离、题材实际收入小和待披露财报风险；不预判10月29日财务结果。"},
        {"code": "603028", "files": ["1225631944"], "fact": "赛福天公告称10月16日以来累计涨幅58.68%；人形机器人腱绳处于研发和客户送样验证，尚无规模量产及相应收入，批量订单能否落地不确定。半年亏损3243.77万元，最近12个月亏损下的负市盈率不与行业正市盈率直接比较。", "impact": "一字板可见强度与已实现经营业绩不同，继续排除一字排队和高位追板，不认定已有机器人订单兑现。"},
        {"code": "600826", "files": ["1225631664"], "fact": "兰生股份针对10月26—27日异动公告称生产经营与外部环境无重大变化，经自查和函询不存在除已披露事项之外应披露未披露重大信息。", "impact": "这属于公司公告声明，不是对未来没有风险的保证；不能把二板和Q3单季改善补成尚未披露的新催化，仍须核验D28承接。"},
    ]
    urls = [r["source"] for r in files.values()]
    text = [f"原研究日T={T}；计划日D={D}。本次追加核验实际完成于北京时间{stamp}，仅使用此时已取得的原公告。",
            "结论保持：综合组0只、打板v2另组0只。此前18:22完整报告、原样本和参考条件全部保留；本篇是隔夜事实补证，不替代四项前置或生成第二次新名单。",
            "本次重新查询12个准确代码的公告，均无下一页；取得10份新原件。检索范围2026-10-01至10-28，不等于清空全部证券状态、减持、解禁、停复牌风险。文件路径日期10月28日与实际HTTP取得时刻分别保存，不将文件日期当精确首次披露时刻，更不回填T27盘中。"]
    for f in facts:
        text += [f"{f['code']}｜可核验事实：{f['fact']}\n研究影响与限制：{f['impact']}"]
    text += ["两份新三季报原始财务表及青岛控制权筹划页面已视觉核对；九百扫描版股东回函另行视觉读取。公告内容是已披露事实，次日表现尚未发生。没有新增行情、实际触发、成交、收益、胜率或权重调整。",
             "下一观察：青岛若因控制权筹划高开或无可执行成交，不追公告；关注九百和机器人四板负反馈是否扩散；凯中/峨眉山仍仅为原30天研究样本。假设须按原规则前推，不能因新消息回看改名为当初已识别的事件模型。若D28实际买入最早D29可卖，当日炸板不能当天止损。"]
    common = "\n\n".join(text)
    addenda = []
    for task in ("combined_pair", "limitup_single"):
        prefix = task.replace("_", "-")
        rid = prefix + "-20261027-overnight-evidence-v1"
        assert not any(r["id"] == rid for r in reports["items"])
        original = prefix + ("-20261027-close-v2" if task == "limitup_single" else "-20261027-close-v1")
        title = ("打板v2" if task == "limitup_single" else "综合双标") + "｜隔夜公告补证，10月28日空仓裁决保持"
        body = f"本篇归属{task}，关联其原完整报告{original}。两组的候选、规则、样本与收益统计继续独立，复用公告证据不重复计为交易样本。\n\n" + common
        report = {"id":rid,"date":T,"market_date":T,"task_id":task,"track":"market_review","title":title,
                  "summary":"追加青岛控制权筹划、九百/多伦Q3及高标风险公告；原两组各0只保持，不回写旧条件。",
                  "body":body,"sources":urls+[EVIDENCE],"report_type":"evidence_update","eligible_for_integrated_research":False,
                  "analysis_completed":True,"status":"completed","published_at":stamp,"recorded_at":stamp,"data_cutoff_at":stamp,
                  "planned_entry_date":D,"earliest_legal_exit_date_if_bought":"2026-10-29","candidate_count":0,"recommendation_ids":[],
                  "decision_unchanged":True,"related_report_ids":[original],"codes":[f["code"] for f in facts],"evidence_file":EVIDENCE,
                  "research_rule_version":"limitup_single_v2" if task=="limitup_single" else "combined_limitup_watch_v5"}
        reports["items"].append(report)
        # Evidence completion must not masquerade as a new complete daily module
        # in delivery_health's current receipt-level analysis_completed check.
        runs["items"].append({"id":rid+"-run-completed","run_id":rid+"-run","task_id":task,"date":T,"trigger":"scheduled",
                              "started_at":started,"completed_at":stamp,"recorded_at":stamp,"status":"completed",
                              "summary":report["summary"],"report_ids":[rid],"recommendation_ids":[],"analysis_completed":False,
                              "evidence_review_completed":True,"analysis_scope":"supplementary_notice_review_not_new_full_daily_module",
                              "eligible_for_integrated_research":False,"delivery_status":"repository_prepared_not_yet_ci_or_production_verified",
                              "sources":[EVIDENCE]})
        addenda.append(report)
    stock = next(s for s in stocks["items"] if s["code"] == "001219")
    episode = {"id":"research-stock-001219-20261027-overnight-v1","date":T,"recorded_at":stamp,
               "title":"控制权变更筹划新增事实，原低位样本不回写",
               "reason":facts[0]["fact"],"evidence_status":"official_notice_verified_transaction_not_completed",
               "fact_note":"本次隔夜方核验；不是T26冻结样本当时已知的选样依据，未签约及审批过户均未完成。",
               "validation":["原13.08收盘失效位及原低中位模型继续前推","控制权筹划单列事件，不与普通隔夜/原模型混算"],
               "risk":"事件溢价和失败/延期风险并存；涨停或高开无成交证据不记买入，不据公告改为D28推荐。",
               "report_ids":[r["id"] for r in addenda],"sources":[u for u in urls if "1225632089" in u]+[EVIDENCE]}
    stock["history"].append(episode)
    stocks["updated_at"] = stamp
    evidence = {"market_date":T,"planned_entry_date":D,"actual_started_at_utc":started,"actual_completed_at":stamp,
                "queries":queries,"official_files":{k:{a:b for a,b in r.items() if a not in ("local_pdf","local_text")} for k,r in files.items()},
                "verified_fact_notes":facts,"decision_unchanged":True,"new_trade_candidates":0,"new_trade_samples":0,
                "stock_history_updates":[{"code":"001219","history_id":episode["id"]}],
                "resume_live_snapshot":load("tmp/T27-resumption-live.json"),"no_changes_to_frozen_reports_or_rules":True}
    # Correct pre-publication source bookkeeping, without changing its analysis.
    # The actual two previous pools were reused from the T26 frozen bundle.
    prior_path = "docs/research/combined-pair-20261026-evidence.json.gz"
    prior_bytes = (ROOT/prior_path).read_bytes()
    prior = json.loads(gzip.decompress(prior_bytes))
    packed_path = manifest["evidence_file"]
    packed = json.loads(gzip.decompress((ROOT/packed_path).read_bytes()))
    packed["prior_pool_reuse"] = [prior_path]
    packed["prior_pool_reuse_sha256"] = hashlib.sha256(prior_bytes).hexdigest()
    for day in ("2026-10-23", "2026-10-26"):
        packed["limit_up_pools"][day] = {**copy.deepcopy(prior["limit_up_pools"][day]),"reused_from":prior_path}
    packed_bytes = gzip.compress(json.dumps(packed,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode(),mtime=0)
    manifest["evidence_sha256"] = hashlib.sha256(packed_bytes).hexdigest()
    manifest["evidence_addendum_report_ids"] = [r["id"] for r in addenda]
    manifest["evidence_addendum_completed_at"] = stamp
    manifest["evidence_addendum_file"] = EVIDENCE
    manifest["evidence_addendum_stock_history_updates"] = evidence["stock_history_updates"]
    evidence_text = encode(evidence)
    manifest["evidence_addendum_sha256"] = hashlib.sha256(evidence_text.encode()).hexdigest()
    writes = {"backend/data/research.json":reports,"backend/data/task_runs.json":runs,
              "backend/data/research_stocks.json":stocks,"app/src/main/assets/research_stocks.json":stocks,MANIFEST:manifest}
    serialized = {p:encode(v) for p,v in writes.items()}
    assert datetime.fromisoformat(started) < datetime.fromisoformat(stamp) <= datetime.now(timezone.utc)
    for p,body in serialized.items():
        target=ROOT/p;temp=target.with_suffix(target.suffix+".tmp");temp.write_text(body);temp.replace(target)
    (ROOT/packed_path).write_bytes(packed_bytes)
    (ROOT/EVIDENCE).write_text(evidence_text)
    for r in addenda:
        (ROOT/("docs/research/"+r["id"]+".md")).write_text("# "+r["title"]+"\n\n"+r["body"]+"\n\n来源：\n\n"+"\n".join("- "+s for s in r["sources"])+"\n")
    print(json.dumps({"added_reports":manifest["evidence_addendum_report_ids"],"actual_completed_at":stamp,
                      "stock_history_update":episode["id"],"original_decisions_unchanged":True},ensure_ascii=False))


if __name__ == "__main__":
    main()
