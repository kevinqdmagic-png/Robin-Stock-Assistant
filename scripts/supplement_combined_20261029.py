"""Supplement dated market evidence; never interpret price points as fills."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from learning_loop import is_session
from collect_combined_20261029 import get, stamp, ROOT, T

def main():
    d=date.fromisoformat(T)-timedelta(days=1); days=[]
    while len(days)<20:
        if is_session(d):days.append(d.isoformat())
        d-=timedelta(days=1)
    def pool(day):
        r=get('https://push2ex.eastmoney.com/getTopicZTPool',{'ut':'7eea3edcaed734bea9cbfc24409ed989','dpt':'wz.ztzt','Pageindex':0,'pagesize':1000,'sort':'fbt:asc','date':day.replace('-',''),'_':''})
        return day,r
    with ThreadPoolExecutor(max_workers=4) as ex:pools=dict(ex.map(pool,days))
    benchmarks={}
    for symbol in ('sh000001','sz399001','sz399006','sh000688','sh000300'):
        r=get('https://web.ifzq.gtimg.cn/appstock/app/kline/kline',{'param':symbol+',day,,,180'})
        block=r.get('payload',{}).get('data',{}).get(symbol,{})
        rows=block.get('day',[])
        r['bars']=[{'date':b[0],'open':float(b[1]),'close':float(b[2]),'high':float(b[3]),'low':float(b[4]),'volume':float(b[5])} for b in rows if b[0]<=T]
        benchmarks[symbol]=r
    out={'calculated_at':stamp(),'historical_20_session_pools':pools,'benchmarks':benchmarks}
    p=ROOT/'tmp/combined-20261029-supplement.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({'historical_pools_available':sum(bool((r.get('payload',{}).get('data') or {}).get('pool')) for r in pools.values()),'requested_days':days,'benchmarks_last':{s:r['bars'][-1]['date'] if r['bars'] else None for s,r in benchmarks.items()}},ensure_ascii=False),flush=True)
    try:
        import pandas as pd
        from urllib.request import Request,urlopen
        url='https://data.10jqka.com.cn/market/longhu/date/'+T+'/'
        data=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25).read()
        dfs=pd.read_html(BytesIO(data),converters={1:str})
        tables=[[[None if pd.isna(v) else v.item() if hasattr(v,'item') else v for v in row] for row in df.itertuples(index=False,name=None)] for df in dfs]
        ths={'source':url,'retrieved_at':stamp(),'ok':True,'table_count':len(tables),'tables':tables}
    except Exception as e:ths={'ok':False,'error':repr(e),'retrieved_at':stamp()}
    (ROOT/'tmp/combined-20261029-ths.json').write_text(json.dumps(ths,ensure_ascii=False,indent=2))
    print(json.dumps({'ths_ok':ths['ok'],'table_count':ths.get('table_count'),'summary_count':len(ths.get('tables',[[],[],[],[],[],[]])[5])},ensure_ascii=False))
if __name__=='__main__':main()
