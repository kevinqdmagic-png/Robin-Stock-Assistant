"""Recompute all frozen volume-price cohorts and the partial twenty-day ladder."""
from collections import defaultdict
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from statistics import mean
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'scripts'))
from learning_loop import nth_session_after,is_session
from prepare_completion_20261023 import pct,stats
from derive_combined_20261028 import board
T='2026-10-28';TD=date.fromisoformat(T)
def load(p):return json.loads((ROOT/p).read_text())
def main():
 raw=load('tmp/combined-20261028-raw.json');ext=load('tmp/combined-20261028-extension.json')
 raw['daily_histories'].update(ext.get('daily_histories',{}))
 daily={c:r['bars'] for c,r in raw['daily_histories'].items() if r.get('ok')}
 sup=load('tmp/combined-20261028-supplement.json')
 bench={b['date']:b for b in sup['benchmarks']['sh000001']['bars']}
 cohorts=[v for v in load('backend/data/volume_price_samples.json')['items'] if v.get('id','').endswith('-cohort') and v.get('samples')]
 out={'calculated_at':datetime.now(timezone.utc).isoformat(),'vp_all_cohort_validations':[]}
 group=defaultdict(list);strata=defaultdict(list)
 for co in cohorts:
  vals=[];origin=co['date'];rule=co['rule_version']
  for s in co['samples']:
   c=s['code'];by={b['date']:b for b in daily.get(c,[])};a=by.get(origin)
   original=s.get('close') if s.get('close') is not None else s.get('trade')
   ref=float(original) if original is not None else None
   match=bool(a and ref is not None and abs(a['close']-ref)<=.011)
   hs=[]
   for h in (1,2,3,5,10,20,30):
    target=nth_session_after(date.fromisoformat(origin),h).isoformat()
    days=[];d=date.fromisoformat(origin)+timedelta(days=1)
    while d<=date.fromisoformat(target) and d<=TD:
     if is_session(d):days.append(d.isoformat())
     d+=timedelta(days=1)
    missing=[d for d in days if d not in by]
    cur=by.get(target);path=[by[d] for d in days if d in by]
    status='pending' if target>T else 'original_anchor_unverified' if not match else 'missing_daily_path' if missing or not cur else 'price_observed'
    bp=pct(bench[target]['close'],bench[origin]['close']) if origin in bench and target in bench else None
    hs.append({'h':h,'date':target,'status':status,'close_pct':pct(cur['close'],ref) if status=='price_observed' else None,'mfe_pct':pct(max(b['high'] for b in path),ref) if status=='price_observed' else None,'mae_pct':pct(min(b['low'] for b in path),ref) if status=='price_observed' else None,'shanghai_benchmark_pct':bp if status=='price_observed' else None,'excess_price_observation_pct':round(pct(cur['close'],ref)-bp,3) if status=='price_observed' and bp is not None else None,'missing_sessions':missing if target<=T else []})
   label=s.get('structure') or s.get('label') or 'unknown_original_label'
   pos=(s.get('range_position_pct') or {}).get('120')
   position='unknown' if pos is None else '0_to_30' if pos<=30 else '30_to_70' if pos<=70 else '70_to_100'
   v={'code':c,'name':s['name'],'origin_date':origin,'original_close_matches_unadjusted_bar':match,'original_close':ref,'horizons':hs,'source':raw['daily_histories'].get(c,{}).get('source'),'original_frozen_label':label,'original_frozen_position_120':pos,'board_regime':board(c,s['name']),'executed_trade':False,'executable_net_return_pct':None}
   vals.append(v);group[rule].append(v)
   strata[(rule,'frozen_label',label)].append(v);strata[(rule,'position_120',position)].append(v);strata[(rule,'board_regime',board(c,s['name']))].append(v)
  out['vp_all_cohort_validations'].append({'origin_cohort_id':co['id'],'origin_date':origin,'rule_version':rule,'sample_count':len(vals),'validations':vals})
 def grouped(rows):
  hs={}
  for h in (1,2,3,5,10,20,30):
   pairs=[(r,next(a for a in r['horizons'] if a['h']==h)) for r in rows]
   pairs=[(r,a) for r,a in pairs if a['status']=='price_observed'];values=[a for r,a in pairs]
   hs[str(h)]={**stats([a['close_pct'] for a in values]),'independent_dates':len({r['origin_date'] for r,a in pairs}),'mean_mfe_pct':round(mean(a['mfe_pct'] for a in values),3) if values else None,'mean_mae_pct':round(mean(a['mae_pct'] for a in values),3) if values else None,'mean_excess_price_pct':round(mean(a['excess_price_observation_pct'] for a in values if a['excess_price_observation_pct'] is not None),3) if any(a['excess_price_observation_pct'] is not None for a in values) else None}
  return {'cohort_dates':sorted({r['origin_date'] for r in rows}),'frozen_sample_count':len(rows),'independent_dates':len({r['origin_date'] for r in rows}),'horizons':hs,'executable_trade_count':0,'strategy_win_rate':None,'net_return_mean_pct':None,'net_return_median_pct':None,'profit_loss_ratio':None,'exit_quality':None,'cost_and_slippage':'20bp placeholder not calibrated; no fill-based net return calculated'}
 out['vp_by_rule_version']={k:grouped(v) for k,v in group.items()}
 out['descriptive_stratifications']=[{'rule_version':r,'dimension':d,'label':l,**grouped(v)} for (r,d,l),v in strata.items()]
 space=[];missing=[]
 for day,r in sorted(sup['historical_20_session_pools'].items()):
  pool=(r.get('payload',{}).get('data') or {}).get('pool') or []
  ordinary=[a for a in pool if board(a['c'],a['n'])=='ordinary_main_10pct']
  if not ordinary:missing.append(day);continue
  h=max(a['lbc'] for a in ordinary);tops=[]
  for a in ordinary:
   if a['lbc']!=h:continue
   bar=next((b for b in daily.get(a['c'],[]) if b['date']==day),None)
   tops.append({'code':a['c'],'name':a['n'],'boards':h,'pool_close':a['p']/1000,'daily_price_crosschecked':bool(bar and abs(bar['close']-a['p']/1000)<=.011)})
  space.append({'date':day,'highest_boards':h,'stocks':tops})
 out['twenty_prior_sessions_space_reference']={'requested_sessions':sorted(sup['historical_20_session_pools']),'available_pools':len(space),'missing_session_pools':missing,'coverage_complete':not missing,'visible_maximum_boards':max((r['highest_boards'] for r in space),default=None),'full_20_session_highest':max((r['highest_boards'] for r in space),default=None) if not missing else None,'daily_visible_highs':space,'emotion_cycle_start_and_high':None,'role':'historical partial context, not a confirmed space breakout'}
 p=ROOT/'tmp/combined-20261028-statistics.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False))
 print(json.dumps({'cohorts':len(cohorts),'frozen_sample_count':sum(len(c['samples']) for c in cohorts),'anchor_verified':sum(v['original_close_matches_unadjusted_bar'] for c in out['vp_all_cohort_validations'] for v in c['validations']),'versions':{k:{'n':v['frozen_sample_count'],'dates':v['independent_dates'],'T1':v['horizons']['1'],'T2':v['horizons']['2']} for k,v in out['vp_by_rule_version'].items()},'space':{k:v for k,v in out['twenty_prior_sessions_space_reference'].items() if k!='daily_visible_highs'}},ensure_ascii=False))
if __name__=='__main__':main()
