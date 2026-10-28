"""One bounded retry of missing inputs; keep all original failed attempts."""
from concurrent.futures import ThreadPoolExecutor
import json
from collect_combined_20261028 import ROOT,daily,seat,minute,stamp
raw=json.loads((ROOT/'tmp/combined-20261028-raw.json').read_text())
out={'started_at':stamp(),'policy':'one bounded retry; original archive retained'}
for kind,fn in [('daily_histories',daily),('seat_queries',seat),('minute_price_points',minute)]:
 keys=[c for c,r in raw[kind].items() if not r.get('ok')]
 with ThreadPoolExecutor(max_workers=2) as p:out[kind]=dict(p.map(lambda c:(c,fn(c)),keys))
out['limit_up_pools']={};out['completed_at']=stamp()
(ROOT/'tmp/combined-20261028-extension.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:{'retried':len(out[k]),'still_missing':[c for c,r in out[k].items() if not r.get('ok')]} for k in ['daily_histories','seat_queries','minute_price_points']}))
