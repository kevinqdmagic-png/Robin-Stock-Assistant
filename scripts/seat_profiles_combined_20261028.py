"""Append descriptive branch evidence; branches and generic labels are not accounts."""
from collections import defaultdict
from pathlib import Path
from datetime import datetime,timezone
import gzip,json
ROOT=Path(__file__).resolve().parents[1]
prev=json.loads(gzip.decompress((ROOT/'docs/research/combined-pair-20261027-evidence.json.gz').read_bytes()))
cur=json.loads((ROOT/'tmp/combined-20261028-derived.json').read_text())
validation={r['code']:r for r in cur['dragon_previous_whole_disclosed_pool']}
profiles=defaultdict(list);generic=[]
for day,rows in [('2026-10-27',prev['derived']['dragon_selected']),('2026-10-28',cur['dragon_selected'])]:
 for s in rows:
  union={(str(r.get('OPERATEDEPT_CODE')),r.get('BUY'),r.get('SELL'),str(r.get('TRADE_ID'))):r for r in s['buy_seats_em']+s['sell_seats_em']}
  for r in union.values():
   name=str(r.get('OPERATEDEPT_NAME') or '')
   obs={'date':day,'code':s['code'],'stock_name':s['name'],'period':s['period'],'trade_id':s['selected_trade_id'],'branch_code':str(r.get('OPERATEDEPT_CODE')),'branch_name':name,'buy_cny':r.get('BUY'),'sell_cny':r.get('SELL'),'net_cny':float(r.get('BUY') or 0)-float(r.get('SELL') or 0),'next_session_close_price_pct':validation.get(s['code'],{}).get('close_pct') if day=='2026-10-27' else None,'actual_holding_period':None,'verified_account_identity':False,'executed_trade_evidence':False}
   if name=='机构专用' or '股通' in name:generic.append(obs)
   else:profiles[(obs['branch_code'],name)].append(obs)
out={'calculated_at':datetime.now(timezone.utc).isoformat(),'source_sessions':['2026-10-27','2026-10-28'],'profiles':[{'branch_code':c,'branch_name':n,'observed_stock_period_rows':len(rs),'distinct_disclosure_dates':len({r['date'] for r in rs}),'observations':rs,'preference_and_holding_period_conclusion':'insufficient independent observations; turnover, lock-up, actual holding period and trader identity unverified','interpretation':'Named public broker branch, not a confirmed person or algorithm account; multi-day disclosures kept separate.'} for (c,n),rs in profiles.items()],'generic_channel_rows_not_merged_as_accounts':generic,'no_strategy_returns_or_win_rate':True}
(ROOT/'tmp/combined-20261028-seat-profiles.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'branch_profiles':len(profiles),'branch_observation_rows':sum(len(v) for v in profiles.values()),'generic_channel_rows':len(generic),'multi_date_branches':sum(len({r['date'] for r in rs})>1 for rs in profiles.values())}))
