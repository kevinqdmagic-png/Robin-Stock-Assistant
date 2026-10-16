"""Frozen evidence and append-only sample checks for Oct 16 publication."""
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from research_evidence_io import load_evidence

ROOT=Path(__file__).resolve().parents[1]
BASE="b3f241941eb15a0a352c07dd786feefa4eb80061"
def current(path):return json.loads((ROOT/path).read_text())
def original(path):return json.loads(subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT))
e=load_evidence(ROOT/'docs/research/combined-pair-2026-10-16-evidence.json')
assert len(e['volume_price']['deep_samples'])==28
assert len(e['volume_price']['previous_validations'])==28
assert len(e['low_position']['existing_validations'])==24
assert len(e['dragon_tiger']['previous_validations'])==5
assert all(s['seat_reconciliation']['matched'] for s in e['dragon_tiger']['selected_observations'])
assert all(s['daily_crosscheck']['max_ohlc_difference']==0 for s in e['volume_price']['deep_samples'])
assert all(s['board_limit_regime']=='20%' and '封板' not in s['structure']
           for s in e['volume_price']['deep_samples'] if s['code'] in ('300719','301555','301696','688295'))
for filename in ('volume_price_samples.json','low_position_samples.json'):
    path='backend/data/'+filename; old=original(path); new=current(path)
    if filename=='volume_price_samples.json':
        # Legacy excerpt records predate stable IDs. Preserve their exact order
        # and content rather than inventing an identifier while validating.
        assert new['items'][:len(old['items'])]==old['items'],filename
        continue
    index={r['id']:r for r in new['items'] if r.get('id')}
    for before in old['items']:
        after=index[before['id']]
        for key,value in before.items():
            if key=='observations':assert after[key][:len(value)]==value,(filename,before['id'],key)
            else:assert after.get(key)==value,(filename,before['id'],key)
reports=current('backend/data/research.json')['items']
report_map={r['id']:r for r in reports}
new_reports=[r for r in reports if r['id'] not in {x['id'] for x in original('backend/data/research.json')['items']}]
assert len(new_reports) in (5,6)
now=datetime.now(timezone.utc)
for r in new_reports:assert datetime.fromisoformat(r['recorded_at'])<=now
combined=report_map['combined-pair-20261016-close-v1']
assert combined['selected_codes']==['000887']
assert len(combined['dependency_report_ids'])==4
assert all(report_map[i]['date']=='2026-10-16' and report_map[i]['eligible_for_integrated_research'] for i in combined['dependency_report_ids'])
recs=current('backend/data/recommendations.json')['items']
selected=[r for r in recs if r.get('date')=='2026-10-16' and r.get('task_id')=='combined_pair']
assert len(selected)==1 and selected[0]['earliest_legal_exit_date_if_bought']=='2026-10-20'
assert selected[0]['reference_price']==17.72 and selected[0]['group']=='close'
assert selected[0]['results'][0]['executed_trade'] is False
runs=current('backend/data/task_runs.json')['items']
assert any(r['task_id']=='limitup_single' and r['date']=='2026-10-16' and r['status']=='blocked' for r in runs)
assert not any(r['task_id']=='quant_research' and r['date']=='2026-10-16' for r in runs)
for r in runs:
    if r.get('report_ids') and any(i in {n['id'] for n in new_reports} for i in r['report_ids']):
        assert datetime.fromisoformat(r['completed_at'])<=now
        assert datetime.fromisoformat(r['started_at'])<=datetime.fromisoformat(r['completed_at'])
print('Oct16 evidence, board regime, seat reconciliation, sample history, four modules and T+1 gates passed.')
