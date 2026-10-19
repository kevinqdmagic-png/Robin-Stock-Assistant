"""Append-only, time-bound and four-prerequisite checks for Oct19 research."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from research_evidence_io import load_evidence

ROOT=Path(__file__).resolve().parents[1]
BASE='2f655a180e5e7b845ed05c1cbb5cb734e35f4c27'
def load(p):return json.loads((ROOT/p).read_text())
def old(p):return json.loads(subprocess.check_output(['git','show',BASE+':'+p],cwd=ROOT))

e=load_evidence(ROOT/'docs/research/combined-pair-2026-10-19-evidence.json')
v=e['volume_price']; d=e['dragon_tiger']; l=e['low_position']
assert len(v['deep_samples'])==len(v['previous_validations'])==28
assert v['broad_verified']==len(v['broad_samples'])>=80
assert len(l['existing_validations'])==26 and 3<=len(l['new_candidates'])<=8
assert len(d['previous_validations'])==5 and len(d['selected_observations'])==5
assert d['reason_rows']==len(d['raw_reason_rows_data'])==80
assert all(s['seat_reconciliation']['matched'] for s in d['selected_observations'])
assert all(s['daily_crosscheck']['max_ohlc_difference']==0 for s in v['deep_samples']+l['new_candidates'])
assert all(s['tail_return_1400_to_1500_pct'] is not None for s in v['deep_samples']+l['new_candidates'])
assert all(r.get('calculation_version')=='low_price_observation_v2_20261019' for r in l['existing_validations'])
assert all(max(b['date'] for b in bs)<='2026-10-19' for bs in e['raw_daily_histories'].values())
for name in ('volume_price_samples.json','low_position_samples.json'):
    p='backend/data/'+name;before=old(p);after=load(p)
    if name.startswith('volume'):
        assert after['items'][:len(before['items'])]==before['items']
    else:
        by={r['id']:r for r in after['items']}
        for r in before['items']:
            cur=by[r['id']]
            for k,value in r.items():
                if k=='observations':assert cur[k][:len(value)]==value,(r['id'],k)
                else:assert cur.get(k)==value,(r['id'],k)
reports=load('backend/data/research.json')['items'];rmap={r['id']:r for r in reports}
new=[r for r in reports if r['id'] not in {r['id'] for r in old('backend/data/research.json')['items']}]
assert len(new)==6
now=datetime.now(timezone.utc)
for r in new:
    assert datetime.fromisoformat(r['recorded_at'])<=now
    assert len(r['body'])>(500 if r['report_type']=='retrospective_review' else 1200)
comb=rmap['combined-pair-20261019-close-v1']
assert comb['selected_codes']==[] and comb['candidate_count']==0
assert len(comb['dependency_report_ids'])==4
assert {rmap[r]['task_id'] for r in comb['dependency_report_ids']}=={'market_review','volume_price','low_position','dragon_tiger'}
assert all(rmap[r]['date']=='2026-10-19' and rmap[r]['eligible_for_integrated_research'] for r in comb['dependency_report_ids'])
runs=load('backend/data/task_runs.json')['items']
for r in new:
    matching=[run for run in runs if r['id'] in run.get('report_ids',[])]
    assert matching
    assert all(datetime.fromisoformat(run['started_at'])<=datetime.fromisoformat(run['completed_at'])<=now for run in matching)
    if r['task_id'] in ('volume_price','low_position','dragon_tiger','combined_pair'):
        assert any(run['status']=='completed' for run in matching)
assert not any(r['task_id']=='quant_research' and r['date']=='2026-10-19' for r in runs)
recs=load('backend/data/recommendations.json')['items']
assert not any(r.get('task_id')=='combined_pair' and r['date']=='2026-10-19' for r in recs)
zd=next(r for r in recs if r['id']=='combined-pair-20261016-000887-close-v1')
result=next(r for r in zd['results'] if r.get('id')==zd['id']+'-daily-validation-20261019')
assert result['observed_open']==17.12 and result['trigger_status']=='not_triggered_open_below_frozen_lower_bound'
assert result['strategy_sample_activated'] is False and result['executable_net_return_pct'] is None
forward=rmap['limitup-single-20261020-review-v2']
assert forward['market_date']=='2026-10-19' and forward['candidate_count']==0 and forward['ladder_complete'] is False
assert rmap['limitup-single-20261019-retro-v2']['not_a_contemporaneous_cash_decision'] is True
catalog=load('backend/data/research_stocks.json')['items']
before_codes={r['code'] for r in old('backend/data/research_stocks.json')['items']}
assert all(r['default_watch'] is False for r in catalog if r['code'] not in before_codes)
assert len(e['issuer_primary_pdf_checks'])>=20 and not any('error' in r for r in e['issuer_primary_pdf_checks'])
print('Oct19: four full modules, raw/minute boundaries, seat reconciliation, unchanged histories, cash decision, T+1 and actual times passed.')
