#!/usr/bin/env python3
"""Intraday research execution gate. No unsupported stock picks or archive writes.

Runs in GitHub Actions at 09:50/14:40 Beijing time. Produces an auditable
JSON outcome; actual selection requires a separately verified market-data
adapter, which is intentionally not fabricated here.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from trading_calendar import session_state

CN_TZ = ZoneInfo("Asia/Shanghai")
SLOTS = {"early_pair": (9, 50), "late_pair": (14, 40)}


def evaluate(slot, now=None):
    if slot not in SLOTS:
        raise ValueError("invalid_intraday_slot")
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    state = session_state(now)
    hour, minute = SLOTS[slot]
    minutes_late = (now.hour * 60 + now.minute) - (hour * 60 + minute)
    outcome = {
        "task_id": slot, "checked_at": now.isoformat(), "market_date": now.date().isoformat(),
        "market_state": state["code"], "recommendations": [],
        "market_data_verified": False,
    }
    if state["code"] != "trading":
        outcome.update(status="skipped", reason="not_a_verified_trading_session")
    elif not 0 <= minutes_late <= 25:
        outcome.update(status="skipped", reason="outside_intraday_execution_window")
    else:
        outcome.update(status="insufficient_evidence",
                       reason="no_verified_live_market_data_adapter_configured")
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", required=True, choices=sorted(SLOTS))
    parser.add_argument("--output", default="intraday_outcome.json")
    args = parser.parse_args()
    result = evaluate(args.slot)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
