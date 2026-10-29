"""Audit original evidence, append-only histories, clocks, gates and dual tracks."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
BASE='4ad25a629dccea20b39cbd8230fefab7f3f973ce'
def load(p):return json.loads((ROOT/p).read_text())
def old(p):return json.loads(subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT,text=True))
def unchanged_prefix(path,key,append_key):
    a=old(path);b=load(path);lookup={x[key]:x for x in b['items']}
    for x in a['items']:
        y=lookup[x[key]]
        assert {k:v for k,v in x.items() if k!=append_key}=={k:v for k,v in y.items() if k!=append_key},(path,x[key])
        assert y.get(append_key,[])[:len(x.get(append_key,[]))]==x.get(append_key,[])
        assert len(y.get(append_key,[]))==len(x.get(append_key,[]))+1,(path,x[key],'one new observation')
    return len(a['items'])
def main():
    manifest=load('docs/research/combined-pair-20261029-publication-manifest.json')
    evidence=(ROOT/manifest['evidence_file']).read_bytes();ev=json.loads(gzip.decompress(evidence))
    assert hashlib.sha256(evidence).hexdigest()==manifest['evidence_sha256']
    now=datetime.now(timezone.utc)
    frozen=datetime.fromisoformat(manifest['analysis_completed_at']);assert frozen<=now and frozen<datetime.fromisoformat('2026-10-30T09:30:00+08:00')
    assert datetime.fromisoformat(ev['prior_shadow_validation']['recorded_at'])<frozen
    for f in ev['official_files'].values():
        if f.get('ok'):assert datetime.fromisoformat(f['retrieved_at'])<=frozen
    assert ev['derived']['crosscheck']['recomputed_broad']==120 and len(ev['derived']['deep_recomputed'])==28
    assert not ev['derived']['crosscheck']['ohlc_mismatches']
    assert ev['derived']['low_summary']['count']==47 and ev['derived']['low_summary']['all_paths_complete']
    assert len(ev['derived']['dragon_selected'])==13
    assert all(r['seat_reconciliation']['matched'] and r['ths_close_match'] for r in ev['derived']['dragon_selected'])
    assert ev['exact_main_price_limit_verification']['price_limit_verified_n']==136
    assert ev['exact_main_price_limit_verification']['closed_at_upper_n']==38
    assert ev['exact_main_price_limit_verification']['closed_at_lower_n']==50
    assert ev['derived']['progression_main_10pct']['1_to_2']['prior_full_denominator']==51
    assert ev['derived']['progression_main_10pct']['1_to_2']['advanced']==6
    assert ev['derived']['progression_main_10pct']['5_to_6']['advanced']==0
    research=load('backend/data/research.json')['items'];runs=load('backend/data/task_runs.json')['items']
    original_reports=old('backend/data/research.json')['items'];lookup={r['id']:r for r in research}
    assert all(lookup[r['id']]==r for r in original_reports),'old report changed'
    original_runs=old('backend/data/task_runs.json')['items'];run_lookup={r['id']:r for r in runs}
    assert all(run_lookup[r['id']]==r for r in original_runs),'old receipt changed'
    for task in ['market_review','volume_price','low_position','dragon_tiger','combined_pair','limitup_single']:
        rs=[r for r in research if r.get('task_id')==task and r['date']=='2026-10-29' and r.get('report_type') in ['full_daily_research','full_trading_research']]
        assert len(rs)==1,(task,len(rs));r=rs[0]
        completed=[x for x in runs if x.get('status')=='completed' and x.get('report_ids')==[r['id']]];assert len(completed)==1
        assert datetime.fromisoformat(completed[0]['started_at'])<=datetime.fromisoformat(completed[0]['completed_at'])<=now
    unchanged_prefix('backend/data/recommendations.json','id','results')
    assert len(load('backend/data/recommendations.json')['items'])==31
    unchanged_prefix('backend/data/low_position_samples.json','id','observations')
    assert len(load('backend/data/low_position_samples.json')['items'])==50
    old_vp=old('backend/data/volume_price_samples.json')['items'];new_vp=load('backend/data/volume_price_samples.json')['items']
    assert new_vp[:len(old_vp)]==old_vp
    old_exp=old('docs/research/shadow-experiments-20261029-v1.json');new_exp=load('docs/research/shadow-experiments-20261029-v1.json')
    for key in ['signals','controls','formal_cash_observations']:
        for a,b in zip(old_exp[key],new_exp[key]):
            assert {k:v for k,v in a.items() if k!='results'}=={k:v for k,v in b.items() if k!='results'},(key,a.get('code'))
            assert b['results'][:len(a['results'])]==a['results'] and len(b['results'])==len(a['results'])+1
    for k,v in old_exp.items():
        if k not in ['signals','controls','formal_cash_observations','results']:assert new_exp[k]==v,k
    validation=load('docs/research/shadow-validation-20261029-v1.json')
    assert validation['summary']['necessary_conditions_disproved_n']==3 and validation['summary']['verified_fill_n']==0
    assert all(r['entry_triggered'] is False and r['executable_net_return_pct'] is None for r in validation['signals'])
    exp=load('docs/research/shadow-experiments-20261030-v1.json')
    assert [s['code'] for s in exp['signals']]==['600118','603279','002275']
    assert len({s['market_event_id'] for s in exp['signals']})==3
    assert exp['T']=='2026-10-29' and exp['planned_D']=='2026-10-30'
    for s in exp['signals']:
        assert s['is_recommendation'] is False and s['formal_buy_signal'] is False and s['send_trade_notification'] is False
        assert s['signal_frozen_at']==manifest['analysis_completed_at'] and s['entry_fill_verified'] is None
        assert s['earliest_legal_exit_if_bought_at']=='2026-11-02T09:30:00+08:00'
        assert s['signal_T_horizon_dates']['1']=='2026-10-30' and s['signal_T_horizon_dates']['2']=='2026-11-02'
        assert all(datetime.fromisoformat(e['retrieved_at'])<=frozen for e in s['evidence_available_at'])
    assert [h['id'] for h in exp['hypotheses']]==['H1','H2','H3']
    assert len(exp['formal_cash_observations'])==2
    for r in exp['formal_cash_observations']:assert len(r['comparison_pool_codes'])==28 and r['formal_candidate_count']==0
    assert exp['hypotheses'][0]['treatment_codes']==[],'partial H1 signals must not become full treatment retroactively'
    assert (ROOT/'backend/data/tasks.json').read_bytes()==subprocess.check_output(['git','show',BASE+':backend/data/tasks.json'],cwd=ROOT)
    assert (ROOT/'backend/data/research_stocks.json').read_bytes()==(ROOT/'app/src/main/assets/research_stocks.json').read_bytes()
    catalog=load('backend/data/research_stocks.json')['items'];old_catalog=old('backend/data/research_stocks.json')['items'];catalog_by={s['code']:s for s in catalog}
    for s in old_catalog:assert catalog_by[s['code']]['history'][:len(s['history'])]==s['history']
    assert all(s['default_watch'] is False for s in catalog if s['code'] not in {a['code'] for a in old_catalog})
    print(json.dumps({'same_T_full_reports':6,'old_reports_immutable':len(original_reports),'old_receipts_immutable':len(original_runs),
        'old_low_observations_appended':47,'old_recommendations_unchanged_with_appended_results':31,'shadow_freeze_at':exp['frozen_at'],
        'old_shadow_not_triggered_n':3,'new_shadow_research_only_n':3,'new_low_n':3,'research_stock_count':len(catalog),'passed':True},ensure_ascii=False))
if __name__=='__main__':main()
