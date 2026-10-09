"""Cached public index and board quotes; retrieval time is not quote time."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import threading
import time

import requests
from analytics import number
from quote_providers import tencent_quotes
from trading_calendar import CN_TZ, session_state

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
_LOCK = threading.Lock()
_CACHE = {"saved_at": 0.0, "payload": None, "refreshing": False}
_TTL = 90


def stamp(value):
    value = number(value)
    if value is None or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, CN_TZ).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def fetch_rows(params, path="/api/qt/clist/get"):
    hosts = ["https://push2.eastmoney.com"]
    board_request = str(params.get("fs", "")).startswith("m:90")
    if board_request:
        hosts.append("https://push2delay.eastmoney.com")
    last_error = None
    for host in hosts:
        try:
            response = requests.get(host + path, params=params,
                                    headers=_HEADERS, timeout=(2.5, 5.5))
            response.raise_for_status()
            data = response.json().get("data") or {}
            rows = data.get("diff") or []
            if isinstance(rows, dict):
                rows = list(rows.values())
            if not isinstance(rows, list) or not rows:
                raise ValueError("empty_quote_data")
            if board_request and any(not isinstance(r, dict) or
                                     not str(r.get("f12", "")).startswith("BK") for r in rows):
                raise ValueError("invalid_board_scope")
            return rows
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = exc
    raise last_error


def index_quotes():
    symbols = ["sh000001", "sz399001", "sz399006", "sh000688"]
    params = {"secids": "1.000001,0.399001,0.399006,1.000688", "fltt": "2",
              "invt": "2", "fields": "f2,f3,f12,f14,f124"}
    rows = []
    try:
        rows = [dict(code=str(r.get("f12") or ""), name=str(r.get("f14") or ""),
                     price=number(r.get("f2")), pct=number(r.get("f3")),
                     as_of=stamp(r.get("f124")), source="eastmoney_public")
                for r in fetch_rows(params, "/api/qt/ulist.np/get")]
    except (requests.RequestException, ValueError, TypeError):
        pass
    by_code = {r["code"]: r for r in rows if r["code"] in {symbol[-6:] for symbol in symbols}
               and r["price"] is not None and r["price"] > 0 and r["pct"] is not None}
    session = session_state()
    now = datetime.now(CN_TZ)
    outdated = any(not r.get("as_of") or
                   (now - datetime.fromisoformat(r["as_of"])).total_seconds() > 180
                   for r in by_code.values())
    if len(by_code) < len(symbols) or (session["is_live"] and outdated):
        try:
            for row in tencent_quotes(symbols):
                old = by_code.get(row["code"])
                if old is None or not old.get("as_of") or row["as_of"] >= old["as_of"]:
                    by_code[row["code"]] = row
        except (requests.RequestException, ValueError, TypeError):
            if not by_code:
                raise
    if not by_code:
        raise ValueError("index_quotes_unavailable")
    return [by_code[symbol[-6:]] for symbol in symbols if symbol[-6:] in by_code]


def board_quotes(kind, strong):
    # Mapping independently checked against AKShare's primary provider implementation.
    params = {"pn": "1", "pz": "5", "po": "1" if strong else "0", "np": "1",
              "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
              "fid": "f3", "fs": "m:90 t:2 f:!50" if kind == "industry" else "m:90 t:3 f:!50",
              "fields": "f3,f6,f12,f14,f104,f105,f128,f136,f124"}
    return [dict(code=str(r.get("f12") or ""), name=str(r.get("f14") or ""),
                 pct=number(r.get("f3")), amount=number(r.get("f6")),
                 advance=number(r.get("f104")), decline=number(r.get("f105")),
                 leader=str(r.get("f128") or ""), leader_pct=number(r.get("f136")),
                 as_of=stamp(r.get("f124")))
            for r in fetch_rows(params)]


def _refresh_overview():
    with _LOCK:
        if _CACHE["refreshing"]:
            return _CACHE["payload"]
        _CACHE["refreshing"] = True
        cached = _CACHE["payload"]

    payload = {"ok": False, "indices": [], "industry": {"strong": [], "weak": []},
               "concept": {"strong": [], "weak": []}, "provider_errors": [],
               "source": "eastmoney_public", "retrieved_at": datetime.now(CN_TZ).isoformat(timespec="seconds")}
    try:
        jobs = {"indices": index_quotes}
        for kind in ("industry", "concept"):
            for side in ("strong", "weak"):
                jobs[kind + ":" + side] = lambda k=kind, s=side: board_quotes(k, s == "strong")
        successes = 0
        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="overview") as pool:
            futures = {pool.submit(fn): key for key, fn in jobs.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    rows = future.result()
                    if key == "indices":
                        payload[key] = rows
                        if any(r.get("source") == "tencent_public" for r in rows):
                            payload["source"] = "eastmoney_and_tencent_public"
                    else:
                        kind, side = key.split(":")
                        payload[kind][side] = rows
                    successes += 1
                except Exception as exc:
                    payload["provider_errors"].append(key + ":" + type(exc).__name__)
                    if cached:
                        if key == "indices":
                            previous = cached.get(key) or []
                            payload[key] = previous
                        else:
                            kind, side = key.split(":")
                            previous = (cached.get(kind) or {}).get(side) or []
                            payload[kind][side] = previous
                        if previous:
                            payload["stale"] = True
                            payload.setdefault("stale_sections", []).append(key)
        payload["ok"] = bool(successes)
        payload["status"] = "ok" if successes == 5 else "partial" if successes else "unavailable"
        if successes:
            with _LOCK:
                _CACHE["saved_at"] = time.time()
                _CACHE["payload"] = payload
        elif cached:
            payload = dict(cached, status="stale", stale=True,
                           provider_errors=payload["provider_errors"])
        payload["session"] = session_state()
        return payload
    finally:
        with _LOCK:
            _CACHE["refreshing"] = False


def overview():
    with _LOCK:
        cached = _CACHE["payload"]
        saved_at = _CACHE["saved_at"]
        refreshing = _CACHE["refreshing"]
    age = time.time() - saved_at if cached else None

    if cached is not None:
        if age is not None and age > _TTL and not refreshing:
            threading.Thread(target=_refresh_overview, daemon=True, name="overview-refresh").start()
        return dict(
            cached,
            session=session_state(),
            cache_age_sec=int(age or 0),
            stale=bool(cached.get("stale") or (age and age > _TTL * 4)),
        )

    payload = _refresh_overview()
    if payload is None:
        return {"ok": False, "status": "warming", "indices": [],
                "industry": {"strong": [], "weak": []},
                "concept": {"strong": [], "weak": []},
                "provider_errors": [], "source": "eastmoney_public",
                "session": session_state()}
    return payload

