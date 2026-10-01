from datetime import datetime
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from analytics import backtest_daily, recommendation_performance
from research_archive import archive_page, load_document
from trading_calendar import completed_bars, session_state
from market_insights import overview as market_overview
from task_center import task_list, run_page, report_page, data_revision
from research_stocks import catalog, stock_research, stock_reports

app = FastAPI(title="Robin Stock Assistant API", version="0.6.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CN_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger("robin-stock-api")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://quote.eastmoney.com/",
}
MARKET_CACHE_TTL = 90
_market_lock = threading.Lock()
_market_cache = {"payload": None, "saved_at": 0.0, "refreshing": False}
_minute_lock = threading.Lock()
_minute_cache = {}

SIGNAL_CACHE_TTL = 75
DAILY_CACHE_TTL = 600
_signal_lock = threading.Lock()
_signal_cache = {"payload": None, "saved_at": 0.0, "refreshing": False}
_daily_lock = threading.Lock()
_daily_cache = {}


def now_cn():
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def _num(value, default=None):
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@app.get("/api/research")
def research(track: str = "", date: str = "", offset: int = 0, limit: int = 30, task: str = "", code: str = ""):
    try:
        if code:
            return {"time_cn": now_cn(), **stock_reports(code, task, track, date, offset, limit)}
        page = report_page(task, track or None, date or None, offset, limit) if task else archive_page(track or None, date or None, offset, limit)
        return {"ok": True, "time_cn": now_cn(), **page}
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Research archive unavailable: %s", exc)
        return {"ok": False, "status": "research_data_unavailable", "items": [], "total": 0}


@app.get("/api/research-stocks")
def research_stocks():
    try:
        return {"ok": True, "time_cn": now_cn(), **catalog()}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Research stock catalog unavailable: %s", exc)
        return {"ok": False, "status": "research_stock_data_unavailable", "items": []}


@app.get("/api/stocks/{code}/research")
def research_stock(code: str):
    try:
        return {"time_cn": now_cn(), **stock_research(code)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Stock rationale unavailable: %s", exc)
        return {"ok": False, "status": "research_stock_data_unavailable"}


@app.get("/api/tasks")
def tasks():
    try:
        return {"ok": True, "time_cn": now_cn(), **task_list()}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Task data unavailable: %s", exc)
        return {"ok": False, "status": "task_data_unavailable", "items": []}


@app.get("/api/task-runs")
def task_runs(task: str = "", offset: int = 0, limit: int = 20):
    try:
        return {"ok": True, "time_cn": now_cn(), **run_page(task or None, offset, limit)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Task receipts unavailable: %s", exc)
        return {"ok": False, "status": "task_receipts_unavailable", "items": []}


@app.get("/api/overview")
def overview():
    return market_overview()


@app.get("/api/recommendations")
def recommendations(limit: int = 20, offset: int = 0):
    try:
        document = load_document("recommendations.json", "ROBIN_RECOMMENDATIONS_FILE")
        rows = sorted(document["items"], key=lambda r: (r.get("date", ""), r.get("published_at", "")), reverse=True)
        limit = max(1, min(30, limit))
        offset = max(0, offset)
        # Metadata returns promptly. Each performance calculation has its own bounded request.
        return {"ok": True, "time_cn": now_cn(), "items": rows[offset:offset + limit],
                "total": len(rows), "has_more": offset + limit < len(rows),
                "legacy_audit": document.get("legacy_audit", [])}
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Recommendations unavailable: %s", exc)
        return {"ok": False, "status": "recommendation_data_unavailable", "items": []}


@app.get("/api/recommendations/{record_id}/performance")
def performance(record_id: str):
    try:
        rows = load_document("recommendations.json", "ROBIN_RECOMMENDATIONS_FILE")["items"]
        row = next((r for r in rows if r.get("id") == record_id), None)
        if row is None:
            return {"ok": False, "status": "record_not_found"}
        if not row.get("reference_price") or row.get("provenance") != "contemporaneous":
            return {"ok": True, **recommendation_performance(row, [])}
        bars, source, errors = _get_daily(row["code"], adjust="0")
        return {"ok": True, **recommendation_performance(row, completed_bars(bars)),
                "source": source, "provider_errors": errors, "time_cn": now_cn()}
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Performance data unavailable: %s", exc)
        return {"ok": False, "status": "performance_data_unavailable"}


@app.get("/api/stocks/{code}/backtest")
def stock_backtest(code: str, days: int = 30, holding: int = 3, cost_bps: float = 20):
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return {"ok": False, "status": "invalid_code"}
    try:
        bars, source, errors = _get_daily(code)
        report = backtest_daily(completed_bars(bars), code, days, holding, cost_bps)
        return {**report, "code": code, "source": source, "provider_errors": errors, "time_cn": now_cn()}
    except (ValueError, TypeError) as exc:
        logger.warning("Backtest data invalid: %s", exc)
        return {"ok": False, "status": "backtest_data_unavailable"}


@app.get("/health")
def health():
    with _market_lock:
        cached = _market_cache["payload"] is not None
        age = int(time.time() - _market_cache["saved_at"]) if cached else None
    try:
        revision = data_revision()
    except (OSError, ValueError, TypeError, KeyError):
        revision = None
    return {
        "ok": True,
        "data_revision": revision,
        "build_commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
        "service": "Robin Stock Assistant API",
        "version": "0.6.1",
        "time_cn": now_cn(),
        "market_cache": cached,
        "market_cache_age_sec": age,
    }


def _eastmoney_spot():
    page_size = 100
    base_params = {
        "po": "1",
        "np": "2",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f2,f3,f6,f8,f10,f12,f14",
    }
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    errors = []

    def fetch_page(page):
        params = dict(base_params)
        params.update({"pn": str(page), "pz": str(page_size)})
        response = requests.get(
            url,
            params=params,
            headers=HTTP_HEADERS,
            timeout=(2.5, 5.5),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        return int(data.get("total") or 0), diff

    try:
        total, first = fetch_page(1)
        if not first:
            raise ValueError("empty first page")
    except Exception as exc:
        logger.warning("Eastmoney first page failed: %s", exc)
        return pd.DataFrame(), None, False, [f"eastmoney_direct:{type(exc).__name__}"]

    pages = max(1, (total + page_size - 1) // page_size)
    all_items = list(first)
    failed_pages = []

    if pages > 1:
        workers = min(16, pages - 1)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="em-page") as pool:
            futures = {pool.submit(fetch_page, page): page for page in range(2, pages + 1)}
            for future in as_completed(futures):
                page = futures[future]
                try:
                    _, rows = future.result()
                    all_items.extend(rows)
                except Exception as exc:
                    failed_pages.append(page)
                    errors.append(f"eastmoney_page_{page}:{type(exc).__name__}")

    if failed_pages:
        logger.warning(
            "Eastmoney pagination incomplete: %s/%s pages failed",
            len(failed_pages),
            pages,
        )

    rows = []
    for item in all_items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "code": str(item.get("f12") or ""),
                "name": str(item.get("f14") or ""),
                "price": _num(item.get("f2")),
                "pct": _num(item.get("f3")),
                "amount": _num(item.get("f6"), 0.0),
                "volume_ratio": _num(item.get("f10"), 0.0),
                "turnover": _num(item.get("f8"), 0.0),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(), None, False, errors + ["eastmoney_direct:empty"]

    unique_codes = frame["code"].astype(str).nunique()
    complete = not failed_pages and (total <= 0 or unique_codes >= int(total * 0.97))
    source = "eastmoney_direct_parallel" if complete else "eastmoney_partial"
    return frame, source, complete, errors


def _sina_partial():
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    params = {
        "page": "1",
        "num": "160",
        "sort": "amount",
        "asc": "0",
        "node": "hs_a",
        "symbol": "",
        "_s_r_a": "setlen",
    }
    headers = dict(HTTP_HEADERS)
    headers["Referer"] = "https://vip.stock.finance.sina.com.cn/"
    response = requests.get(url, params=params, headers=headers, timeout=(2.5, 5.5))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data:
        raise ValueError("empty sina response")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "code": str(item.get("code") or str(item.get("symbol") or "")[-6:]),
                "name": str(item.get("name") or ""),
                "price": _num(item.get("trade")),
                "pct": _num(item.get("changepercent")),
                "amount": _num(item.get("amount"), 0.0),
                "volume_ratio": 0.0,
                "turnover": _num(item.get("turnoverratio"), 0.0),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("empty sina frame")
    return frame, "sina_partial", False, []



def _eastmoney_candidate_frame():
    """Fast live candidate pool: merge leaders by amount, pct, turnover and volume ratio."""
    base_params = {
        "po": "1",
        "np": "2",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f2,f3,f6,f8,f10,f12,f14",
        "pn": "1",
        "pz": "100",
    }
    url = "https://push2.eastmoney.com/api/qt/clist/get"

    def fetch_rank(fid):
        params = dict(base_params)
        params["fid"] = fid
        response = requests.get(
            url,
            params=params,
            headers=HTTP_HEADERS,
            timeout=(2.5, 5.5),
        )
        response.raise_for_status()
        data = (response.json().get("data") or {})
        diff = data.get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        return diff

    items = []
    errors = []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="candidate-rank") as pool:
        futures = {pool.submit(fetch_rank, fid): fid for fid in ("f6", "f3", "f8", "f10")}
        for future in as_completed(futures):
            fid = futures[future]
            try:
                items.extend(future.result())
            except Exception as exc:
                errors.append(f"{fid}:{type(exc).__name__}")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "code": str(item.get("f12") or ""),
                "name": str(item.get("f14") or ""),
                "price": _num(item.get("f2")),
                "pct": _num(item.get("f3")),
                "amount": _num(item.get("f6"), 0.0),
                "volume_ratio": _num(item.get("f10"), 0.0),
                "turnover": _num(item.get("f8"), 0.0),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("empty live candidate frame")
    frame = frame.drop_duplicates(subset=["code"], keep="first")
    return frame, errors

def _build_market_payload(frame, source, breadth_complete, provider_errors):
    work = frame.copy()
    required = {"code", "name", "price", "pct", "amount"}
    if not required.issubset(work.columns):
        raise ValueError("market_data_schema_changed")

    for col in ("price", "pct", "amount", "volume_ratio", "turnover"):
        if col not in work.columns:
            work[col] = 0.0
        work[col] = pd.to_numeric(work[col], errors="coerce")

    work["code"] = work["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    work["name"] = work["name"].astype(str)
    work = work.dropna(subset=["price", "pct", "amount"])
    work = work[work["code"].str.len() == 6]
    work = work[work["price"] > 0]

    if work.empty:
        raise ValueError("market_data_empty_after_clean")

    work = work.drop_duplicates(subset=["code"], keep="last")
    breadth = work.copy()
    work = work[~work["name"].str.contains("ST|退", regex=True, na=False)]
    amt_rank = work["amount"].rank(pct=True)
    vr_rank = work["volume_ratio"].fillna(0).rank(pct=True)
    to_rank = work["turnover"].fillna(0).rank(pct=True)
    pct_score = ((work["pct"].clip(-5, 10) + 5) / 15).clip(0, 1)

    if (work["volume_ratio"].fillna(0) > 0).any():
        work["score"] = (amt_rank * 0.35 + vr_rank * 0.25 + pct_score * 0.25 + to_rank * 0.15) * 100
    else:
        work["score"] = (amt_rank * 0.45 + pct_score * 0.35 + to_rank * 0.20) * 100

    top = work.sort_values("score", ascending=False).head(120)
    rounded = top[
        ["code", "name", "price", "pct", "amount", "volume_ratio", "turnover", "score"]
    ].round(
        {
            "price": 3,
            "pct": 2,
            "amount": 0,
            "volume_ratio": 2,
            "turnover": 2,
            "score": 1,
        }
    )
    rows = rounded.astype(object).where(pd.notnull(rounded), None).to_dict("records")

    return {
        "ok": True,
        "status": "ok" if breadth_complete else "partial",
        "time_cn": now_cn(),
        "source": source,
        "breadth_complete": breadth_complete,
        "provider_errors": provider_errors,
        "count": int(len(breadth)),
        "advance": int((breadth["pct"] > 0).sum()),
        "decline": int((breadth["pct"] < 0).sum()),
        "flat": int((breadth["pct"] == 0).sum()),
        "amount_yi": round(float(breadth["amount"].sum()) / 1e8, 2),
        "amount_scope": "沪深京A股覆盖成交额" if breadth_complete else "部分覆盖成交额",
        "candidate_count": len(rows),
        "candidates": rows,
    }


def _refresh_market():
    with _market_lock:
        if _market_cache["refreshing"]:
            return _market_cache["payload"]
        _market_cache["refreshing"] = True

    payload = None
    provider_errors = []
    try:
        frame, source, complete, errors = _eastmoney_spot()
        provider_errors.extend(errors)
        if frame.empty:
            try:
                frame, source, complete, errors = _sina_partial()
                provider_errors.extend(errors)
            except Exception as exc:
                logger.warning("Sina partial failed: %s", exc)
                provider_errors.append(f"sina_partial:{type(exc).__name__}")
                frame = pd.DataFrame()
                source = None
                complete = False

        if not frame.empty:
            payload = _build_market_payload(frame, source, complete, provider_errors)
            with _market_lock:
                _market_cache["payload"] = payload
                _market_cache["saved_at"] = time.time()
    except Exception as exc:
        logger.exception("Market refresh failed: %s", exc)
        provider_errors.append(f"refresh:{type(exc).__name__}")
    finally:
        with _market_lock:
            _market_cache["refreshing"] = False

    return payload


def _kick_market_refresh():
    with _market_lock:
        if _market_cache["refreshing"]:
            return
    threading.Thread(target=_refresh_market, daemon=True, name="market-refresh").start()


@app.on_event("startup")
def warm_market_cache():
    def self_test():
        market_payload = _refresh_market()
        if market_payload:
            print(
                "ROBIN_SELFTEST market "
                f"ok={market_payload.get('ok')} "
                f"source={market_payload.get('source')} "
                f"count={market_payload.get('count')} "
                f"candidates={market_payload.get('candidate_count')}",
                flush=True,
            )
        else:
            print("ROBIN_SELFTEST market ok=False source=None count=0", flush=True)

        bars, source, errors = _eastmoney_minute("600000")
        print(
            "ROBIN_SELFTEST minute "
            f"ok={bool(bars)} source={source} bars={len(bars)} errors={','.join(errors)}",
            flush=True,
        )

    threading.Thread(target=self_test, daemon=True, name="startup-self-test").start()



@app.get("/api/candidates")
def live_candidates(limit: int = 20):
    limit = max(1, min(50, int(limit)))
    try:
        frame, errors = _eastmoney_candidate_frame()
        payload = _build_market_payload(
            frame,
            "eastmoney_live_candidates",
            False,
            errors,
        )
        rows = list(payload.get("candidates") or [])[:limit]
        return {
            "ok": True,
            "status": "ok",
            "time_cn": payload.get("time_cn") or now_cn(),
            "source": "eastmoney_live_candidates",
            "scanned": payload.get("count", 0),
            "candidate_count": len(rows),
            "candidates": rows,
            "provider_errors": errors,
        }
    except Exception as exc:
        logger.warning("Live candidate refresh failed: %s", exc)
        with _market_lock:
            cached = _market_cache["payload"]
            age = time.time() - _market_cache["saved_at"] if cached else None
        if cached:
            rows = list(cached.get("candidates") or [])[:limit]
            return {
                "ok": True,
                "status": "fallback_market_cache",
                "time_cn": cached.get("time_cn") or now_cn(),
                "source": cached.get("source"),
                "scanned": cached.get("count", 0),
                "candidate_count": len(rows),
                "candidates": rows,
                "cache_age_sec": int(age or 0),
            }
        return {
            "ok": False,
            "status": "candidate_data_temporarily_unavailable",
            "time_cn": now_cn(),
            "source": None,
            "scanned": 0,
            "candidate_count": 0,
            "candidates": [],
        }

@app.get("/api/market")
def market():
    with _market_lock:
        cached = _market_cache["payload"]
        saved_at = _market_cache["saved_at"]
    age = time.time() - saved_at if cached else None

    if cached is not None:
        if age is not None and age > MARKET_CACHE_TTL:
            _kick_market_refresh()
        result = dict(cached)
        result["cache_age_sec"] = int(age or 0)
        result["stale"] = bool(age and age > MARKET_CACHE_TTL * 4)
        return result

    _kick_market_refresh()
    deadline = time.time() + 12.0
    while time.time() < deadline:
        time.sleep(0.15)
        with _market_lock:
            payload = _market_cache["payload"]
        if payload is not None:
            result = dict(payload)
            result["cache_age_sec"] = 0
            result["stale"] = False
            return result

    return {
        "ok": False,
        "status": "market_data_temporarily_unavailable",
        "time_cn": now_cn(),
        "source": None,
        "breadth_complete": False,
        "count": 0,
        "advance": 0,
        "decline": 0,
        "flat": 0,
        "candidate_count": 0,
        "candidates": [],
    }


def _minute_secid(code):
    return ("1." if code.startswith(("5", "6", "9")) else "0.") + code


def _eastmoney_minute(code):
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "ndays": "1",
        "iscr": "0",
        "iscca": "0",
        "secid": _minute_secid(code),
    }
    errors = []
    for host in ("https://push2.eastmoney.com", "https://push2his.eastmoney.com"):
        try:
            response = requests.get(
                host + "/api/qt/stock/trends2/get",
                params=params,
                headers=HTTP_HEADERS,
                timeout=(2.5, 5.5),
            )
            response.raise_for_status()
            data = (response.json().get("data") or {})
            trends = data.get("trends") or []
            if not trends:
                raise ValueError("empty trends")
            bars = []
            for line in trends[-300:]:
                parts = str(line).split(",")
                if len(parts) < 7:
                    continue
                price = _num(parts[1])
                if price is None or price <= 0:
                    price = _num(parts[2])
                if price is None or price <= 0:
                    continue
                high = _num(parts[3], price)
                low = _num(parts[4], price)
                bars.append(
                    {
                        "time": parts[0],
                        "open": price,
                        "close": price,
                        "high": high if high and high > 0 else price,
                        "low": low if low and low > 0 else price,
                        "volume": _num(parts[5], 0.0),
                        "amount": _num(parts[6], 0.0),
                    }
                )
            if bars:
                return bars, "eastmoney_trends", errors
            raise ValueError("no valid bars")
        except Exception as exc:
            logger.warning("Minute direct failed for %s via %s: %s", code, host, exc)
            errors.append(f"{type(exc).__name__}")
    return [], None, errors


@app.get("/api/stocks/{code}/minute")
def stock_minute(code: str):
    code = "".join(ch for ch in code if ch.isdigit())[:6]
    if len(code) != 6:
        return {"ok": False, "status": "invalid_code", "code": code, "bars": []}

    now = time.time()
    with _minute_lock:
        cached = _minute_cache.get(code)
    if cached and now - cached["saved_at"] < 20:
        return dict(cached["payload"])

    bars, source, errors = _eastmoney_minute(code)
    if not bars:
        if cached:
            result = dict(cached["payload"])
            result["status"] = "stale"
            result["stale"] = True
            result["errors"] = errors
            return result
        return {
            "ok": False,
            "status": "minute_data_temporarily_unavailable",
            "time_cn": now_cn(),
            "code": code,
            "source": source,
            "errors": errors,
            "count": 0,
            "bars": [],
        }

    payload = {
        "ok": True,
        "status": "ok",
        "time_cn": now_cn(),
        "code": code,
        "source": source,
        "count": len(bars),
        "bars": bars,
    }
    with _minute_lock:
        _minute_cache[code] = {"saved_at": now, "payload": payload}
    return payload


def _eastmoney_daily(code, limit=120, adjust="1"):
    params = {
        "secid": _minute_secid(code),
        "klt": "101",
        "fqt": adjust,
        "lmt": str(limit),
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    errors = []
    for host in ("https://push2his.eastmoney.com", "https://push2.eastmoney.com"):
        try:
            response = requests.get(
                host + "/api/qt/stock/kline/get",
                params=params,
                headers=HTTP_HEADERS,
                timeout=(2.5, 5.5),
            )
            response.raise_for_status()
            data = (response.json().get("data") or {})
            lines = data.get("klines") or []
            if not lines:
                raise ValueError("empty klines")
            bars = []
            for line in lines[-limit:]:
                parts = str(line).split(",")
                if len(parts) < 7:
                    continue
                close = _num(parts[2])
                if close is None or close <= 0:
                    continue
                bars.append(
                    {
                        "date": parts[0],
                        "open": _num(parts[1], close),
                        "close": close,
                        "high": _num(parts[3], close),
                        "low": _num(parts[4], close),
                        "volume": _num(parts[5], 0.0),
                        "amount": _num(parts[6], 0.0),
                        "pct": _num(parts[8], 0.0) if len(parts) > 8 else 0.0,
                        "turnover": _num(parts[10], 0.0) if len(parts) > 10 else 0.0,
                    }
                )
            if bars:
                return bars, "eastmoney_kline", errors
            raise ValueError("no valid daily bars")
        except Exception as exc:
            logger.warning("Daily direct failed for %s via %s: %s", code, host, exc)
            errors.append(type(exc).__name__)
    return [], None, errors


def _get_daily(code, adjust="1"):
    cache_key = code + ":" + adjust
    now = time.time()
    with _daily_lock:
        cached = _daily_cache.get(cache_key)
    if cached and now - cached["saved_at"] < DAILY_CACHE_TTL:
        return cached["bars"], cached["source"], cached["errors"]

    bars, source, errors = _eastmoney_daily(code, adjust=adjust)
    if bars:
        with _daily_lock:
            _daily_cache[cache_key] = {
                "saved_at": now,
                "bars": bars,
                "source": source,
                "errors": errors,
            }
    elif cached:
        return cached["bars"], cached["source"], errors + ["stale_cache"]
    return bars, source, errors


def _signal_session_state():
    state = session_state()
    if state["is_live"]:
        return "实时观察"
    if state["code"] == "lunch":
        return "午间观察"
    if state["code"] == "closed":
        return "休市历史观察"
    return "收盘观察"


def _analyze_signal(stock):
    code = str(stock.get("code") or "")
    name = str(stock.get("name") or "")
    pct = _num(stock.get("pct"))
    if len(code) != 6 or pct is None or pct < 0.3 or pct > 9.3:
        return None

    minute_bars, minute_source, minute_errors = _eastmoney_minute(code)
    if len(minute_bars) < 25:
        return None

    prices = [float(x["close"]) for x in minute_bars if _num(x.get("close"))]
    volumes = [float(x.get("volume") or 0.0) for x in minute_bars if _num(x.get("close"))]
    if len(prices) < 25:
        return None

    current = prices[-1]
    session_open = prices[0]
    session_high = max(prices)
    session_low = min(prices)
    span = max(session_high - session_low, current * 0.002)
    range_pos = (current - session_low) / span
    early = prices[: min(60, len(prices))]
    early_low = min(early)
    early_drawdown = early_low / session_open - 1.0 if session_open else 0.0
    recent_start = max(0, len(prices) - 20)
    recent_return = current / prices[recent_start] - 1.0 if prices[recent_start] else 0.0
    recent_floor = min(prices[-20:])
    previous_slice = prices[-50:-20] if len(prices) >= 50 else prices[:-20]
    previous_floor = min(previous_slice) if previous_slice else session_low
    low_lift = recent_floor >= previous_floor * 1.002

    recent_vol = sum(volumes[-10:]) / max(1, len(volumes[-10:]))
    prior_vols = volumes[-40:-10] if len(volumes) >= 40 else volumes[:-10]
    prior_vol = sum(prior_vols) / max(1, len(prior_vols)) if prior_vols else recent_vol
    volume_pulse = recent_vol / prior_vol if prior_vol > 0 else 1.0

    daily_bars, daily_source, daily_errors = _get_daily(code)
    position60 = None
    drawdown20 = None
    ma5 = None
    ma10 = None
    if len(daily_bars) >= 20:
        closes = [float(x["close"]) for x in daily_bars]
        highs = [float(x["high"]) for x in daily_bars]
        lows = [float(x["low"]) for x in daily_bars]
        lookback = min(60, len(closes))
        low60 = min(lows[-lookback:])
        high60 = max(highs[-lookback:])
        if high60 > low60:
            position60 = (current - low60) / (high60 - low60)
        prior_highs = highs[-21:-1] if len(highs) >= 21 else highs[:-1]
        if prior_highs:
            drawdown20 = current / max(prior_highs) - 1.0
        ma5 = sum(closes[-5:]) / min(5, len(closes))
        ma10 = sum(closes[-10:]) / min(10, len(closes))

    choices = []

    if (
        position60 is not None
        and position60 <= 0.45
        and ma10 is not None
        and current >= ma10 * 0.995
        and 1.0 <= pct <= 7.8
        and range_pos >= 0.72
        and recent_return >= 0.0015
    ):
        score = 66
        score += min(8, int(max(0.0, (0.45 - position60) * 40)))
        score += min(7, int(max(0.0, (range_pos - 0.72) * 25)))
        score += min(6, int(max(0.0, recent_return * 450)))
        score += min(5, int(max(0.0, (volume_pulse - 1.0) * 8)))
        choices.append(
            (
                score,
                "低位首次启动",
                [
                    f"60日位置约{position60 * 100:.0f}%",
                    "分时收在日内区间上部",
                    "近20分钟保持转强",
                ],
            )
        )

    if (
        early_drawdown <= -0.003
        and current >= session_open * 1.003
        and range_pos >= 0.70
        and recent_return >= 0.001
        and low_lift
    ):
        score = 67
        score += min(8, int(abs(early_drawdown) * 350))
        score += min(7, int(max(0.0, (range_pos - 0.70) * 25)))
        score += min(7, int(max(0.0, recent_return * 500)))
        score += min(5, int(max(0.0, (volume_pulse - 1.0) * 8)))
        choices.append(
            (
                score,
                "分歧转一致",
                [
                    f"早盘回撤{early_drawdown * 100:.1f}%后收复",
                    "近期低点抬高",
                    "价格回到日内强势区",
                ],
            )
        )

    if (
        drawdown20 is not None
        and position60 is not None
        and drawdown20 <= -0.10
        and position60 <= 0.58
        and pct >= 1.5
        and range_pos >= 0.72
        and (ma5 is None or current >= ma5 * 0.985)
    ):
        score = 65
        score += min(10, int(max(0.0, abs(drawdown20) - 0.10) * 70))
        score += min(8, int(max(0.0, (range_pos - 0.72) * 28)))
        score += min(6, int(max(0.0, recent_return * 420)))
        choices.append(
            (
                score,
                "超跌转强",
                [
                    f"距近20日高点回撤约{abs(drawdown20) * 100:.0f}%",
                    "当日涨幅转正并处于强势区",
                    "分时未出现明显破位",
                ],
            )
        )

    if not choices:
        return None

    score, signal_type, reasons = max(choices, key=lambda x: x[0])
    recent_high = max(prices[-10:])
    confirm_price = max(current, recent_high)
    invalid_price = min(recent_floor, current * 0.988)
    return {
        "code": code,
        "name": name,
        "type": signal_type,
        "state": _signal_session_state(),
        "score": min(95, int(score)),
        "price": round(current, 3),
        "pct": round(pct, 2),
        "confirm_price": round(confirm_price, 3),
        "invalid_price": round(invalid_price, 3),
        "range_position": round(range_pos, 3),
        "volume_pulse": round(volume_pulse, 2),
        "reasons": reasons,
        "minute_source": minute_source,
        "daily_source": daily_source,
        "provider_errors": minute_errors + daily_errors,
    }


def _refresh_signals():
    with _signal_lock:
        if _signal_cache["refreshing"]:
            return _signal_cache["payload"]
        _signal_cache["refreshing"] = True

    payload = None
    try:
        with _market_lock:
            market_payload = _market_cache["payload"]
            market_age = time.time() - _market_cache["saved_at"] if market_payload else None

        if market_payload is None or (market_age is not None and market_age > MARKET_CACHE_TTL * 4):
            market_payload = _refresh_market()

        candidates = list((market_payload or {}).get("candidates") or [])
        candidates = [
            x for x in candidates
            if 0.3 <= (_num(x.get("pct"), -99.0) or -99.0) <= 9.3
        ][:16]

        signals = []
        if candidates:
            with ThreadPoolExecutor(max_workers=min(8, len(candidates)), thread_name_prefix="signal") as pool:
                futures = [pool.submit(_analyze_signal, item) for item in candidates]
                for future in as_completed(futures):
                    try:
                        signal = future.result()
                        if signal:
                            signals.append(signal)
                    except Exception as exc:
                        logger.warning("Signal scan item failed: %s", exc)

        signals.sort(key=lambda x: (x.get("score", 0), x.get("pct", 0)), reverse=True)
        payload = {
            "ok": True,
            "status": "ok" if signals else "no_signal",
            "time_cn": now_cn(),
            "model": "live_observation_v0.1",
            "model_status": "unbacktested",
            "scanned": len(candidates),
            "count": len(signals),
            "signals": signals[:12],
        }
        with _signal_lock:
            _signal_cache["payload"] = payload
            _signal_cache["saved_at"] = time.time()
    except Exception as exc:
        logger.exception("Signal refresh failed: %s", exc)
    finally:
        with _signal_lock:
            _signal_cache["refreshing"] = False
    return payload


def _kick_signal_refresh():
    with _signal_lock:
        if _signal_cache["refreshing"]:
            return
    threading.Thread(target=_refresh_signals, daemon=True, name="signal-refresh").start()


@app.get("/api/signals")
def signals(limit: int = 8):
    limit = max(1, min(12, int(limit)))
    with _signal_lock:
        cached = _signal_cache["payload"]
        saved_at = _signal_cache["saved_at"]
    age = time.time() - saved_at if cached else None

    if cached is not None:
        if age is not None and age > SIGNAL_CACHE_TTL:
            _kick_signal_refresh()
        result = dict(cached)
        result["signals"] = list(cached.get("signals") or [])[:limit]
        result["count"] = len(result["signals"])
        result["cache_age_sec"] = int(age or 0)
        result["stale"] = bool(age and age > SIGNAL_CACHE_TTL * 4)
        return result

    _kick_signal_refresh()
    deadline = time.time() + 18.0
    while time.time() < deadline:
        time.sleep(0.15)
        with _signal_lock:
            payload = _signal_cache["payload"]
        if payload is not None:
            result = dict(payload)
            result["signals"] = list(payload.get("signals") or [])[:limit]
            result["count"] = len(result["signals"])
            result["cache_age_sec"] = 0
            result["stale"] = False
            return result

    return {
        "ok": False,
        "status": "signal_scan_warming",
        "time_cn": now_cn(),
        "model": "live_observation_v0.1",
        "model_status": "unbacktested",
        "scanned": 0,
        "count": 0,
        "signals": [],
    }
