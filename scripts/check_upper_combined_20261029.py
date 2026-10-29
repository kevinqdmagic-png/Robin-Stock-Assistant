"""Cross-check provider limit-price fields; a threshold proxy is not a seal."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from pathlib import Path
import json,re
from collect_combined_20261029 import ROOT,T,stamp,symbol
r=json.loads((ROOT/'tmp/combined-20261029-raw.json').read_text());m=json.loads((ROOT/'docs/research/market-review-2026-10-29-evidence.json').read_text())
codes={q['code'] for q in m['broad_pool']}
codes.update(q['code'] for q in r['quotes'].values() if q['code'].startswith(('00','60')) and 'ST' not in q['name'].upper() and '退' not in q['name'] and float(q.get('changepercent') or 0)>=9.7)
codes.update(q['c'] for q in r['limit_up_pools'][T]['payload']['data']['pool'])
codes.update(['603699','603926','000554','300539','603037','601956','603337','603633','600118','300900','002275'])
seq=sorted(codes);batches=[seq[i:i+40] for i in range(0,len(seq),40)]
def fetch(cs):
 u='https://qt.gtimg.cn/q='+','.join(symbol(c) for c in cs)
 try:
  b=urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15).read();s=b.decode('gb18030',errors='replace');fields={v[0]:v[1].split('~') for v in re.findall(r'v_([a-zA-Z0-9]+)="([^"]*)";',s)}
  return {'ok':True,'source':u,'retrieved_at':stamp(),'provider_fields':fields,'raw_text':s}
 except Exception as e:return {'ok':False,'source':u,'retrieved_at':stamp(),'error':repr(e)}
with ThreadPoolExecutor(max_workers=2) as p:out=list(p.map(fetch,batches))
fields={k:v for r in out for k,v in r.get('provider_fields',{}).items() if len(v)>48}
report={'market_date':T,'source':'https://qt.gtimg.cn/q=dated_provider_batches','requested_codes':seq,'batches':out,'provider_fields':fields,'upper_field':47,'lower_field':48,'timestamp_field':30,'interpretation':'provider reported limit fields, not an exchange order book or fill proof'}
(ROOT/'tmp/combined-20261029-quote-upper-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'requested':len(seq),'returned':len(fields),'batch_failures':[r.get('error') for r in out if not r['ok']],'selected':{c:{'name':fields.get(symbol(c),['',''])[1],'close':fields.get(symbol(c),['']*49)[3],'upper':fields.get(symbol(c),['']*49)[47],'lower':fields.get(symbol(c),['']*49)[48],'provider_timestamp':fields.get(symbol(c),['']*49)[30]} for c in ['603699','000554','603926','603633','000678','600838','603028','603528']}},ensure_ascii=False))
