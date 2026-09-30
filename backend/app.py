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

app = FastAPI(title="Robin Stock Assistant API", version="0.2.0")
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
def research():
    """Published research only. A scheduled task does not itself publish here."""
    path = os.environ.get("ROBIN_RESEARCH_FILE", "/data/research.json")
    try:
        with open(path, encoding="utf-8") as file:
            payload = json.load(file)
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("items must be a list")
        allowed = {"market_review", "dragon_tiger", "low_position", "quant_research"}
        clean = [
            {key: str(item[key]) for key in ("date", "track", "title", "summary")}
            for item in items
            if isinstance(item, dict)
            and all(key in item for key in ("date", "track", "title", "summary"))
            and item["track"] in allowed
        ]
        return {"ok": True, "time_cn": now_cn(), "items": clean[-100:][::-1]}
    except FileNotFoundError:
        return {"ok": True, "time_cn": now_cn(), "items": [], "status": "not_published"}
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Research data unavailable: %s", exc)
        return {"ok": False, "time_cn": now_cn(), "items": [], "status": "research_data_unavailable"}


@app.get("/health")
def health():
    with _market_lock:
        cached = _market_cache["payload"] is not None
        age = int(time.time() - _market_cache["saved_at"]) if cached else None
    return {
        "ok": True,
        "service": "Robin Stock Assistant API",
        "version": "0.2.0",
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
    work = work[~work["name"].str.contains("ST|退", regex=True, na=False)]
    work = work.dropna(subset=["price", "pct", "amount"])
    work = work[work["code"].str.len() == 6]
    work = work[work["price"] > 0]

    if work.empty:
        raise ValueError("market_data_empty_after_clean")

    amt_rank = work["amount"].rank(pct=True)
    vr_rank = work["volume_ratio"].fillna(0).rank(pct=True)
    to_rank = work["turnover"].fillna(0).rank(pct=True)
    pct_score = ((work["pct"].clip(-5, 10) + 5) / 15).clip(0, 1)

    if (work["volume_ratio"].fillna(0) > 0).any():
        work["score"] = (amt_rank * 0.35 + vr_rank * 0.25 + pct_score * 0.25 + to_rank * 0.15) * 100
    else:
        work["score"] = (amt_rank * 0.45 + pct_score * 0.35 + to_rank * 0.20) * 100

    top = work.sort_values("score", ascending=False).head(50)
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
        "count": int(len(work)),
        "advance": int((work["pct"] > 0).sum()),
        "decline": int((work["pct"] < 0).sum()),
        "flat": int((work["pct"] == 0).sum()),
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
