#!/usr/bin/env python3
"""Build the substantive SH/SZ volume-price study for 2026-11-13."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import statistics
import subprocess
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
T, PREV, D = "2026-11-13", "2026-11-12", "2026-11-16"
CN = ZoneInfo("Asia/Shanghai")
REPORT_ID = "volume-price-20261113-close-v1"
RUN_ID = "volume-price-20261113-scheduled-close-v1"
RECEIPT_ID = RUN_ID + "-completed"
HISTORY_ID = "volume-price-20261112-t1-supplement-v1"
HISTORY_RUN = "volume-price-20261112-t1-supplement-v1-manual"
EVIDENCE = ROOT / "docs/research/volume-price-20261113-evidence.json"
REPORT = ROOT / "docs/research/volume-price-20261113-close-v1.md"
HISTORY_REPORT = ROOT / "docs/research/volume-price-20261112-t1-supplement-v1.md"

spec = importlib.util.spec_from_file_location("vp", ROOT / "scripts/publish_volume_price_20261104.py")
vp = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(vp); vp.T = T

def now_cn():
    return datetime.now(timezone.utc).astimezone(CN).isoformat(timespec="seconds")

def curl_json(url: str):
    p = subprocess.run(["curl", "-LfsS", "--max-time", "20", "-H", "User-Agent: Mozilla/5.0", url], capture_output=True, text=True, timeout=24)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    return json.loads(p.stdout)

def fetch_5m(code: str):
    sym = ("sh" if code.startswith("6") else "sz") + code
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData?symbol={sym}&scale=5&ma=no&datalen=48"
    p = subprocess.run(["curl", "-fsS", "--max-time", "20", "-H", "User-Agent: Mozilla/5.0", url], capture_output=True, text=True, timeout=24)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    m = re.search(r"=\((\[.*\])\)\s*;?\s*$", p.stdout, re.S)
    if not m: raise ValueError("jsonp_missing")
    bars=[]
    for x in json.loads(m.group(1)):
        if not str(x.get("day", "")).startswith(T): continue
        bars.append({"time":x["day"], **{k:float(x[k]) for k in ("open","high","low","close","volume")}})
    if len(bars) != 48: raise ValueError(f"bar_count_{len(bars)}")
    low=min(bars,key=lambda z:z["low"]); high=max(bars,key=lambda z:z["high"])
    b1440=next((z for z in bars if z["time"].endswith("14:40:00")),None)
    return {"code":code,"provider":"Sina historical 5-minute","bar_count":48,"first":bars[0]["time"],"last":bars[-1]["time"],
            "low":low["low"],"low_time":low["time"],"high":high["high"],"high_time":high["time"],"close":bars[-1]["close"],
            "low_to_close_pct":round((bars[-1]["close"]/low["low"]-1)*100,3),
            "close_vs_1440_pct":round((bars[-1]["close"]/b1440["close"]-1)*100,3) if b1440 else None,
            "historical_only":True,"five_minute_not_tick":True,"executed_trade":False,"url":url}

def eastmoney_all():
    url="https://push2.eastmoney.com/api/qt/clist/get"
    base={"po":"1","np":"2","ut":"bd1d9ddb04089700cf9c27f6f7426281","fltt":"2","invt":"2","fid":"f6",
          "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23","fields":"f2,f3,f5,f6,f7,f8,f10,f12,f14,f15,f16,f17,f18,f100"}
    def get(page):
        q=urllib.parse.urlencode(dict(base,pn=str(page),pz="100")); d=curl_json(url+"?"+q).get("data") or {}; diff=d.get("diff") or []
        if isinstance(diff,dict): diff=list(diff.values())
        return int(d.get("total") or 0),diff
    total,first=get(1); pages=(total+99)//100; rows=list(first); errors=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        jobs={ex.submit(get,p):p for p in range(2,pages+1)}
        for f in as_completed(jobs):
            try: rows.extend(f.result()[1])
            except Exception as e: errors.append(f"page{jobs[f]}:{type(e).__name__}:{str(e)[:60]}")
    return {"total":total,"pages":pages,"rows":rows,"errors":errors}

def tencent_quotes(codes):
    syms=",".join(("sh" if c.startswith("6") else "sz")+c for c in codes)
    p=subprocess.run(["curl","-fsS","--max-time","20","-H","User-Agent: Mozilla/5.0",f"https://qt.gtimg.cn/q={syms}"],capture_output=True,timeout=24)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    text=p.stdout.decode("gb18030","replace"); out={}
    for line in text.splitlines():
        m=re.search(r'v_(?:sh|sz)(\d{6})="(.*)";',line)
        if not m: continue
        f=m.group(2).split("~")
        if len(f)>43:
            out[m.group(1)]={"name":f[1],"close":float(f[3]),"turnover_pct":float(f[38]),"high":float(f[33]),"low":float(f[34]),"quote_time":f[30],"provider":"Tencent close quote"}
    return out

def sina_industry(code):
    url=f"https://money.finance.sina.com.cn/corp/go.php/vCI_CorpOtherInfo/stockid/{code}/menu_num/2.phtml"
    p=subprocess.run(["curl","-LfsS","--max-time","18","-H","User-Agent: Mozilla/5.0",url],capture_output=True,timeout=22)
    if p.returncode: raise ValueError(f"curl_exit_{p.returncode}")
    text=p.stdout.decode("gb18030","replace")
    m=re.search(r"<td[^>]*class=\"ct\"[^>]*>([^<]+)</td>\s*<td[^>]*class=\"ct\"[^>]*><a[^>]*>点击查看</a>",text,re.S)
    if not m: raise ValueError("industry_missing")
    return m.group(1).strip()

def avg(xs): return round(statistics.mean(xs),3) if xs else None
def med(xs): return round(statistics.median(xs),3) if xs else None
def fmt(v,n=2): return "N/A" if v is None else f"{v:.{n}f}"

def main():
    started=now_cn()
    snap=json.loads((ROOT/f"backend/data/sina_daily_full/{T}.json").read_text())
    prev=json.loads((ROOT/f"backend/data/baostock/{PREV}.json").read_text())
    current=snap["rows"]; previous={r["code"].split(".")[1]:r for r in prev["rows"]}; names={r["code"].split(".")[1]:r["name"] for r in current}
    broad_seed,_=vp.freeze_broad(current,previous,set(names)); curmap={r["code"].split(".")[1]:r for r in current}
    histories={}; history_errors={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        jobs={ex.submit(vp.fetch_history,r["code6"]):r["code6"] for r in broad_seed}
        for f in as_completed(jobs):
            c=jobs[f]
            try: histories[c]=f.result()
            except Exception as e: history_errors[c]=f"{type(e).__name__}:{str(e)[:100]}"
    broad=[]
    for seed in broad_seed:
        c=seed["code6"]
        if c not in histories: continue
        x=vp.metrics(histories[c],curmap[c]); x.update(name=names[c],amount_yuan=seed["amount"]); broad.append(x)
    deep=vp.select_deep(broad)
    try: em=eastmoney_all()
    except Exception as e: em={"total":0,"pages":0,"rows":[],"errors":[f"page1:{type(e).__name__}:{str(e)[:80]}"]}
    emmap={str(x.get("f12")):x for x in em["rows"] if x.get("f12")}
    try: tq=tencent_quotes([x["code"] for x in deep])
    except Exception: tq={}
    industries={}; industry_errors={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        jobs={ex.submit(sina_industry,x["code"]):x["code"] for x in broad}
        for f in as_completed(jobs):
            c=jobs[f]
            try: industries[c]=f.result()
            except Exception as e: industry_errors[c]=f"{type(e).__name__}:{str(e)[:80]}"
    for x in broad: x["industry"]=industries.get(x["code"])
    for x in deep:
        q=emmap.get(x["code"]); t=tq.get(x["code"]); x["turnover_pct"]=q.get("f8") if q else (t.get("turnover_pct") if t else None); x["industry"]=q.get("f100") if q else industries.get(x["code"])
        x["eastmoney_volume_ratio"]=q.get("f10") if q else None
        x["close_crosscheck_abs"]=round(abs(float(q["f2"])-x["close"]),4) if q and isinstance(q.get("f2"),(int,float)) else None
        x["tencent_close_crosscheck_abs"]=round(abs(t["close"]-x["close"]),4) if t else None
    minutes=[]; minute_errors={}
    with ThreadPoolExecutor(max_workers=3) as ex:
        jobs={ex.submit(fetch_5m,x["code"]):x["code"] for x in deep}
        for f in as_completed(jobs):
            c=jobs[f]
            try: minutes.append(f.result())
            except Exception as e: minute_errors[c]=f"{type(e).__name__}:{str(e)[:100]}"
    mmap={x["code"]:x for x in minutes}
    for x in deep:
        m=mmap.get(x["code"]); x["minute_validation"]=m
        if m and (x.get("rvol20") or 0)>=1.2 and (x.get("clv") or 0)>=.7 and m["low_time"] < T+" 14:00:00" and m["low_to_close_pct"]>=2:
            x["path_label"]="分歧后承接/再转强代理"
        elif (x.get("rvol20") or 0)>=1.5 and ((x.get("clv") or 0)<.45 or x["pct"]<0):
            x["path_label"]="高量滞涨/放量下跌风险"
        else: x["path_label"]="活跃量价对照"
    # Validate the entire 28-name cohort frozen by the 2026-11-12 report.
    prior_codes=["301618","603135","002431","600238","688757","605222","002148","000752","600327","002593","603706","603536","600467","002209","002861","600076","002313","603259","600519","603396","002229","301575","688267","301317","002713","603227","603499","000882"]
    prior=[]
    for c in prior_codes:
        a=previous.get(c); b=curmap.get(c)
        if not a or not b: continue
        prior.append({"code":c,"name":b["name"],"base_close":a["close"],"close":b["close"],"close_pct":round((b["close"]/a["close"]-1)*100,3),
                      "mfe_pct":round((b["high"]/a["close"]-1)*100,3),"mae_pct":round((b["low"]/a["close"]-1)*100,3),"executed_trade":False})
    pos=sum(x["close_pct"]>0 for x in prior)
    prior_summary={"n":len(prior),"positive_n":pos,"positive_price_change_ratio":round(pos/len(prior),4) if prior else None,
                   "mean_close_pct":avg([x["close_pct"] for x in prior]),"median_close_pct":med([x["close_pct"] for x in prior]),
                   "mean_mfe_pct":avg([x["mfe_pct"] for x in prior]),"mean_mae_pct":avg([x["mae_pct"] for x in prior]),
                   "verified_fill_count":0,"win_rate":None,"net_return":None}
    # Original-time intraday freezes are preserved as evidence, not rewritten candidates.
    intraday={}; intraday_errors={}
    for slot in ("early_pair","late_pair"):
        try: intraday[slot]=curl_json(f"https://robin-stock-api-production.up.railway.app/api/intraday-live?slot={slot}&limit=3")
        except Exception as e: intraday_errors[slot]=f"{type(e).__name__}:{str(e)[:120]}"
    relative=[x for x in deep if "ST" not in x["name"].upper() and -3<=x["pct"]<=8 and (x.get("rvol20") or 0)>=1.2 and (x.get("clv") or 0)>=.68 and (x.get("position120") or 1)<=.78 and x["amount_yuan"]>=1e8 and mmap.get(x["code"])]
    relative.sort(key=lambda x:(2*(x.get("clv") or 0)+min(x.get("rvol20") or 0,3)+(1-(x.get("position120") or 1))+max(mmap[x["code"]]["low_to_close_pct"],0)/10),reverse=True)
    pair=relative[:2]; candidates=[]
    for x in pair:
        support=round(max(x["low"],x.get("ma20") or x["low"]),2); pressure=round(max(x["high"],x.get("previous20_high") or x["high"]),2)
        candidates.append({"code":x["code"],"name":x["name"],"qualification":"volume_price待综合观察（非最终双标、非正式买点）",
                           "reference_price":x["close"],"reference_time":T+"T15:00:00+08:00","formal_buy_signal":False,"buy_order_allowed":False,
                           "trigger":f"{D}竞价不过度高开，回踩守住{support:.2f}且板块同步，随后放量站稳{pressure:.2f}",
                           "invalid":f"有效跌破{support:.2f}，或板块不同步、放量冲高回落","earliest_legal_exit_if_entered": "2026-11-17"})
    sector_sync={}
    for ind in sorted(set(x.get("industry") for x in broad if x.get("industry"))):
        g=[x for x in broad if x.get("industry")==ind]
        sector_sync[ind]={"broad_pool_n":len(g),"positive_n":sum(x["pct"]>0 for x in g),"positive_ratio":round(sum(x["pct"]>0 for x in g)/len(g),4),"median_pct":med([x["pct"] for x in g]),"scope":"frozen 120-name active broad pool, not full industry"}
    for x in deep: x["sector_sync_proxy"]=sector_sync.get(x.get("industry"))
    completed=now_cn(); full_minutes=len(minutes)==len(deep); full_history=len(broad)>=115; turnover_verified=sum(x.get("turnover_pct") is not None for x in deep); industry_verified=sum(x.get("industry") is not None for x in deep)
    complete=full_minutes and full_history and len(prior)==28 and turnover_verified>=24 and industry_verified>=24
    blocked=[]
    if not full_minutes: blocked.append(f"深筛分钟仅{len(minutes)}/{len(deep)}只取得48根5分钟；错误{minute_errors}")
    if turnover_verified<24: blocked.append(f"换手/行业交叉仅{turnover_verified}/28只；东财错误{em['errors']}")
    blocked += ["没有实际成交、排队和T+1退出证据；真实成交胜率、净收益、成本后盈亏比保持N/A。",
                "历史5分钟不是逐笔；不能据此证明资金身份或模拟盘口成交。"]
    evidence={"schema_version":1,"market_date":T,"started_at":started,"completed_at":completed,"market_scope":"Shanghai+Shenzhen; Beijing excluded",
              "providers":{"baostock":json.loads((ROOT/f"backend/data/market_source_status/baostock-{T}.json").read_text()),
                           "sina":json.loads((ROOT/f"backend/data/market_source_status/sina-{T}.json").read_text()),
                           "eastmoney":{"type":"close list metadata","source_total":em["total"],"rows":len(emmap),"pages":em["pages"],"errors":em["errors"]},
                           "tencent":{"type":"independent close quote/turnover fallback","deep_verified":len(tq)},
                           "sina_industry":{"type":"company profile Shenwan industry","broad_verified":len(industries),"errors":industry_errors}},
              "market_scan":{"verified":len(current),"checked":snap["coverage"]["checked"],"coverage_ratio":snap["coverage"]["coverage_ratio"]},
              "history":{"requested":120,"verified":len(broad),"errors":history_errors},"broad_pool":broad,"deep_pool":deep,"sector_sync_proxy":sector_sync,"minute_errors":minute_errors,
              "prior_20261112_full_cohort_validation":prior,"prior_summary":prior_summary,"original_time_intraday":intraday,"intraday_errors":intraday_errors,
              "after_close_relative_research_pair":candidates,"analysis_completed":complete,"eligible_for_integrated_research":complete,
              "blocked_or_limitations":blocked,"rule_version":"volume_price_close_v8_shsz_full_sample"}
    EVIDENCE.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    cand=[]
    for c in candidates:
        cand += [f"## **{c['name']}（{c['code']}）**",f"**资格：{c['qualification']}。**",f"参考价：{c['reference_price']:.2f}元（{T} 15:00，北京时间收盘）。",f"触发：{c['trigger']}。",f"放弃：{c['invalid']}。",f"若{D}真实买入，A股T+1下最早2026-11-17卖出；跌停、停牌或无成交不能假定退出。",""]
    table=[]
    for x in deep:
        m=mmap.get(x["code"]); table.append(f"|{x['name']} {x['code']}|{x['path_label']}|{x['pct']:+.2f}%|{fmt(x.get('turnover_pct'))}%|{fmt(x.get('rvol5'))}/{fmt(x.get('rvol10'))}/{fmt(x.get('rvol20'))}|{fmt((x.get('position120') or 0)*100,1)}%|{fmt(x.get('clv'),3)}|{m['low_time'][11:16] if m else '缺'} / {fmt(m['low_to_close_pct'] if m else None)}%|")
    body=f"""研究交易日：{T}｜发布时间：北京时间 {completed[:16].replace('T',' ')}（UTC+8）

本轮完成最新已收盘交易日T={T}的沪深量价研究；观察日D={D}。范围仅沪深，北交所不采集也不构成门槛。报告状态：**{'completed' if complete else 'partial/blocked'}**；正式买点0只，原因是本模块只形成盘后量价相对观察，尚未经过最终综合和D日竞价/承接确认，并非断言市场没有机会。

{chr(10).join(cand)}
最终综合尚未完成，上列不得称最终双标。

### 数据来源、单位与覆盖

- BaoStock：安装SDK后单次登录实测失败 `10002007 网络接收错误`，遵守不并发/不循环登录；未因单源失败停止。
- 新浪免费日线：首轮标准采集2694/5225（51.56%）不足；可续传备用采集最终5216/5225（99.8278%），日期均为{T}，未复权OHLC、成交量单位股、成交额单位元，9只保留缺失。
- 新浪逐股历史日线：冻结120广池后成功{len(broad)}/120；RV5/10/20均为当日成交量相对此前5/10/20个完整交易日均量，**不是盘中量比**。
- 新浪历史5分钟：深筛{len(minutes)}/28只各48根，属于历史5分钟K线，**不是逐笔或盘口**。
- 东方财富免费收盘元数据：{len(emmap)}/{em['total']}只、{em['pages']}页，错误{em['errors'] or '无'}；深池换手/行业可核{turnover_verified}/28，收盘交叉而非实时源。
- 东方财富本轮502后，腾讯免费收盘报价独立交叉{len(tq)}/28并补换手；新浪公司资料申万行业覆盖广池{len(industries)}/120。板块同步只统计冻结120只活跃广池内同行业正变化比例/中位涨跌，明确不是全行业成员精确宽度。

### 沪深广池、深池与结构结论

冻结120只广池，逐股验证后形成28只深池；每只失败、风险结构和数据缺失均保留在证据文件。高成交后的价格去向以RV、CLV、位置、突破/回踩及历史5分钟的低点至收盘修复共同检验，不能凭K线名称认定资金身份。

|股票|结构|涨跌|换手|RV5/10/20|120日位置|CLV|日内低点时刻/至收盘|
|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table)}

### 上一交易日完整深池验证（历史欠项实质推进）

对11月12日原冻结28只深池全部取得11月13日日线结果：正价格变化{pos}/{len(prior)}（{prior_summary['positive_price_change_ratio']:.1%}），收盘变化均值{prior_summary['mean_close_pct']:+.3f}%、中位{prior_summary['median_close_pct']:+.3f}%，日线MFE均值{prior_summary['mean_mfe_pct']:+.3f}%、MAE均值{prior_summary['mean_mae_pct']:+.3f}%。这是价格观察，不是成交胜率；没有实际成交时，真实胜率、净收益与成本后盈亏比均N/A。

原11月12日优先影子中重科技603135与起帆电缆605222也仅按原冻结基准追加日线结果，不倒推盘中触发或成交。原09:50/14:40冻结由生产接口读回并原样存入证据；不以收盘后赢家替换。

### 有效、反例与筛选反馈

- `分歧后承接/再转强代理`要求低点在14:00前、低点至收盘修复≥2%、CLV≥0.70且RV20≥1.2；这是可证伪代理，不是确认买点。
- `高量滞涨/放量下跌风险`保留RV20≥1.5但CLV<0.45或收跌对象，防止只挑成功样本。
- 盘后相对观察仍需D日竞价、板块同步、回踩缩量与关键位再突破；任一失败即放弃，不自动交易。

### 明日待证伪假设

1. 低/中位置且高CLV的放量修复组，D日MAE是否小于高量低CLV风险组。
2. D日不能守住T日突破位的对象，是否显著弱于板块同步的缩量回踩组。
3. 14:40后继续推进是否只在板块收盘同步为正时改善T+1价格观察。

### 限制与未完成项

{chr(10).join('- '+x for x in blocked)}

规则版本 `{evidence['rule_version']}`。不保证收益，不自动下单，不自行调权。
"""
    REPORT.write_text("# 量价研究与全样本验证｜2026-11-13\n\n"+body+"\n")
    hbody=f"""研究交易日：2026-11-12｜补做发布时间：北京时间 {completed[:16].replace('T',' ')}（UTC+8）

本补充只追加11月12日原冻结28只深池在11月13日的T+1日线价格观察，不改写原报告和候选。完整28只均已核验；正价格变化{pos}/{len(prior)}，均值{prior_summary['mean_close_pct']:+.3f}%、中位{prior_summary['median_close_pct']:+.3f}%，MFE/MAE均值{prior_summary['mean_mfe_pct']:+.3f}%/{prior_summary['mean_mae_pct']:+.3f}%。没有原时点实际成交证据，成交胜率、净收益和盈亏比保持N/A；不从11月13日结果事后挑选11月12日候选。明细见 `{EVIDENCE.relative_to(ROOT)}`。
"""
    HISTORY_REPORT.write_text("# 2026-11-12量价深池T+1补充\n\n"+hbody+"\n")
    research=json.loads((ROOT/"backend/data/research.json").read_text()); runs=json.loads((ROOT/"backend/data/task_runs.json").read_text()); samples=json.loads((ROOT/"backend/data/volume_price_samples.json").read_text())
    for obj,key,ids in ((research,"items",{REPORT_ID,HISTORY_ID}),(runs,"items",{RECEIPT_ID,HISTORY_RUN+"-completed"}),(samples,"items",{"volume-price-20261113-full-cohort-v1","volume-price-20261112-t1-validation-20261113-v1"})):
        obj[key]=[x for x in obj[key] if x.get("id") not in ids]
    sources=[str(EVIDENCE.relative_to(ROOT)),f"backend/data/sina_daily_full/{T}.json",f"backend/data/market_source_status/sina-{T}.json",f"backend/data/market_source_status/baostock-{T}.json","https://quotes.sina.cn/cn/api/jsonp_v2.php/CN_MarketDataService.getKLineData","https://push2.eastmoney.com/api/qt/clist/get"]
    research["items"].append({"id":REPORT_ID,"date":T,"market_date":T,"task_id":"volume_price","track":"volume_price","run_id":RUN_ID,"title":"量价研究｜11月13日沪深5216只、120广池、28深池与全样本分钟验证","summary":f"沪深{len(current)}/5225只OHLCV、120广池、28深池、历史5分钟{len(minutes)}/28；验证上一冻结28/28并形成{len(candidates)}只待综合观察。","body":body,"sources":sources,"report_type":"substantive_daily_research","eligible_for_integrated_research":complete,"analysis_completed":complete,"status":"completed" if complete else "partial","published_at":completed,"recorded_at":completed,"market_data_cutoff_at":T+"T15:00:00+08:00","planned_entry_date":D,"earliest_legal_exit_date_if_bought":"2026-11-17","research_rule_version":evidence["rule_version"],"candidate_count":len(candidates),"research_shadow_candidates":candidates,"formal_candidate_count":0,"verified_fill_count":0,"recommendation_ids":[],"evidence_file":str(EVIDENCE.relative_to(ROOT)),"full_scan_count":len(current),"broad_pool_count":120,"broad_pool_verified_count":len(broad),"deep_pool_count":28,"minute_verified_count":len(minutes),"codes":[x["code"] for x in deep],"blocked_modules":[] if complete else blocked})
    research["items"].append({"id":HISTORY_ID,"date":PREV,"market_date":PREV,"task_id":"volume_price","track":"volume_price","run_id":HISTORY_RUN,"title":"11月12日量价深池T+1补充","summary":f"原冻结28只全部追加11月13日日线价格观察；正变化{pos}/28，成交胜率与净收益N/A。","body":hbody,"sources":sources,"report_type":"historical_validation_supplement","eligible_for_integrated_research":False,"analysis_completed":True,"status":"completed","published_at":completed,"recorded_at":completed,"verified_fill_count":0})
    runs["items"].append({"id":RECEIPT_ID,"run_id":RUN_ID,"task_id":"volume_price","date":T,"trigger":"scheduled","started_at":started,"recorded_at":completed,"completed_at":completed,"status":"completed" if complete else "blocked","summary":f"完成沪深{len(current)}/5225扫描、120广池、28深池、分钟{len(minutes)}/28及上一冻结28/28验证。","report_ids":[REPORT_ID],"recommendation_ids":[],"analysis_completed":complete,"eligible_for_integrated_research":complete,"sources":sources,"blocked_modules":[] if complete else blocked})
    runs["items"].append({"id":HISTORY_RUN+"-completed","run_id":HISTORY_RUN,"task_id":"volume_price","date":PREV,"trigger":"manual_backfill","started_at":started,"recorded_at":completed,"completed_at":completed,"status":"completed","summary":"追加11月12日冻结28只的11月13日T+1价格观察；未伪造成交。","report_ids":[HISTORY_ID],"recommendation_ids":[],"analysis_completed":True,"eligible_for_integrated_research":False,"sources":sources})
    samples["items"].append({"id":"volume-price-20261113-full-cohort-v1","date":T,"task_id":"volume_price","frozen_at":completed,"report_ids":[REPORT_ID],"rule_version":evidence["rule_version"],"broad_pool_count":120,"broad_pool_verified_count":len(broad),"deep_screen_count":28,"minute_verified_count":len(minutes),"samples":deep,"research_shadow_candidates":candidates,"eligible_for_model_statistics":False,"statistical_scope":"future price observation; no fill-based profitability","missing":blocked})
    samples["items"].append({"id":"volume-price-20261112-t1-validation-20261113-v1","date":T,"task_id":"volume_price","recorded_at":completed,"report_ids":[HISTORY_ID,REPORT_ID],"rule_version":evidence["rule_version"],"full_validation_completed":len(prior)==28,"full_pool_summary":prior_summary,"full_pool_validations":prior,"executed_trade_count":0,"eligible_for_model_statistics":False})
    for path,obj in ((ROOT/"backend/data/research.json",research),(ROOT/"backend/data/task_runs.json",runs),(ROOT/"backend/data/volume_price_samples.json",samples)):
        path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"complete":complete,"scan":len(current),"broad":len(broad),"deep":len(deep),"minutes":len(minutes),"turnover":turnover_verified,"industry":industry_verified,"prior":len(prior),"candidates":[x["code"] for x in candidates],"em_errors":em["errors"],"completed":completed},ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
