"""Read-only BaoStock feasibility probe; never writes research receipts.

Run: python scripts/probe_baostock.py [YYYY-MM-DD]
This is a diagnostic, not a production fallback. The BaoStock socket service
may be blocked in Railway; only enable a runtime fallback after measuring it.
"""
import json
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
import math

def main():
    try:
        import baostock as bs
    except ImportError:
        print(json.dumps({"ok": False, "provider": "baostock", "status": "dependency_missing", "install": "pip install baostock"}))
        return 2
    day = date.fromisoformat(sys.argv[1]).isoformat() if len(sys.argv) > 1 else datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    result = {"ok": False, "requested_date": day, "provider": "baostock", "scope": "three_stock_probe", "symbols": ["sh.600000", "sz.000001", "sz.300750"]}
    logged_in = False
    try:
        login = bs.login()
        logged_in = login.error_code == "0"
        if not logged_in:
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
        if not calendar_rows:
            result.update(status="calendar_empty", error="No trade-calendar rows returned")
            return 1
        if calendar_rows[0][-1] == "0":
            result.update(status="nontrading_day", ok=True, coverage="calendar only; no OHLCV expected")
            return 0
        # Universe is an independent coverage diagnostic, not a full OHLCV scan.
        universe = bs.query_all_stock(day=day)
        if universe.error_code != "0":
            result.update(status="universe_failed", error_code=universe.error_code)
            return 1
        market_counts = {"sh": 0, "sz": 0, "bj": 0}
        tradable_count = 0
        while universe.next():
            row = dict(zip(universe.fields, universe.get_row_data()))
            code = str(row.get("code", ""))
            prefix, _, digits = code.partition(".")
            if prefix not in market_counts or len(digits) != 6 or not digits.isdigit():
                continue
            # Exclude indices/ETFs and other non-A-share securities by prefix.
            is_stock = ((prefix == "sh" and digits.startswith("6"))
                        or (prefix == "sz" and digits.startswith(("0", "3")))
                        or (prefix == "bj" and digits.startswith(("4", "8", "9"))))
            if not is_stock:
                continue
            market_counts[prefix] += 1
            if str(row.get("tradeStatus", "")) == "1":
                tradable_count += 1
        result["universe"] = {"candidate_count": sum(market_counts.values()),
                              "by_exchange": market_counts, "tradable_count": tradable_count,
                              "method": "code-prefix approximation; excludes no verified instrument types"}
        if sum(market_counts.values()) < 1000:
            result.update(status="universe_too_small")
            return 1
        per_symbol = {}
        for symbol in result["symbols"]:
            rows = bs.query_history_k_data_plus(
                symbol, "date,code,open,high,low,close,volume,amount,tradestatus",
                start_date=day, end_date=day, frequency="d", adjustflag="3")
            if rows.error_code != "0":
                per_symbol[symbol] = {"status": "kline_failed", "error_code": rows.error_code}
                continue
            data = []
            while rows.next():
                data.append(dict(zip(rows.fields, rows.get_row_data())))
            valid = []
            for bar in data:
                try:
                    prices = [float(bar[k]) for k in ("open", "high", "low", "close")]
                    volume = float(bar["volume"])
                    amount = float(bar["amount"])
                except (ValueError, TypeError, KeyError):
                    continue
                opening, high, low, closing = prices
                if (bar["date"] == day and 0 < low <= min(opening, closing)
                        and max(opening, closing) <= high and volume >= 0 and amount >= 0
                        and all(math.isfinite(v) for v in prices + [volume, amount])):
                    valid.append(bar)
            per_symbol[symbol] = {"status": "verified" if valid else "missing_or_suspended",
                                  "bars": valid}
        verified_count = sum(item["status"] == "verified" for item in per_symbol.values())
        # BaoStock offers 5-minute historical bars, not tick-level realtime quotes.
        minute = {"symbol": "sh.600000", "frequency": "5", "status": "not_checked"}
        mrs = bs.query_history_k_data_plus(
            "sh.600000", "date,time,code,open,high,low,close,volume,amount",
            start_date=day, end_date=day, frequency="5", adjustflag="3")
        if mrs.error_code != "0":
            minute.update(status="query_failed", error_code=mrs.error_code)
        else:
            minute_bars = 0
            invalid_bars = 0
            while mrs.next():
                bar = dict(zip(mrs.fields, mrs.get_row_data()))
                try:
                    o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
                    v, a = float(bar["volume"]), float(bar["amount"])
                    valid = (bar["date"] == day and 0 < l <= min(o, c)
                             and max(o, c) <= h and v >= 0 and a >= 0
                             and all(math.isfinite(x) for x in (o, h, l, c, v, a)))
                except (ValueError, TypeError, KeyError):
                    valid = False
                minute_bars += int(valid)
                invalid_bars += int(not valid)
            minute.update(status="verified" if minute_bars > 0 and invalid_bars == 0 else "missing_or_invalid",
                          valid_bars=minute_bars, invalid_bars=invalid_bars)
        result["minute_5m"] = minute
        result.update(ok=verified_count == len(per_symbol) and minute["status"] == "verified",
                      status="verified_daily_and_5m" if verified_count == len(per_symbol) and minute["status"] == "verified" else "partial_or_missing",
                      verified_count=verified_count, checked_count=len(per_symbol),
                      per_symbol=per_symbol,
                      coverage="three selected stocks only; not full-market verified")
        return 0 if result["ok"] else 1
    except Exception as exc:
        result.update(status="provider_exception", error_type=type(exc).__name__, error=str(exc)[:200])
        return 1
    finally:
        if logged_in:
            try:
                bs.logout()
            except Exception:
                pass
        print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    raise SystemExit(main())
