#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip, hashlib, json, re, statistics, sys, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publish_volume_price_20261104 as vp

T, PREV, D = "2026-11-26", "2026-11-25", "2026-11-27"
EXIT = "2026-11-30"
CN = ZoneInfo("Asia/Shanghai")
NOW = datetime.now(timezone.utc).astimezone(CN)
STAMP = NOW.isoformat(timespec="seconds")
DISPLAY = NOW.strftime("%Y-%m-%d %H:%M")

def dump(path, data, gz=False):
    path = ROOT / path; path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode()
    (gzip.open(path, "wb") if gz else open(path, "wb")).write(raw)

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.szse.cn/"})
    with urllib.request.urlopen(req,timeout=25) as r: return json.loads(r.read().decode("utf-8"))

def c6(r): return str(r["code"]).split(".")[-1]
def valid(c): return bool(re.fullmatch(r"(?:6\d{5}|00\d{4}|30\d{4})", c))
def f(x,n=2): return "N/A" if x is None else f"{x:.{n}f}"
def pct(x): return f(x,2)+"%" if x is not None else "N/A"

cur_doc=json.load(open(ROOT/f"backend/data/sina_daily_full/{T}.json"))
pre_doc=json.load(open(ROOT/f"backend/data/sina_daily_full/{PREV}.json"))
cur={c6(r):r for r in cur_doc["rows"] if valid(c6(r))}
pre={c6(r):r for r in pre_doc["rows"] if valid(c6(r))}

# Freeze 120-name broad pool and calculate 150-day history metrics.
vp.T=T
broad, market = vp.freeze_broad(cur_doc["rows"], pre, set(cur))
hist, errors = {}, {}
with ThreadPoolExecutor(max_workers=24) as ex:
    fut={ex.submit(vp.fetch_history,r["code6"],1):r["code6"] for r in broad}
    for q in as_completed(fut):
        code=fut[q]
        try: hist[code]=q.result()
        except Exception as e: errors[code]=f"{type(e).__name__}:{e}"
metrics=[]
for r in broad:
    code=r["code6"]
    if code in hist:
        m=vp.metrics(hist[code],cur[code]); m["name"]=cur[code]["name"]; m["amount"]=cur[code]["amount"]
        metrics.append(m)
deep=vp.select_deep(metrics)

low_candidates=[]
for m in metrics:
    if "ST" in m["name"].upper(): continue
    pos=m.get("position120"); rv=m.get("rvol20"); clv=m.get("clv")
    if pos is None or rv is None or clv is None: continue
    # Low-position research excludes already accelerated 19/20% one-day moves.
    if pos <= .50 and rv >= 1.20 and clv >= .55 and .5 <= m["pct"] <= 10.5:
        if m.get("breakout20"): model="低位放量突破"
        elif m["low"] < m["open"] and clv >= .72: model="低位分歧承接"
        else: model="低位首次放量观察"
        score=(.5-pos)*2 + min(rv,6)/6 + clv + min(max(m["pct"],0),10)/20
        low_candidates.append({**m,"model":model,"score":score})
low_candidates=sorted(low_candidates,key=lambda x:(x["score"],x["amount"]),reverse=True)[:5]

# Track every immutable legacy low-position sample; never delete failures.
ledger=json.load(open(ROOT/"backend/data/low_position_samples.json"))
# Rebuild only this not-yet-published run's T rows; prior dates stay immutable.
ledger["items"]=[x for x in ledger["items"] if x.get("date") != T]
legacy=[]
for item in ledger["items"]:
    if item.get("date") == T:
        continue
    code=item["code"]; bar=cur.get(code); anchor=float(item["day0_close"]); inv=item.get("invalid_close_below")
    rec={"id":item["id"],"code":code,"name":item["name"],"anchor_date":item["date"],"anchor_close":anchor,
         "original_snapshot_verified":item.get("original_snapshot_verified"),"eligible_for_model_statistics":item.get("eligible_for_model_statistics")}
    if bar:
        rec.update({"date":T,"open":bar["open"],"high":bar["high"],"low":bar["low"],"close":bar["close"],
                    "volume":bar["volume"],"close_return_pct":(bar["close"]/anchor-1)*100,
                    "below_original_invalid_close": bool(inv is not None and bar["close"] < float(inv))})
    else: rec["missing_reason"]="same-day SH/SZ close snapshot missing"
    legacy.append(rec)

# Today's immutable conditions are published in the dated samples archive below.
# The long-running legacy ledger is read-only here so a daily build cannot
# rewrite or reformat older frozen records.

# Public-copy dragon/tiger events, with BUY/SELL union per exact TRADE_ID.
pub=json.load(open(ROOT/f"docs/research/{T.replace('-','')}-lhb-public-copy.json"))
summ=pub["main_list"]["rows"]
events=[]; signatures={}
for s in summ:
    code=str(s.get("SECURITY_CODE","")); tid=str(s.get("TRADE_ID",""))
    if not valid(code): continue
    rows=[]; seen=set()
    for side in ("BUY","SELL"):
        for r in pub["seat_queries"].get(code,{}).get(side,{}).get("rows",[]):
            if str(r.get("TRADE_ID")) != tid: continue
            key=(r.get("OPERATEDEPT_CODE"),r.get("OPERATEDEPT_NAME"),round(float(r.get("BUY") or 0),2),round(float(r.get("SELL") or 0),2))
            if key not in seen: seen.add(key); rows.append(r)
    buy=sum(float(r.get("BUY") or 0) for r in rows); sell=sum(float(r.get("SELL") or 0) for r in rows)
    inst=sum(float(r.get("NET") or 0) for r in rows if "机构专用" in str(r.get("OPERATEDEPT_NAME")))
    connect=sum(float(r.get("NET") or 0) for r in rows if "股通专用" in str(r.get("OPERATEDEPT_NAME")))
    sig=hashlib.sha256(json.dumps(sorted((r.get("OPERATEDEPT_NAME"),round(float(r.get("BUY") or 0),2),round(float(r.get("SELL") or 0),2)) for r in rows),ensure_ascii=False).encode()).hexdigest()[:16]
    period="multi_day" if any(x in str(s.get("EXPLANATION","")) for x in ("连续","三个交易日","异常期间")) else "single_day"
    dup=(code,period,sig) in signatures; signatures[(code,period,sig)]=tid
    event={"trade_id":tid,"code":code,"name":s.get("SECURITY_NAME_ABBR"),"reason":s.get("EXPLANATION"),"period_type":period,
      "close":float(s.get("CLOSE_PRICE") or 0),"change_pct":float(s.get("CHANGE_RATE") or 0),"turnover_pct":float(s.get("TURNOVERRATE") or 0),
      "buy_yuan":buy,"sell_yuan":sell,"net_yuan":buy-sell,"institution_net_yuan":inst,"connect_net_yuan":connect,
      "seat_count":len(rows),"buy_concentration":max([float(r.get("BUY") or 0) for r in rows] or [0])/buy if buy else None,
      "sell_concentration":max([float(r.get("SELL") or 0) for r in rows] or [0])/sell if sell else None,
      "seat_signature":sig,"duplicate_content":dup}
    events.append(event)

# Fetch every SZSE official page and every detail; preserve raw evidence.
sz_pages=[]; sz_details={}; official_errors=[]
base="https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1842_xxpl&txtStart=2026-11-26&txtEnd=2026-11-26&tab1PAGENO={}"
for page in range(1,6):
    try: sz_pages.append(get_json(base.format(page)))
    except Exception as e: official_errors.append(f"SZSE page {page}: {type(e).__name__}:{e}")
params=[]
for payload in sz_pages:
    for block in payload:
        for row in block.get("data",[]):
            m=re.search(r"a-param=['\"]([^'\"]+)",str(row.get("bz","")))
            if m: params.append(m.group(1).replace("&amp;","&"))
def fetch_sz_detail(p):
    u="https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1842_detal&"+p
    return p,get_json(u)
with ThreadPoolExecutor(max_workers=12) as ex:
    fut={ex.submit(fetch_sz_detail,p):p for p in params}
    for q in as_completed(fut):
        p=fut[q]
        try:
            key,value=q.result(); sz_details[key]=value
        except Exception as e: official_errors.append(f"SZSE detail {p}: {type(e).__name__}:{e}")

def load_tmp(p):
    try: return json.load(open(p))
    except Exception as e: official_errors.append(f"{p}: {type(e).__name__}:{e}"); return None
sse_main=load_tmp("/tmp/sse_main_20261126.json")
sse_star=load_tmp("/tmp/sse_star_20261126.json")
official_ok=bool(sse_main and sse_star and len(sz_pages)==5 and len(sz_details)==45 and not official_errors)

# Rank independent dragon observations. Formal buy permission remains zero.
dragon_candidates=[]
for e in events:
    if e["duplicate_content"] or e["period_type"]!="single_day" or "ST" in str(e["name"]).upper(): continue
    bar=cur.get(e["code"])
    if not bar or e["net_yuan"] <= 0 or e["change_pct"] < 0: continue
    risk=max(e["turnover_pct"]-25,0)/20
    score=e["net_yuan"]/1e8 + max(e["institution_net_yuan"],0)/2e8 + max(e["connect_net_yuan"],0)/2e8 - risk
    dragon_candidates.append({**e,"day_low":bar["low"],"day_high":bar["high"],"score":score})
dragon_candidates=sorted(dragon_candidates,key=lambda x:x["score"],reverse=True)[:5]

# Advance one historical backlog: every 11/20 new low sample and every unique dragon code to 11/26.
old=json.load(gzip.open(ROOT/"docs/research/low-dragon-20261120-samples.json.gz","rt"))
follow=[]
anchors=[]
for x in old.get("low_position_samples",[]): anchors.append(("low_position",x["code"],x["name"],float(x.get("close") or x.get("anchor_close") or 0)))
seen=set()
for x in old.get("dragon_tiger_events",[]):
    if x["code"] not in seen: anchors.append(("dragon_tiger",x["code"],x["name"],float(x["close"]))); seen.add(x["code"])
for track,code,name,anchor in anchors:
    bar=cur.get(code)
    if bar and anchor>0: follow.append({"track":track,"code":code,"name":name,"anchor_date":"2026-11-20","anchor_close":anchor,"date":T,
      "open":bar["open"],"high":bar["high"],"low":bar["low"],"close":bar["close"],"close_return_pct":(bar["close"]/anchor-1)*100,
      "day_mfe_pct":(bar["high"]/anchor-1)*100,"day_mae_pct":(bar["low"]/anchor-1)*100,"price_observation_only":True})

header=f"研究交易日：{T}｜发布时间：北京时间 {DISPLAY}（UTC+8）"
def low_block(m):
    return f'''## **{m['name']}（{m['code']}）**

- 资格：低位栏目待综合观察，不是最终双标、不是正式买点。
- 参考价：{T} 15:00 收盘 {m['close']:.2f} 元；当日区间 {m['low']:.2f}–{m['high']:.2f} 元。
- 量价：{m['model']}；RV5/10/20={f(m['rvol5'])}/{f(m['rvol10'])}/{f(m['rvol20'])}，120日位置 {f(m['position120']*100,1)}%，CLV {f(m['clv'],3)}。RV是收盘日量相对历史日均量，不是盘中量比。
- 触发：{D} 回踩不破 {m['low']:.2f} 元后重新站上 {m['high']:.2f} 元，且板块同步；放弃：跌破 {m['low']:.2f} 元、放量滞涨或板块转弱。若 {D} 买入，T+1最早 {EXIT} 卖出。
'''
def dragon_block(e):
    return f'''## **{e['name']}（{e['code']}）**

- 资格：龙虎榜栏目待综合观察，不是最终双标、不是正式买点。
- 参考价：{T} 15:00 收盘 {e['close']:.2f} 元；当日区间 {e['day_low']:.2f}–{e['day_high']:.2f} 元。
- 事件：{e['period_type']}，{e['reason']}；买/卖/净额 {e['buy_yuan']/1e6:.1f}/{e['sell_yuan']/1e6:.1f}/{e['net_yuan']/1e6:.1f} 百万元，机构净 {e['institution_net_yuan']/1e6:.1f} 百万元，股通净 {e['connect_net_yuan']/1e6:.1f} 百万元。公开席位名称不确认最终账户。
- 触发：{D} 不高开加速，回踩不破 {e['day_low']:.2f} 元后量价再转强且板块同步；放弃：跌破 {e['day_low']:.2f} 元、净卖出/放量滞涨或板块转弱。若 {D} 买入，T+1最早 {EXIT} 卖出。
'''

low_table="\n".join(f"|{m['code']}|{m['name']}|{m['model']}|{m['close']:.2f}|{m['pct']:.2f}|{f(m['rvol5'])}/{f(m['rvol10'])}/{f(m['rvol20'])}|{f(m['position120']*100,1)}|{f(m['clv'],3)}|{'是' if m['breakout20'] else '否'}|" for m in low_candidates)
low_body=header+"\n\n"+"\n".join(low_block(x) for x in low_candidates[:2])+f'''\n### 结论与证据边界

- 独立完整 low_position 研究；正式买点 0 只，原因是次日竞价、板块与承接尚未发生，不代表市场确定无机会。
- 沪深收盘快照覆盖 {cur_doc['coverage']['verified']}/{cur_doc['coverage']['checked']}（{cur_doc['coverage']['coverage_ratio']:.2%}），排除北交所；未复权 OHLCV，量单位股、额单位元。BaoStock 单次登录失败 `10002007 网络接收错误`，未并发重登；独立新浪源完成替代。
- 广域 120 只，历史日线成功 {len(metrics)}/120，深池 {len(deep)} 只，逐股数据均在证据包；展示两只不替代全样本。板块分类源本轮缺失，因此“板块同步”保留为次日触发门槛，不作已满足断言。

### 新增冻结样本

|代码|名称|模型|收盘|涨跌%|RV5/10/20|120日位置%|CLV|突破20日|
|---|---|---|---:|---:|---|---:|---:|---|
{low_table}

### 旧30日样本全量跟踪

- 原冻结 {len(legacy)} 条，本轮收盘取得 {sum('close' in x for x in legacy)}/{len(legacy)}；正价格变化 {sum(x.get('close_return_pct',-1)>0 for x in legacy)} 条，跌破原失效线 {sum(x.get('below_original_invalid_close',False) for x in legacy)} 条。
- 仅为价格观察；没有真实成交，成交胜率和净收益留空。成功、失败和缺失全部保留。

### 反例与风险

- 深池保留高量滞涨、放量下跌和假突破对照；单日高RV、涨停或长阳均不等于主力建仓完成。
- 次日若高开加速后量价背离、跌破冻结低点或板块不同步，样本按失败/未触发追加，不删除。
'''

dt_rows="\n".join(f"|{e['code']}|{e['name']}|{'多日' if e['period_type']=='multi_day' else '单日'}|{str(e['reason'])[:25]}|{e['change_pct']:.2f}|{e['turnover_pct']:.2f}|{e['buy_yuan']/1e6:.1f}|{e['sell_yuan']/1e6:.1f}|{e['net_yuan']/1e6:.1f}|{e['institution_net_yuan']/1e6:.1f}|{e['connect_net_yuan']/1e6:.1f}|{'是' if e['duplicate_content'] else '否'}|" for e in events)
neg=sorted([e for e in events if not e['duplicate_content']],key=lambda x:x['net_yuan'])[:3]
dt_body=header+"\n\n"+"\n".join(dragon_block(x) for x in dragon_candidates[:3])+f'''\n### 结论与来源核验

- 独立完整 dragon_tiger 研究；正式买点 0 只，次日竞价和承接尚未发生。公开副本沪深事件 {len(events)} 条，所有事件按 `TRADE_ID` 配对买卖两侧并对相同经济行去重。
- 深交所官方 5/5 摘要页、45/45 明细成功；上交所主板与科创板官方端点均返回同日有效正文。官方原文与东方财富公开副本相互独立；单日/多日及不同原因不混加。
- 机构专用、沪/深股通仅按公开席位名称统计，不确认最终账户；五分钟线不是逐笔，本报告没有把任何榜单推断为盘中成交顺序。

### 全事件摘要（金额百万元）

|代码|名称|周期|原因|涨跌%|换手%|买|卖|净|机构净|股通净|重复内容|
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
{dt_rows}

### 失败反例

''' + "\n".join(f"- {x['name']}（{x['code']}）：净额 {x['net_yuan']/1e6:.1f} 百万元、涨跌 {x['change_pct']:.2f}%、换手 {x['turnover_pct']:.2f}%；席位标签不能覆盖价格/净卖出风险。" for x in neg) + "\n"

follow_vals=[x['close_return_pct'] for x in follow]
follow_body=f'''研究交易日：2026-11-20｜补做/发布时间：北京时间 {DISPLAY}（UTC+8）

### 历史欠项推进

- 2026-11-20 低位新增与龙虎榜独立代码共 {len(anchors)} 条锚点，2026-11-26 取得 {len(follow)} 条未复权 OHLCV。
- 收盘正变化 {sum(x>0 for x in follow_vals)}/{len(follow_vals)}，均值 {statistics.mean(follow_vals):.3f}%，中位数 {statistics.median(follow_vals):.3f}%。这是价格观察比例，不是成交胜率；无原时点成交证据，净收益留空。
- 每条当日 MFE/MAE 与 OHLCV 已写入证据包；不由日线高低反推触发顺序。
'''

report_paths={
 "low-position-20261126-close-v1.md":low_body,
 "dragon-tiger-20261126-close-v1.md":dt_body,
 "low-dragon-20261120-followup-20261126-v1.md":follow_body,
}
for fn,body in report_paths.items(): (ROOT/"docs/research"/fn).write_text(body,encoding="utf-8")

evidence={"schema_version":"2026-11-26.v1","market_date":T,"generated_at":STAMP,
 "source_status":{"sina":cur_doc["coverage"],"baostock":json.load(open(ROOT/f"backend/data/market_source_status/baostock-{T}.json")),
 "sina_history":{"requested":120,"verified":len(metrics),"errors":errors},"official":{"sse_main":bool(sse_main),"sse_star":bool(sse_star),"szse_pages":len(sz_pages),"szse_details":len(sz_details),"errors":official_errors}},
 "broad_pool":broad,"deep_pool":deep,"low_candidates":low_candidates,"legacy_tracking":legacy,"dragon_tiger_events":events,
 "dragon_candidates":dragon_candidates,"historical_followup":follow,"official_raw":{"sse_main":sse_main,"sse_star":sse_star,"szse_pages":sz_pages,"szse_details":sz_details}}
dump("docs/research/low-dragon-20261126-evidence.json.gz",evidence,True)
samples={"schema_version":"2026-11-26.v1","market_date":T,"low_position_samples":low_candidates,"low_position_legacy_tracking":legacy,"dragon_tiger_events":events,"historical_followup":follow}
dump("docs/research/low-dragon-20261126-samples.json.gz",samples,True)

def report(id,date,track,typ,status,title,summary,body,eligible):
 return {"id":id,"date":date,"track":track,"task_id":track,"report_type":typ,"status":status,"title":title,"summary":summary,"body":body,
 "recorded_at":STAMP,"published_at":STAMP,"source_urls":["https://hq.sinajs.cn/","https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_vp=/CN_MarketDataService.getKLineData","https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DAILYBILLBOARD_DETAILS","https://query.sse.com.cn/infodisplay/showTradePublicFile.do","https://query.sse.com.cn/marketdata/tradedata/queryKCBTradeInfo.do","https://www.szse.cn/api/report/ShowReport/data"],
 "analysis_completed":status=="completed","eligible_for_integrated_research":eligible,"evidence_files":["docs/research/low-dragon-20261126-evidence.json.gz","docs/research/low-dragon-20261126-samples.json.gz"]}
low_status="completed" if len(metrics)>=110 and len(deep)==28 and len(legacy)>=52 and len(low_candidates)>=3 else "partial"
dt_status="completed" if official_ok and events else "partial"
reports=[
 report("low-position-20261126-close-v1",T,"low_position","daily_research",low_status,"11月26日低位启动｜全样本扫描、旧30日样本全跟踪与新增冻结",f"沪深{cur_doc['coverage']['verified']}/{cur_doc['coverage']['checked']}；120广池、{len(deep)}深池、{len(legacy)}条旧样本、{len(low_candidates)}条新增。",low_body,low_status=="completed"),
 report("dragon-tiger-20261126-close-v1",T,"dragon_tiger","daily_research",dt_status,"11月26日龙虎榜｜全事件双侧席位与沪深交易所官方核验",f"沪深{len(events)}事件；SZSE 45/45明细，SSE主板/科创板同日正文。",dt_body,dt_status=="completed"),
 report("low-dragon-20261120-followup-20261126-v1","2026-11-20","dragon_tiger","validation_supplement","completed","11月20日低位与龙虎榜历史锚点截至11月26日价格验证",f"{len(follow)}/{len(anchors)}条取得日线，仅价格观察。",follow_body,False),
]
summary_status="completed" if low_status==dt_status=="completed" else "partial"
summary_body=header+f"\n\n- low_position：{low_status}，报告 `low-position-20261126-close-v1`。\n- dragon_tiger：{dt_status}，报告 `dragon-tiger-20261126-close-v1`。\n- 联合仅执行编排，不替代两份正文；eligible_for_integrated_research=false。\n"
reports.append(report("low-dragon-20261126-execution-summary-v1",T,"market_review","execution_summary",summary_status,"11月26日低位+龙虎榜联合执行摘要",f"低位{low_status}；龙虎榜{dt_status}。",summary_body,False))

runs=[]
for r in reports:
 task=r["task_id"]; rid=r["id"]
 runs.append({"id":f"{rid}-scheduled-run","run_id":f"{rid}-scheduled","task_id":task,"date":r["date"],"trigger":"scheduled","started_at":STAMP,"recorded_at":STAMP,"completed_at":STAMP,"status":r["status"],"summary":r["summary"],"report_ids":[rid]})
dump("research_backfills/linked-low-dragon-20261126-v1.json",{"research":reports,"task_runs":runs})
print(json.dumps({"low_status":low_status,"dragon_status":dt_status,"metrics":len(metrics),"deep":len(deep),"low_candidates":[(x['code'],x['name']) for x in low_candidates],"events":len(events),"dragon_candidates":[(x['code'],x['name']) for x in dragon_candidates],"official_ok":official_ok,"historical":len(follow)},ensure_ascii=False,indent=2))
