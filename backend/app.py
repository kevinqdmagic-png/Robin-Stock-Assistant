from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from zoneinfo import ZoneInfo
import akshare as ak
import pandas as pd

app = FastAPI(title="Robin Stock Assistant API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CN_TZ = ZoneInfo("Asia/Shanghai")

def now_cn():
    return datetime.now(CN_TZ).isoformat(timespec="seconds")

def get_spot():
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        return pd.DataFrame()
    return df

@app.get("/health")
def health():
    return {"ok": True, "service": "Robin Stock Assistant API", "time_cn": now_cn()}

@app.get("/api/market")
def market():
    df = get_spot()
    if df.empty:
        return {"ok": False, "time_cn": now_cn(), "count": 0, "candidates": []}

    rename = {
        "代码":"code","名称":"name","最新价":"price","涨跌幅":"pct",
        "成交额":"amount","量比":"volume_ratio","换手率":"turnover"
    }
    cols = [c for c in rename if c in df.columns]
    work = df[cols].rename(columns=rename).copy()

    for c in ["price","pct","amount","volume_ratio","turnover"]:
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce")

    if "name" in work.columns:
        work = work[~work["name"].astype(str).str.contains("ST|退", regex=True, na=False)]

    work = work.dropna(subset=["price","pct","amount"], how="any")

    if "volume_ratio" not in work.columns:
        work["volume_ratio"] = 1.0
    if "turnover" not in work.columns:
        work["turnover"] = 0.0

    amt_rank = work["amount"].rank(pct=True)
    vr_rank = work["volume_ratio"].fillna(0).rank(pct=True)
    pct_score = ((work["pct"].clip(-5, 10) + 5) / 15).clip(0, 1)
    to_rank = work["turnover"].fillna(0).rank(pct=True)
    work["score"] = (amt_rank*0.35 + vr_rank*0.25 + pct_score*0.25 + to_rank*0.15) * 100

    top = work.sort_values("score", ascending=False).head(50)
    rows = top[["code","name","price","pct","amount","volume_ratio","turnover","score"]].round({
        "price":3,"pct":2,"amount":0,"volume_ratio":2,"turnover":2,"score":1
    }).to_dict("records")

    adv = int((work["pct"] > 0).sum())
    dec = int((work["pct"] < 0).sum())
    flat = int((work["pct"] == 0).sum())

    return {
        "ok": True,
        "time_cn": now_cn(),
        "count": int(len(work)),
        "advance": adv,
        "decline": dec,
        "flat": flat,
        "candidate_count": len(rows),
        "candidates": rows
    }
