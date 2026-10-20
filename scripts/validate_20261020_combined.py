#!/usr/bin/env python3
"""Recompute publication invariants without inventing fills or replacing history."""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'backend/data'


def read(name):
    return json.loads((DATA / name).read_text())


def main():
    e = load_evidence(ROOT / 'docs/research/combined-pair-2026-10-20-evidence.json')
    research, runs, recs = (read(n)['items'] for n in ('research.json', 'task_runs.json', 'recommendations.json'))
    reports = {r['id']: r for r in research}
    ids = [t.replace('_', '-') + '-20261020-close-v1'
           for t in ('market_review', 'volume_price', 'low_position', 'dragon_tiger', 'combined_pair')]
    for rid in ids:
        r = reports[rid]
        assert r['date'] == '2026-10-20' and r['eligible_for_integrated_research']
        assert any(x['status'] == 'completed' and rid in x['report_ids'] and x['task_id'] == r['task_id'] for x in runs)
        for field in ('published_at', 'recorded_at'):
            assert datetime.fromisoformat(r[field]) <= datetime.now(timezone.utc)
    assert reports[ids[-1]]['prerequisite_report_ids'] == ids[:4]
    assert len([r for r in research if r['id'] == ids[-1]]) == 1
    v = e['volume_price']; ss = v['deep_samples']
    assert len(ss) == 28 and len({s['code'] for s in ss}) == 28
    assert v['broad_verified'] == len(v['broad_samples']) == 108
    assert set(v['supplemental_raw_basis_codes']) == {'688836', '688795'}
    assert all(s['daily_crosscheck']['max_ohlc_difference'] == 0 for s in ss)
    assert len(v['previous_validations']) == 28
    assert v['cumulative_v4_next_day_price_statistics']['verified'] == 56
    assert v['cumulative_v4_next_day_price_statistics']['executable_sample_count'] == 0
    for s in ss:
        bs = e['raw_daily_histories'][s['code']] if s['code'] in v['supplemental_raw_basis_codes'] else e['qfq_daily_histories'][s['code']]
        assert bs[-1]['date'] == '2026-10-20'
        for n in (5, 10, 20):
            expected = round(bs[-1]['volume'] / statistics.fmean(x['volume'] for x in bs[-n-1:-1]), 3)
            assert expected == s['rvol'][str(n)], (s['code'], n)
        assert s['frozen_at'] == reports[ids[1]]['published_at']
    lows = e['low_position']['existing_validations']
    assert len(lows) == 32 and all(r['full_validation_completed'] for r in lows)
    assert sum(x['observed_close_below_original_invalid'] for x in lows) == 4
    assert sum(x['ever_verified_close_below_original_invalid'] for x in lows) == 8
    assert not any(x['thirty_natural_days_matured'] for x in lows)
    assert [s['code'] for s in e['low_position']['new_candidates']] == ['301658', '003021', '300314']
    assert len(read('low_position_samples.json')['items']) == 35
    d = e['dragon_tiger']
    assert (d['reason_rows'], d['unique_codes'], d['mainland_a_unique_codes']) == (82, 67, 58)
    assert len(d['previous_validations']) == 5
    assert all(s['seat_reconciliation']['matched'] for s in d['selected_observations'])
    runjian = next(s for s in d['selected_observations'] if s['code'] == '002929')
    assert abs(runjian['net_cny'] - 188603.93) < .01
    assert len(e['combined_horizon_validation']) == 8
    row = next(r for r in recs if r['id'] == 'combined-pair-20261020-300458-close-v1')
    assert row['reference_price'] == 28.64 and row['planned_entry_date'] == '2026-10-21'
    assert row['earliest_legal_exit_date_if_bought'] == '2026-10-22'
    assert row['entry_price_condition_range'] == [28.55, 28.85] and row['results'] == []
    assert row['rules']['exit_weights_pct'] == [50, 25, 25]
    from sys import path
    path.insert(0, str(ROOT / 'backend'))
    from entry_confirmation import NEEDED
    assert NEEDED.issubset(row['rules'])
    assert row['group'] == 'close' and row['strategy'] == 'combined_limitup_watch'
    old = next(r for r in recs if r['id'] == 'combined-pair-20261016-000887-close-v1')
    assert old['results'][-1]['status'] == 'not_triggered'
    limit = reports['limitup-single-20261021-review-v2']
    assert limit['date'] == '2026-10-21' and limit['market_date'] == '2026-10-20'
    assert not limit['eligible_for_integrated_research'] and limit['candidate_count'] == 0
    for code in ('301658', '003021', '300314', '300458'):
        s = next(s for s in read('research_stocks.json')['items'] if s['code'] == code)
        assert s['default_watch'] is False and s['history'][-1]['date'] == '2026-10-20'
    assert read('research_stocks.json') == json.loads((ROOT / 'app/src/main/assets/research_stocks.json').read_text())
    print('T20 invariants passed: four prerequisites, 28 deep/2 explicit raw supplements, prior28/low32/dragon5, 1 frozen candidate, D21 cash, no inferred fills.')


if __name__ == '__main__':
    main()
