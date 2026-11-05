"""One BaoStock connection and one market-wide daily request. No parallel shards."""
import argparse
import json
import math
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from baostock_snapshot import CODE_RE
from daily_snapshot import validate_snapshot


def records(result):
    if result.error_code != "0":
        raise ValueError("baostock_query_failed:" + result.error_code + ":" + result.error_msg)
    rows = []
    while result.next():
        rows.append(dict(zip(result.fields, result.get_row_data())))
    if result.error_code != "0":
        raise ValueError("baostock_receive_failed:" + result.error_code)
    return rows


def collect(client, day, prior_codes):
    """SDK 0.9.3 exposes query_daily_history_k_AStock(date), one market request."""
    logged_in = False
    try:
        login = client.login()
        if login.error_code != "0":
            raise ValueError("baostock_login_failed:" + login.error_code + ":" + login.error_msg)
        logged_in = True
        raw = records(client.query_daily_history_k_AStock(date=day))
        scoped = [r for r in raw if CODE_RE.fullmatch(str(r.get("code", "")))]
        codes = [r["code"] for r in scoped]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate_bulk_code")
        if any(r.get("date") != day for r in scoped):
            raise ValueError("stale_bulk_date")
        # Include previously known codes so missing securities do not vanish
        # from the denominator; the bulk response also admits new listings.
        universe = sorted(set(prior_codes) | set(codes))
        by_code = {r["code"]: r for r in scoped}
        rows, errors = [], []
        for code in universe:
            try:
                row = by_code[code]
                if row.get("adjustflag") != "3":
                    raise ValueError("unadjusted_bulk_required")
                values = [float(row[k]) for k in ("open", "high", "low", "close", "volume", "amount")]
                o, h, l, c, v, a = values
                if not all(math.isfinite(x) for x in values) or not (0 < l <= min(o, c) <= max(o, c) <= h and v >= 0 and a >= 0):
                    raise ValueError("invalid_bulk_ohlcv")
                bar = {"code": code, "date": day, "open": o, "high": h, "low": l,
                       "close": c, "volume": v, "amount": a, "provider": "baostock",
                       "adjustment": "none", "volume_unit": "shares"}
                for key in ("preclose", "turn", "pctChg", "tradestatus", "isST"):
                    if key in row:
                        bar[key] = row[key]
                rows.append(bar)
            except (KeyError, ValueError, TypeError):
                errors.append({"code": code, "reason": "missing_suspended_or_invalid_bulk_bar"})
        checked = len(universe)
        payload = {"provider": "baostock", "trade_date": day,
                   "status": "historical_observation_only", "exchange_scope": "Shanghai+Shenzhen; Beijing excluded",
                   "collection_method": "single_connection_query_daily_history_k_AStock",
                   "coverage": {"checked": checked, "verified": len(rows), "errors": len(errors),
                                "coverage_ratio": round(len(rows) / checked, 6) if checked else 0},
                   "rows": rows, "errors": errors}
        validate_snapshot(payload, day, "baostock")
        return payload
    finally:
        if logged_in:
            try:
                client.logout()
            except (OSError, ValueError):
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    root = Path("backend/data")
    target = root / "baostock" / (day + ".json")
    status = {"provider": "baostock", "trade_date": day,
              "attempted_at": datetime.now(timezone.utc).isoformat(), "ok": False}
    try:
        if target.exists():
            validate_snapshot(json.loads(target.read_text()), day, "baostock")
            status.update(ok=True, status="already_verified_no_network_request")
            return 0
        prior_codes = set()
        for path in sorted((root / "baostock").glob("20??-??-??.json"), reverse=True):
            if not (day > path.stem >= (date.fromisoformat(day) - timedelta(days=10)).isoformat()):
                continue
            payload = json.loads(path.read_text())
            validate_snapshot(payload, path.stem, "baostock")
            prior_codes.update(r["code"] for r in payload["rows"] + payload["errors"])
            break
        import baostock as bs
        socket.setdefaulttimeout(15)
        payload = collect(bs, day, prior_codes)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
        status.update(ok=True, status="verified", coverage=payload["coverage"])
        return 0
    except Exception as exc:
        status.update(status="collection_failed", reason=type(exc).__name__ + ":" + str(exc)[:200])
        return 1
    finally:
        path = root / "market_source_status" / ("baostock-" + day + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, ensure_ascii=False) + "\n")
        print(json.dumps(status, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
