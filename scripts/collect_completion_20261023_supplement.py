#!/usr/bin/env python3
"""Supplement the dated close evidence, keeping publication and market clocks separate."""
import concurrent.futures as cf
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT.parent / 'task_audit_20261023'
T = '2026-10-23'

def load(p):
    return json.loads(p.read_text())

def get(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=22) as r:
        return json.loads(r.read().decode('utf-8'))

def sym(c):
    return ('sh' if c.startswith(('6','5')) else 'bj' if c.startswith(('4','8','9')) else 'sz') + c

def daily(c):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={sym(c)},day,,,180'
    data = get(url)['data'][sym(c)]
    rows = [{'date': a[0], **{k:float(v) for k,v in zip(('open','close','high','low','volume'),a[1:6])}}
            for a in data.get('day',[]) if a[0] <= T]
    if not rows or rows[-1]['date'] != T:
        raise ValueError('missing target unadjusted close')
    return {'source':url, 'adjustment':'unadjusted', 'volume_unit':'provider_lots', 'bars':rows}

def seat(key):
    code,side = key
    p = dict(reportName='RPT_BILLBOARD_DAILYDETAILS'+side,columns='ALL',
             filter=f'''(TRADE_DATE='{T}')(SECURITY_CODE="{code}")''',
             pageNumber=1,pageSize=500,sortTypes='-1',sortColumns=side,source='WEB',client='WEB')
    url = 'https://datacenter-web.eastmoney.com/api/data/v1/get?'+urlencode(p)
    data = get(url)
    rows = (data.get('result') or {}).get('data') or []
    if not rows: raise ValueError(str(data.get('message')))
    assert all(r['TRADE_DATE'].startswith(T) and r['SECURITY_CODE']==code for r in rows)
    return {'code':code,'side':side,'source':url,'rows':rows}

def minute(c):
    url = f'https://web.ifzq.gtimg.cn/appstock/app/day/query?code={sym(c)}'
    data = get(url)['data'][sym(c)]['data']
    groups = []
    for g in data:
        if str(g.get('date','')) > T.replace('-',''): continue
        points = []
        for line in g.get('data',[]):
            a = str(line).split()
            if len(a)>=3 and '0930'<=a[0]<='1500':
                points.append({'clock':a[0],'price':float(a[1]),'cumulative_volume_provider_units':float(a[2]),
                               'cumulative_amount_cny':float(a[3]) if len(a)>3 else None})
        groups.append({'date':g.get('date'),'points':points})
    if not any(g['date']==T.replace('-','') and g['points'] for g in groups):
        raise ValueError('no target minute price points')
    return {'source':url,'type':'minute_price_points_not_OHLC_or_fills','groups':groups}

def collect(keys, fun):
    good,bad={},{}
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        fs={pool.submit(fun,k):k for k in keys}
        for f in cf.as_completed(fs):
            k=fs[f]
            try:good[k]=f.result()
            except Exception as e:bad[str(k)]=f'{type(e).__name__}: {e}'
    return good,bad

def main():
    start=datetime.now(timezone.utc).isoformat()
    raw=load(AUDIT/'completion_raw.json')
    scan=load(ROOT/'docs/research/low-dragon-2026-10-23-market-scan.json')
    prev=load(ROOT/'docs/research/completion-2026-10-22-evidence.json')['dragon_tiger']
    codes={r['code'] for r in scan['broad_pool']+prev['institution_rows']+prev['stock_connect_rows']} | {'002241'}
    extra,errors=collect(sorted(codes-set(raw['daily'])),daily)
    raw['daily'].update(extra)
    (AUDIT/'completion_raw.json').write_text(json.dumps(raw,ensure_ascii=False))
    chosen=['002354','002747','603466','688368','002343','002724','603278','002241']
    seats,seaterr=collect([(c,s) for c in chosen for s in ('BUY','SELL')],seat)
    mins,minerr=collect(sorted({r['code'] for r in scan['deep_pool']}|set(chosen)|{'600592'}),minute)
    thsurl=f'https://data.10jqka.com.cn/market/longhu/date/{T}/'
    try:
        with urlopen(Request(thsurl,headers={'User-Agent':'Mozilla/5.0'}),timeout=22) as r:
            body=r.read();ths={'source':thsurl,'status':r.status,'bytes':len(body),'verified_dated_table':False,
                              'note':'HTTP reachability is not a verified dated seat crosscheck'}
    except Exception as e:ths={'source':thsurl,'error':str(e),'verified_dated_table':False}
    out={'market_date':T,'started_at_utc':start,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
         'additional_daily_count':len(extra),'daily_errors':errors,'seat_queries':list(seats.values()),
         'seat_errors':seaterr,'minute_price_points':mins,'minute_errors':minerr,'ths_crosscheck':ths}
    (AUDIT/'completion_supplement.json').write_text(json.dumps(out,ensure_ascii=False))
    print(json.dumps({k:v for k,v in out.items() if k not in ('seat_queries','minute_price_points')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
