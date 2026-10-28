"""Verify preserved history, real-source calculations and shadow/formal isolation."""
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
import gzip, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from entry_alerts import scheduled_recommendations
BASE='526005c62039093a5fc4f214db9f5fe1539297f2'
T='2026-10-28';D='2026-10-29'
def load(p):return json.loads((ROOT/p).read_text())
def old(p):return json.loads(subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT))
def main():
 now=datetime.now(timezone.utc);m=load('docs/research/combined-pair-20261028-publication-manifest.json')
 e=json.loads(gzip.decompress((ROOT/m['evidence_file']).read_bytes()));x=load(m['shadow_experiment_file'])
 assert hashlib.sha256((ROOT/m['evidence_file']).read_bytes()).hexdigest()==m['evidence_sha256']
 assert hashlib.sha256((ROOT/m['shadow_experiment_file']).read_bytes()).hexdigest()==m['shadow_experiment_sha256']
 assert e['research_shadow_experiments']==x
 reports=load('backend/data/research.json')['items'];runs=load('backend/data/task_runs.json')['items']
 assert reports[:len(old('backend/data/research.json')['items'])]==old('backend/data/research.json')['items']
 assert runs[:len(old('backend/data/task_runs.json')['items'])]==old('backend/data/task_runs.json')['items']
 for task in ['market_review','volume_price','low_position','dragon_tiger','combined_pair','limitup_single']:
  rr=[r for r in reports if r.get('task_id')==task and r['date']==T and r.get('report_type') in ['full_daily_research','full_trading_research']]
  assert len(rr)==1,task
  r=rr[0];assert r.get('eligible_for_integrated_research') is (task!='limitup_single')
  aa=[a for a in runs if a.get('status')=='completed' and a.get('report_ids')==[r['id']]]
  assert len(aa)==1
  a=aa[0];assert a['trigger']=='scheduled'
  assert datetime.fromisoformat(a['started_at'])<=datetime.fromisoformat(a['completed_at'])<=datetime.fromisoformat(a['recorded_at'])<=now
  if task=='market_review':continue
  assert r['id'] in m['new_report_ids'] and r['planned_entry_date']==D and r['earliest_legal_exit_date_if_bought']=='2026-10-30'
  assert r['candidate_count']==0 and r['recommendation_ids']==[] and '\ufffd' not in r['body']
  assert datetime.fromisoformat(r['published_at'])<=now
 assert len(m['new_report_ids'])==5
 assert load('backend/data/tasks.json')==old('backend/data/tasks.json')
 lows=load('backend/data/low_position_samples.json')['items'];olds=old('backend/data/low_position_samples.json')['items']
 assert len(olds)==44 and len(lows)==47
 for before in olds:
  after=next(s for s in lows if s['id']==before['id'])
  assert {k:v for k,v in before.items() if k!='observations'}=={k:after[k] for k in before if k!='observations'}
  assert after['observations'][:-1]==before.get('observations',[]) and after['observations'][-1]['date']==T
 assert {s['code'] for s in lows[44:]}=={'000554','603109','603926'}
 assert all(s['is_recommendation'] is False and s['default_watch'] is False for s in lows[44:])
 vp=load('backend/data/volume_price_samples.json')['items'];ov=old('backend/data/volume_price_samples.json')['items']
 assert vp[:len(ov)]==ov and len(vp[-1]['samples'])==28
 recs=load('backend/data/recommendations.json')['items'];orecs=old('backend/data/recommendations.json')['items']
 assert len(recs)==len(orecs)==31
 for a,b in zip(orecs,recs):
  assert {k:v for k,v in a.items() if k!='results'}=={k:b[k] for k in a if k!='results'}
  assert b['results'][:-1]==a.get('results',[]) and b['results'][-1]['date']==T
  assert b['results'][-1]['executed_trade'] is False and b['results'][-1]['executable_net_return_pct'] is None
 assert scheduled_recommendations(recs,D)==[]
 signals=x['signals'];assert len(signals)==3
 assert [(s['parent_task_id'],s['code']) for s in signals]==[('combined_pair','603699'),('combined_pair','603926'),('limitup_single','000554')]
 assert scheduled_recommendations(signals,D)==[]
 assert len({s['market_event_id'] for s in signals})==3
 assert len(x['formal_cash_observations'])==2 and {h['id'] for h in x['hypotheses']}=={'H1','H2','H3'}
 for s in signals:
  assert s['role']=='research_shadow' and s['formal_buy_signal'] is False and s['send_trade_notification'] is False and s['is_recommendation'] is False
  assert s['T']==T and s['planned_entry_date']==D and s['daily_limit_pct']==10
  f=datetime.fromisoformat(s['signal_frozen_at']);assert f<datetime.fromisoformat(D+'T09:30:00+08:00') and f<=now
  assert s['entry_triggered'] is None and s['entry_fill_verified'] is None and s['executable_net_return_pct'] is None and s['results']==[]
  assert s['D_actual_upper_price'] is None and s['reference_is_fill'] is False
  assert s['earliest_legal_exit_if_bought_at']=='2026-10-30T09:30:00+08:00'
  for a in s['evidence_available_at']:assert datetime.fromisoformat(a['retrieved_at'])<=f
  raw=e['daily_histories'][s['code']];bar=next(b for b in raw['bars'] if b['date']==T)
  assert bar['close']==s['reference_price']
  for rid in s['report_ids']:
   report=next(r for r in reports if r['id']==rid);assert s in report['research_shadow_candidates']
 assert signals[0]['reference_price']==38.39 and signals[0]['observed_T_upper_price']==38.4
 assert x['benchmark']['primary']=='sh000300' and x['review']['automatic_model_updates'] is False
 assert all(s['results']==[] for s in x['controls'])
 de=e['derived'];rows=de['previous_whole_pool'];assert len(rows)==28
 assert round(mean(r['close_pct'] for r in rows),3)==0.982 and round(median(r['close_pct'] for r in rows),3)==1.808
 assert sum(r['mae_pct']<=-5 for r in rows)==13
 assert de['crosscheck']['recomputed_broad']==120 and not de['crosscheck']['ohlc_mismatches']
 assert de['low_summary']['count']==44 and de['low_summary']['all_paths_complete'] and de['low_summary']['eligible_mature_calendar_30']==0
 assert len(de['dragon_previous_whole_disclosed_pool'])==77
 assert sum(r['status']=='price_observed' for r in de['dragon_previous_whole_disclosed_pool'])==76
 missing=next(r for r in de['dragon_previous_whole_disclosed_pool'] if r['code']=='301139')
 assert missing['status']=='delisted_no_exchange_trading_bar' and missing['price_observation_return_pct'] is None and '1225629444.PDF' in missing['source']
 assert len(de['dragon_selected'])==8 and all(s['seat_reconciliation']['matched'] and s['ths_close_match'] for s in de['dragon_selected'])
 assert len(e['new_dragon_observations'])==5
 assert de['progression_main_10pct']['1_to_2']['prior_full_denominator']==26 and de['progression_main_10pct']['1_to_2']['advanced']==5
 assert de['progression_main_10pct']['2_to_3']['prior_full_denominator']==8 and de['progression_main_10pct']['2_to_3']['advanced']==2
 assert de['limit_pool_reconciliation']['original_provider_count']==72 and de['limit_pool_reconciliation']['original_pool_preserved']
 assert de['limit_pool_reconciliation']['added_records'][0]['c']=='605488' and de['limit_pool_reconciliation']['added_records'][0]['verified_upper']==48.61
 exact=e['exact_main_price_limit_verification'];assert (exact['price_limit_verified_n'],exact['closed_at_upper_n'],exact['touched_not_sealed_n'],exact['closed_at_lower_n'])==(160,59,49,7)
 space=e['cumulative']['twenty_prior_sessions_space_reference'];assert space['available_pools']==16 and space['full_20_session_highest'] is None
 v4=e['cumulative']['vp_by_rule_version']['volume_price_close_v4'];assert v4['frozen_sample_count']==196 and v4['independent_dates']==7
 cat=load('backend/data/research_stocks.json');assert cat==load('app/src/main/assets/research_stocks.json')
 for c in old('backend/data/research_stocks.json')['items']:
  a=next(v for v in cat['items'] if v['code']==c['code']);assert a['history'][:len(c['history'])]==c['history']
 assert len(m['stock_history_updates'])==19
 print('T28 full research, source-date/limit/denominator corrections, immutable history, cash events and 2+1 pre-open shadow isolation verified.')
if __name__=='__main__':main()
