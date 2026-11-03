"""Read-only BaoStock feasibility probe; never writes research receipts.

Run: python scripts/probe_baostock.py [YYYY-MM-DD]
This is a diagnostic, not a production fallback. The BaoStock socket service
may be blocked in Railway; only enable a runtime fallback after measuring it.
"""
import json
import sys
from datetime import date

def main():
    try:
        import baostock as bs
    except ImportError:
        print(json.dumps({"ok": False, "status": "dependency_missing", "install": "pip install baostock"}))
        return 2
    day = date.fromisoformat(sys.argv[1]).isoformat() if len(sys.argv) > 1 else date.today().isoformat()
    result = {"ok": False, "requested_date": day, "provider": "baostock", "scope": "single_stock_probe"}
    login = bs.login()
    try:
        if login.error_code != "0":
            result.update(status="login_failed", error_code=login.error_code, error=login.error_msg)
            return 1
        cal = bs.query_trade_dates(start_date=day, end_date=day)
        if cal.error_code != "0":
            result.update(status="calendar_failed", error_code=cal.error_code)
            return 1
        calendar_rows = []
        while cal.next():
            calendar_rows.append(cal.get_row_data())
        result["calendar"] = calendar_rows
        rows = bs.query_history_k_data_plus(
            "sh.600000", "date,code,open,high,low,close,volume,amount,tradestatus",
            start_date=day, end_date=day, frequency="d", adjustflag="3")
        if rows.error_code != "0":
            result.update(status="kline_failed", error_code=rows.error_code)
            return 1
        data = []
        while rows.next():
            data.append(dict(zip(rows.fields, rows.get_row_data())))
        valid = [r for r in data if r["date"] == day and all(
            float(r[k]) > 0 for k in ("open", "high", "low", "close"))]
        result.update(ok=bool(valid), status="verified_single_stock" if valid else "missing_or_nontrading",
                      bars=valid, coverage="one stock only; not full-market verified")
        return 0 if valid else 1
    finally:
        bs.logout()
        print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    raise SystemExit(main())
