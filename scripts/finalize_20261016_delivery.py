"""Merge concurrent audit receipts and append a truthful late-delivery note.

Original research, decision, prices and signal timestamps remain immutable.
No deployment success is asserted by this local archive operation.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

from audit_20261016_combined import issuer_notices

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend/data"
T = "2026-10-16"
BASE = "69bc22b4e08053fff3b4f6c8a92d98ddb924bea6"
ADDENDUM = "combined-pair-20261016-delivery-addendum-v1"
EVIDENCE = "docs/research/combined-pair-20261016-delivery-evidence-v1.json"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    research = load("research.json")
    if any(r["id"] == ADDENDUM for r in research["items"]):
        print("Late-delivery addendum already frozen; no changes.")
        return
    phase_started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    latest = json.loads(subprocess.check_output(
        ["git", "show", BASE + ":backend/data/task_runs.json"], cwd=ROOT))
    local = load("task_runs.json")
    incoming = {r["id"]: r for r in latest["items"]}
    for event in local["items"]:
        if event["id"] in incoming and event != incoming[event["id"]]:
            raise ValueError("Concurrent receipt changed: " + event["id"])
    merged = dict(latest)
    merged["items"] = latest["items"] + [r for r in local["items"] if r["id"] not in incoming]
    notices = issuer_notices(("000887", "中鼎股份"))
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    cn = now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    latest_notice = max((a["adjunctUrl"] for a in notices["announcements"]), default="")
    # Scope is explicit: a name-based first-page query, exactly filtered by code.
    # No search result is promoted to an unannounced issuer development.
    has_after_oct8 = any("2026-10-" in a["adjunctUrl"] and
                         a["adjunctUrl"].split("/")[1] > "2026-10-08"
                         for a in notices["announcements"])
    if has_after_oct8:
        raise ValueError("New issuer disclosure requires substantive review before publication")
    evidence = {"research_date": T, "recorded_at": stamp,
                "delivery_phase_started_at": phase_started, "base_main_sha": BASE,
                "issuer_notice_recheck": notices,
                "status": "local_archive_prepared_ci_and_production_pending",
                "original_analysis_completed_at": "2026-10-16T18:01:18+08:00",
                "frozen_decision_id": "combined-pair-20261016-close-v1",
                "latest_notice_in_checked_scope": latest_notice,
                "correction": {"code": "601091", "correct_name": "沈鼓集团",
                    "incorrect_label": "中泰国际", "deep_pool_member": False,
                    "reason_missing_qfq_T": "not_verified_do_not_infer_IPO",
                    "source": "https://data.10jqka.com.cn/market/longhu/"}}
    body = f"""本说明记录于北京时间{cn}，研究交易日仍为T=2026-10-16。

一、实际完成与交付分开

四模块及综合决策原文于2026-10-16 18:01:18北京时间冻结在本地；当时尚未推送、通过CI或上线，不能称APP已同步。最新main {BASE}已追加21:16:55的未交付审计，该审计准确描述当时线上缺少报告的状态，原文全部保留。本次合并这些并发记录，并追加实际归档阶段回执；不把它们回填成18点已上线。完整报告、原始条件和旧回执不改写。当前脚本只完成本地原子提交的准备，CI、容器和Railway终态/API仍须随后核验。

二、晚间公告复核，不重新推荐

中鼎股份000887的巨潮公告接口按2026-08-01至10月16日、名称检索首50条并按代码精确过滤，抓取时间和全部返回行在{EVIDENCE}。本次可见最新正式公告仍为10月8日可转债注册稿/财务数据更新，未发现10月16日新增正式公告；不等于保证不存在未检索到或未来披露的消息。腾讯云框架合作未产生收入的8月风险提示仍有效。没有足以变更原条件的新核验事实，本次保留原唯一决策、17.72收盘参考、10月19日条件观察及最早20日退出计划；不是新选股或第二次推荐。

三、非入选代码名称勘误

原量价正文将601091写为“中泰国际”，正确证券简称为沈鼓集团。该代码原价历史取得，但前复权历史未含T，具体原因未核实，不应凭此断言IPO。它不在28只深筛和最终候选内，不影响中鼎股份的原报价、相对量或条件。保留原报告并追加本勘误，不覆盖历史正文。

四、原始证据可复算与打板未完成范围

较大的完整原始行情JSON按原字节无损gzip留档，SHA-256及原字节数记录在同名可读JSON；113只原价、112只前复权历史和54只五日价格路径均保留。打包不改变任何冻结字段。

独立打板D=10月16日仍缺事前冻结及完整v2逐层名单/盘口证据；已有盘后审计不冒称按时完成，也不补造当日候选/成交。D=10月19日尚无新的完整盘前报告，不能拿本综合条件股冒充打板样本。原任务时间/启停不改变；周末不生成新的交易日报告。
"""
    report = {"id": ADDENDUM, "date": T, "market_date": T,
              "task_id": "combined_pair", "track": "market_review",
              "title": "10月16日综合双标：迟到交付、晚间复核与名称勘误（非新决策）",
              "summary": "保留18:01原始冻结与21:16未交付审计；追加真实归档时间，公告复核不改原中鼎条件；601091名称勘误；打板事前缺报仍blocked。",
              "body": body, "recorded_at": stamp, "published_at": cn,
              "report_type": "publication_audit", "eligible_for_integrated_research": False,
              "sources": [notices["source"], "https://data.10jqka.com.cn/market/longhu/",
                          "https://static.cninfo.com.cn/finalpage/2026-08-13/1225470157.PDF", EVIDENCE],
              "evidence_file": EVIDENCE,
              "amends_report_ids": ["volume-price-20261016-close-v1", "combined-pair-20261016-close-v1"]}
    research["items"].append(report)
    for task in ("volume_price", "low_position", "dragon_tiger", "combined_pair", "limitup_single"):
        original_id = ("limitup-single-20261016-retro-audit-blocked" if task == "limitup_single" else
                       task.replace("_", "-") + "-20261016-scheduled-093718z-completed")
        original = next(r for r in merged["items"] if r["id"] == original_id)
        event = dict(original)
        event.update(id=original["run_id"] + "-late-archive-v1", recorded_at=stamp,
                     completed_at=stamp, analysis_completed_at=original["completed_at"],
                     delivery_phase_started_at=phase_started,
                     delivery_status="archive_prepared_ci_and_production_pending",
                     summary=("迟到归档；原分析18:01完成，但21:16审计时尚未交付。" + original["summary"] +
                              "本回执不声称CI或生产已核验。"))
        if task == "combined_pair":
            event["report_ids"] = original["report_ids"] + [ADDENDUM]
        event["sources"] = original["sources"] + [EVIDENCE]
        merged["items"].append(event)
    catalog = load("research_stocks.json")
    stock = next(s for s in catalog["items"] if s["code"] == "000887")
    stock["history"].append({
        "id": "research-stock-000887-20261016-late-recheck", "date": T, "recorded_at": stamp,
        "title": "晚间公告补查：不改变原条件", "reason": "中鼎股份检索范围内最新公告仍为10月8日；未核实新的公司级催化，保留原10月19日严格条件而非新增推荐。",
        "evidence_status": "issuer_notice_recheck_no_material_change_in_checked_scope",
        "fact_note": "公告检索有范围限制；原冻结时间不等于线上交付时间。",
        "validation": ["10月19日竞价、证券状态、普通成交及先回踩后转强仍须重新核验；未满足不认定成交。"],
        "risk": "周末消息、可转债、未收复MA20和高开兑现风险不因补查消除。",
        "report_ids": [ADDENDUM], "sources": [EVIDENCE, notices["source"]]})
    save(ROOT / EVIDENCE, evidence)
    save(DATA / "research.json", research)
    save(DATA / "task_runs.json", merged)
    save(DATA / "research_stocks.json", catalog)
    save(ROOT / "app/src/main/assets/research_stocks.json", catalog)
    (ROOT / "docs/research" / (ADDENDUM + ".md")).write_text(body, encoding="utf-8")
    print(json.dumps({"recorded_at": stamp, "merged_main": BASE,
                      "original_decision_unchanged": True, "report_id": ADDENDUM}))


if __name__ == "__main__":
    main()
