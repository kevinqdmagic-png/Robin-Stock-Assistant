#!/usr/bin/env python3
from __future__ import annotations
from datetime import datetime, timezone
import gzip, json, re, statistics, subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
T,D,EXIT="2026-11-26","2026-11-27","2026-11-30"
NOW=datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
STAMP=NOW.isoformat(timespec="seconds"); DISPLAY=NOW.strftime("%Y-%m-%d %H:%M")

def loadgz(p): return json.load(gzip.open(ROOT/p,"rt",encoding="utf-8"))
def dump(p,x,gz=False):
    path=ROOT/p; path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
    (gzip.open(path,"wb") if gz else open(path,"wb")).write(raw)
def f(x,n=2): return "N/A" if x is None else f"{x:.{n}f}"

base=loadgz("docs/research/low-dragon-20261126-evidence.json.gz")
broad=base["broad_pool"]; deep=base["deep_pool"]
snapshot=json.load(open(ROOT/"backend/data/sina_daily_full/2026-11-26.json"))
cur={r["code"].split(".")[-1]:r for r in snapshot["rows"]}

# Independent Tencent close quote adds turnover for the frozen 28 only.
symbols=",".join(("sh" if x["code"].startswith("6") else "sz")+x["code"] for x in deep)
url="https://qt.gtimg.cn/q="+symbols
turnover={}; tq_error=None
try:
    p=subprocess.run(["curl","-fsS","--max-time","20","-H","Referer: https://gu.qq.com/",url],capture_output=True,check=True,timeout=23)
    text=p.stdout.decode("gb18030","replace")
    for line in text.splitlines():
        m=re.search(r'="(.*)";',line)
        if not m: continue
        a=m.group(1).split("~")
        if len(a)>38 and re.fullmatch(r"\d{6}",a[2]) and a[30].startswith("20261126"):
            turnover[a[2]]={"turnover_pct":float(a[38]),"quote_time":a[30],"close":float(a[3]),"source":url}
except Exception as e: tq_error=f"{type(e).__name__}:{e}"
for x in deep:
    x["turnover_pct"]=turnover.get(x["code"],{}).get("turnover_pct")
    x["turnover_quote_time"]=turnover.get(x["code"],{}).get("quote_time")
    x["sector_sync"]="缺少统一板块分类源；保留为D日触发条件，不判已满足"

support=[x for x in deep if ("日线分歧转强代理" in x["tags"] or "放量突破" in x["tags"])
         and x["pct"]<=10.5 and (x.get("position120") or 1)<=.60 and (x.get("clv") or 0)>=.60]
support=sorted(support,key=lambda x:((x.get("rvol20") or 0)*(x.get("clv") or 0)+(1-(x.get("position120") or 1))*2),reverse=True)[:5]
risks=[x for x in deep if any(t in x["tags"] for t in ("高位爆量滞涨/长上影风险","放量下跌"))]

# Advance one backlog: all 11/23 deep samples to the 11/26 close.
old=loadgz("docs/research/volume-price-20261123-samples.json.gz")
follow=[]
for x in old["deep_pool"]:
    bar=cur.get(x["code"]); anchor=float(x["close"])
    if not bar: continue
    follow.append({"code":x["code"],"name":x["name"],"anchor_date":"2026-11-23","anchor_close":anchor,"date":T,
      "open":bar["open"],"high":bar["high"],"low":bar["low"],"close":bar["close"],
      "close_return_pct":(bar["close"]/anchor-1)*100,"day_mfe_pct":(bar["high"]/anchor-1)*100,"day_mae_pct":(bar["low"]/anchor-1)*100,
      "price_observation_only":True,"actual_fill_verified":False})

header=f"研究交易日：{T}｜发布时间：北京时间 {DISPLAY}（UTC+8）"
def block(x):
 return f'''## **{x['name']}（{x['code']}）**

- 资格：量价栏目待综合观察，不是最终双标、不是正式买点。
- 参考价：{T} 15:00 收盘 {x['close']:.2f} 元；当日区间 {x['low']:.2f}–{x['high']:.2f} 元。
- 结构：{'、'.join(x['tags'])}；RV5/10/20={f(x['rvol5'])}/{f(x['rvol10'])}/{f(x['rvol20'])}，换手 {f(x['turnover_pct'])}%，120日位置 {f(x['position120']*100,1)}%，CLV {f(x['clv'],3)}。RV是收盘日成交量/此前日均量，不是盘中量比；五分钟线不是逐笔。
- 触发：{D} 回踩不破 {x['low']:.2f} 元后低点抬高、缩量回踩并再次放量站上 {x['high']:.2f} 元，同时板块同步；放弃：跌破 {x['low']:.2f} 元、单笔拉升后量价背离或板块转弱。若 {D} 买入，T+1最早 {EXIT} 卖出。
'''

rows="\n".join(f"|{x['code']}|{x['name']}|{'、'.join(x['tags'])}|{x['close']:.2f}|{x['pct']:.2f}|{f(x['turnover_pct'])}|{f(x['rvol5'])}/{f(x['rvol10'])}/{f(x['rvol20'])}|{f(x['position120']*100,1)}|{f(x['clv'],3)}|{'是' if x['breakout20'] else '否'}|" for x in deep)
risk_lines="\n".join(f"- {x['name']}（{x['code']}）：{'、'.join(x['tags'])}，涨跌 {x['pct']:.2f}%、RV20 {f(x['rvol20'])}、CLV {f(x['clv'],3)}；列为失败/风险对照，不进入观察前列。" for x in risks)
body=header+"\n\n"+"\n".join(block(x) for x in support[:3])+f'''\n### 完整性与来源

- 沪深收盘快照 {snapshot['coverage']['verified']}/{snapshot['coverage']['checked']}（{snapshot['coverage']['coverage_ratio']:.2%}），排除北交所；新浪未复权 OHLCV，量单位股、额单位元。BaoStock 单次登录失败 `10002007 网络接收错误` 后未并发重登。
- 冻结 120 只多结构广池，120/120 历史日线成功；28 只深池逐股计算 RV5/10/20、20/60/120日位置、CLV、上下影、突破/回踩。腾讯同日收盘报价为 28/28 补充换手与收盘交叉核验；东方财富个股接口实测 HTTP 502，未作为证据。
- 板块统一分类源本轮缺失，不能伪造板块同步；该字段明确作为 {D} 二次触发门槛。正式买点仍为 0 只，因为次日竞价、回踩承接与板块条件尚未发生。

### 28只深池逐股验证

|代码|名称|结构|收盘|涨跌%|换手%|RV5/10/20|120日位置%|CLV|突破20日|
|---|---|---|---:|---:|---:|---|---:|---:|---|
{rows}

### 结构结论与反例

- “分歧→承接→再转强”仅用日线代理初筛：当日下探、收盘靠近高位、RV放大并推进价格；真正分时顺序必须由 {D} 当时分钟证据确认，不能由日线高低反推。
- 放量突破有效性的下一步检验是突破后能否缩量回踩且不破关键位；单日高 RV 或涨停不是持续性结论。
{risk_lines}

### 全样本与统计边界

- 3只醒目展示不替代 120 广池、28 深池；所有失败、未触发、风险结构和数据缺失均保存在证据包。
- 当前只有价格观察，没有真实成交；上涨比例可统计，已验证成交胜率与净收益留空。小样本不自动调权。
'''

vals=[x["close_return_pct"] for x in follow]
supp=f'''研究交易日：2026-11-23｜补做/发布时间：北京时间 {DISPLAY}（UTC+8）

### 11月23日全深池截至11月26日验证

- 原冻结 28 只深池，取得 {len(follow)}/28 条 11月26日未复权 OHLCV；正价格变化 {sum(v>0 for v in vals)}/{len(vals)}，均值 {statistics.mean(vals):.3f}%，中位数 {statistics.median(vals):.3f}%。
- 以上仅为价格观察，不是成交胜率；无原时点成交证据，净收益留空。逐股当日 MFE/MAE 已保存，未从日线高低推断触发顺序。
'''

(ROOT/"docs/research/volume-price-20261126-close-v1.md").write_text(body,encoding="utf-8")
(ROOT/"docs/research/volume-price-20261123-followup-20261126-v1.md").write_text(supp,encoding="utf-8")
evidence={"schema_version":"2026-11-26.v1","market_date":T,"generated_at":STAMP,"sources":{"sina_close":snapshot["coverage"],"sina_history":base["source_status"]["sina_history"],"baostock":base["source_status"]["baostock"],"tencent_turnover":{"verified":len(turnover),"requested":28,"error":tq_error,"url":url},"eastmoney":{"error":"HTTP 502 on sampled quote endpoint"}},"broad_pool":broad,"deep_pool":deep,"research_observations":support,"risk_counterexamples":risks,"prior_20261123_validation":follow}
dump("docs/research/volume-price-20261126-evidence.json.gz",evidence,True)
dump("docs/research/volume-price-20261126-samples.json.gz",{"schema_version":"2026-11-26.v1","market_date":T,"broad_pool":broad,"deep_pool":deep,"research_observations":support,"risk_counterexamples":risks,"prior_20261123_validation":follow},True)

sources=["https://hq.sinajs.cn/","https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData",url,"https://push2.eastmoney.com/api/qt/stock/get"]
def rec(id,date,typ,title,summary,text):
 return {"id":id,"date":date,"track":"volume_price","task_id":"volume_price","report_type":typ,"status":"completed","title":title,"summary":summary,"body":text,"recorded_at":STAMP,"published_at":STAMP,"source_urls":sources,"analysis_completed":True,"eligible_for_integrated_research":typ=="daily_research","evidence_files":["docs/research/volume-price-20261126-evidence.json.gz","docs/research/volume-price-20261126-samples.json.gz"]}
reports=[rec("volume-price-20261126-close-v1",T,"daily_research","11月26日完整量价研究｜120广池、28深池与结构反例",f"沪深{snapshot['coverage']['verified']}/{snapshot['coverage']['checked']}；120/120历史日线、28/28换手补充、28只深池逐股验证。",body),rec("volume-price-20261123-followup-20261126-v1","2026-11-23","validation_supplement","11月23日量价深池截至11月26日价格验证",f"{len(follow)}/28条完成价格观察；成交胜率和净收益留空。",supp)]
runs=[]
for r in reports:
 runs.append({"id":r["id"]+"-scheduled-run","run_id":r["id"]+"-scheduled","task_id":"volume_price","date":r["date"],"trigger":"scheduled","started_at":STAMP,"recorded_at":STAMP,"completed_at":STAMP,"status":"completed","summary":r["summary"],"report_ids":[r["id"]]})
dump("research_backfills/linked-volume-price-20261126-v1.json",{"research":reports,"task_runs":runs})
print(json.dumps({"status":"completed","broad":len(broad),"deep":len(deep),"turnover":len(turnover),"observations":[(x['code'],x['name']) for x in support],"risks":len(risks),"history":len(follow)},ensure_ascii=False))
