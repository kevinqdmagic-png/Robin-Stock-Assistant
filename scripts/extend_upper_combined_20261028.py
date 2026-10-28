"""Verify normal-main price limits for all threshold-touch candidates."""
from pathlib import Path
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
import json,re
from collect_combined_20261028 import ROOT,stamp,symbol,T
path=ROOT/'tmp/combined-20261028-quote-upper-check.json';out=json.loads(path.read_text());raw=json.loads((ROOT/'tmp/combined-20261028-raw.json').read_text())
needed=set(['600838','603028','603528','603089','002535','002708','001219','001331','002820'])
for q in raw['quotes'].values():
 if not q['code'].startswith(('00','60')) or 'ST' in q['name'].upper() or '退' in q['name']:continue
 ref=float(q.get('settlement') or 0);hi=float(q.get('high') or 0);lo=float(q.get('low') or 0)
 if ref>0 and (hi/ref>=1.095 or (lo>0 and lo/ref<=.905)):needed.add(q['code'])
missing=sorted(c for c in needed if symbol(c) not in out['provider_fields']);batches=[missing[i:i+40] for i in range(0,len(missing),40)]
def fetch(cs):
 u='https://qt.gtimg.cn/q='+','.join(symbol(c) for c in cs)
 try:
  b=urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15).read();s=b.decode('gb18030',errors='replace');fs={k:v.split('~') for k,v in re.findall(r'v_([a-zA-Z0-9]+)="([^"]*)";',s)}
  return {'ok':True,'source':u,'retrieved_at':stamp(),'provider_fields':fs,'raw_text':s}
 except Exception as e:return {'ok':False,'source':u,'retrieved_at':stamp(),'error':str(e)}
with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(fetch,batches))
out['additional_touch_and_negative_batches']=results
for r in results:out['provider_fields'].update({k:v for k,v in r.get('provider_fields',{}).items() if len(v)>48})
out['requested_codes']=sorted(set(out['requested_codes'])|set(missing));path.write_text(json.dumps(out,ensure_ascii=False,indent=2))
rows=[];unverified=[]
for c in sorted(needed):
 q=raw['quotes'].get(c);fs=out['provider_fields'].get(symbol(c))
 if not q or not fs or not fs[30].startswith('20261028'):
  unverified.append(c);continue
 up=float(fs[47] or 0);dn=float(fs[48] or 0);ref=float(fs[4] or 0)
 if up<=0 or ref<=0 or not 9.0<=(up/ref-1)*100<=11.0:
  unverified.append(c);continue
 close=float(q['trade']);hi=float(q['high']);lo=float(q['low']);assert abs(close-float(fs[3]))<=.001,(c,close,fs[3])
 touched=abs(hi-up)<=.001;sealed=abs(close-up)<=.001;down=abs(close-dn)<=.001
 rows.append({'code':c,'name':q['name'],'close':close,'high':hi,'low':lo,'verified_provider_upper':up,'verified_provider_lower':dn,'touched_upper':touched,'closed_at_upper':sealed,'touched_not_sealed':touched and not sealed,'closed_at_lower':down,'provider_timestamp':fs[30]})
metrics={'market_date':T,'retrieved_at':stamp(),'scope':'Sina full-A normal-main threshold-entry candidates verified against dated Tencent reported upper/lower prices; not full point-in-time security master',
 'candidate_count':len(needed),'price_limit_verified_n':len(rows),'unverified_codes':unverified,'closed_at_upper_n':sum(r['closed_at_upper'] for r in rows),'touched_upper_n':sum(r['touched_upper'] for r in rows),'touched_not_sealed_n':sum(r['touched_not_sealed'] for r in rows),'closed_at_lower_n':sum(r['closed_at_lower'] for r in rows),'rows':rows,'no_order_fill_inference':True}
(ROOT/'tmp/combined-20261028-exact-main-limit-check.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in metrics.items() if k!='rows'},ensure_ascii=False))
