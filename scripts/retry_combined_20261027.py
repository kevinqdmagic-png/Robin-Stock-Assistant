"""Retry only failed evidence requests, retaining the initial failure archive."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
from collect_combined_20261027 import ROOT, daily, minute, seat, stamp
raw=json.loads((ROOT/'tmp/combined-20261027-raw.json').read_text())
checks=json.loads((ROOT/'tmp/combined-20261027-retry-checks.json').read_text())
ext={'started_at':stamp(),'policy':'One bounded retry, four workers; initial failed responses remain unchanged.','daily_histories':{'688836':checks['daily688836']},'minute_price_points':{'002724':checks['minute002724']},'seat_queries':{'000678:BUY':checks['seat000678BUY']},'limit_up_pools':{'2026-10-27':checks['poolT27']}}
for kind,fn in [('daily_histories',daily),('seat_queries',seat),('minute_price_points',minute)]:
 keys=[c for c,r in raw[kind].items() if not r.get('ok') and c not in ext[kind]]
 def one(c):return c,fn(c)
 with ThreadPoolExecutor(max_workers=4) as ex:ext[kind].update(dict(ex.map(one,keys)))
 (ROOT/'tmp/combined-20261027-extension.json').write_text(json.dumps(ext,ensure_ascii=False,indent=2))
 print(json.dumps({'kind':kind,'retried':len(keys),'ok':sum(r['ok'] for r in ext[kind].values()),'errors':{c:r.get('error') for c,r in ext[kind].items() if not r['ok']}}),flush=True)
ext['completed_at']=stamp()
(ROOT/'tmp/combined-20261027-extension.json').write_text(json.dumps(ext,ensure_ascii=False,indent=2))
