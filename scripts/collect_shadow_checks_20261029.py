"""Small dated audit of every D29 shadow and frozen control before new signals."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
import json,re
from collect_combined_20261029 import ROOT,T,stamp,daily,minute,symbol
codes=['603699','603926','000554','603037','601956','603337','603633','300539']
with ThreadPoolExecutor(max_workers=4) as p:ds=dict(zip(codes,p.map(daily,codes)))
with ThreadPoolExecutor(max_workers=4) as p:ms=dict(zip(codes,p.map(minute,codes)))
u='https://qt.gtimg.cn/q='+','.join(symbol(c) for c in codes)
try:
 with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as f:b=f.read()
 s=b.decode('gb18030',errors='replace');fs={k:v.split('~') for k,v in re.findall(r'v_([a-zA-Z0-9]+)="([^"]*)";',s)};q={'ok':True,'source':u,'retrieved_at':stamp(),'provider_fields':fs,'raw_text':s}
except Exception as e:q={'ok':False,'source':u,'retrieved_at':stamp(),'error':repr(e),'provider_fields':{}}
out={'market_date':T,'retrieved_at':stamp(),'daily_histories':ds,'minute_price_points':ms,'quoted_upper':q}
(ROOT/'tmp/shadow-inputs-20261029.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'daily':{c:r['ok'] for c,r in ds.items()},'minute':{c:r['ok'] for c,r in ms.items()},'quote_ok':q['ok']},ensure_ascii=False))
