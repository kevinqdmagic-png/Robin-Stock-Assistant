"""Exact dated limit fields for the threshold/pool entry scope, not all securities."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from derive_combined_20261030 import board
def main():
 raw=json.loads((ROOT/'tmp/combined-20261030-raw.json').read_text());quotes=raw['quotes']
 checks=json.loads((ROOT/'tmp/combined-20261030-quote-upper-check.json').read_text());fs=checks['provider_fields']
 codes=set()
 for c,q in quotes.items():
  if board(c,q['name'])!='ordinary_main_10pct':continue
  ref=float(q.get('settlement') or 0)
  if ref and (float(q.get('high') or 0)/ref>=1.095 or 0<float(q.get('low') or 0)/ref<=.905):codes.add(c)
 for r in raw['limit_up_pools']['2026-10-30']['payload']['data']['pool']:
  if board(r['c'],r['n'])=='ordinary_main_10pct':codes.add(r['c'])
 rows=[];missing=[]
 for c in sorted(codes):
  f=fs.get(('sh' if c.startswith('6') else 'sz')+c)
  if not f or not f[30].startswith('20261030') or not f[47] or not f[48]:missing.append(c);continue
  close,high,low,upper,lower=map(float,[f[3],f[33],f[34],f[47],f[48]])
  assert abs(close-float(quotes[c]['trade']))<.011,(c,'cross-provider price mismatch')
  rows.append({'code':c,'name':f[1],'close':close,'high':high,'low':low,'upper':upper,'lower':lower,'provider_timestamp':f[30],
   'closed_at_upper':abs(close-upper)<.001,'touched_upper':abs(high-upper)<.001,'touched_not_sealed':abs(high-upper)<.001 and close<upper-.001,
   'closed_at_lower':abs(close-lower)<.001,'opening_one_price':abs(float(f[5])-upper)<.001 and abs(low-upper)<.001})
 out={'market_date':'2026-10-30','candidate_count':len(codes),'price_limit_verified_n':len(rows),'unverified_codes':missing,
  'closed_at_upper_n':sum(r['closed_at_upper'] for r in rows),'touched_upper_n':sum(r['touched_upper'] for r in rows),
  'touched_not_sealed_n':sum(r['touched_not_sealed'] for r in rows),'closed_at_lower_n':sum(r['closed_at_lower'] for r in rows),
  'source_evidence':'tmp/combined-20261030-quote-upper-check.json','scope':'ordinary main non-ST threshold/pool entry codes only, not a complete point-in-time security master','rows':rows}
 (ROOT/'tmp/combined-20261030-exact-main-limit-check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in out.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
