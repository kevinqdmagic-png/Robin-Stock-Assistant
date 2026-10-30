"""Audit T30 append-only publication, prior experiments and the future D1102 freeze."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '5911f75e9d32bf08a9ebe09248da56f091a04993'


def load(path):
    return json.loads((ROOT / path).read_text())


def old(path):
    return json.loads(subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT, text=True))


def one_observation(path, key):
    original = old(path)['items']
    current = {r['id']: r for r in load(path)['items']}
    for a in original:
        b = current[a['id']]
        assert {k: v for k, v in a.items() if k != key} == {k: v for k, v in b.items() if k != key}
        assert b.get(key, [])[:-1] == a.get(key, [])
        assert len(b.get(key, [])) == len(a.get(key, [])) + 1
        assert b[key][-1].get('date', '2026-10-30') == '2026-10-30'
    return len(original)


def main():
    manifest = load('docs/research/combined-pair-20261030-publication-manifest.json')
    encoded = (ROOT / manifest['evidence_file']).read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == manifest['evidence_sha256']
    ev = json.loads(gzip.decompress(encoded))
    frozen = datetime.fromisoformat(manifest['analysis_completed_at'])
    now = datetime.now(timezone.utc)
    assert frozen <= now and frozen < datetime.fromisoformat('2026-11-02T09:30:00+08:00')
    assert datetime.fromisoformat(ev['prior_shadow_validation']['recorded_at']) < frozen
    assert ev['market_module_executed_this_run'] and manifest['reused_report_ids'] == []
    assert len(manifest['new_report_ids']) == 6
    for filing in ev['official_files'].values():
        if filing.get('ok'):
            assert datetime.fromisoformat(filing['retrieved_at']) <= frozen
    assert sum(f.get('ok', False) for f in ev['official_files'].values()) == 32
    de = ev['derived']
    assert de['crosscheck']['recomputed_broad'] == 120 and len(de['deep_recomputed']) == 28
    assert not de['crosscheck']['ohlc_mismatches']
    assert de['low_summary']['count'] == 50 and de['low_summary']['all_paths_complete']
    assert len(de['dragon_selected']) == 13
    assert all(r['seat_reconciliation']['matched'] and r['ths_close_match'] for r in de['dragon_selected'])
    assert de['seat_query_missing_or_not_disclosed'] == [dict(code='001219', listed_on_T=False, buy_query_ok=False, sell_query_ok=False)]
    assert len(ev['independent_direct_bar_checks']) == 21
    assert all(r['max_difference'] == 0 for r in ev['independent_direct_bar_checks'])
    exact = ev['exact_main_price_limit_verification']
    assert (exact['price_limit_verified_n'], exact['closed_at_upper_n'], exact['touched_upper_n'],
            exact['touched_not_sealed_n'], exact['closed_at_lower_n']) == (211, 42, 67, 25, 89)
    assert de['progression_main_10pct']['1_to_2']['prior_full_denominator'] == 28
    assert de['progression_main_10pct']['1_to_2']['advanced'] == 6
    assert de['progression_main_10pct']['3_to_4']['advanced'] == 0
    assert de['progression_main_10pct']['4_to_5']['advanced'] == 1
    quality = load('docs/research/market-review-2026-10-30-evidence.json')['coverage']
    assert (quality['positive_quote_entry_count'], quality['same_day_positive_OHLCV_count'],
            quality['inactive_or_missing_current_OHLCV_count']) == (5574, 5570, 4)
    reports = load('backend/data/research.json')['items']
    runs = load('backend/data/task_runs.json')['items']
    for path, current in [('backend/data/research.json', reports), ('backend/data/task_runs.json', runs)]:
        by_id = {r['id']: r for r in current}
        assert len(by_id) == len(current)
        assert all(by_id[r['id']] == r for r in old(path)['items']), path + ' changed historical records'
    report_by = {r['id']: r for r in reports}
    for task in ['market_review', 'volume_price', 'low_position', 'dragon_tiger', 'combined_pair', 'limitup_single']:
        rs = [r for r in reports if r.get('task_id') == task and r['date'] == '2026-10-30' and
              r.get('report_type') in ('full_daily_research', 'full_trading_research')]
        assert len(rs) == 1
        r = rs[0]
        receipt = [x for x in runs if x.get('status') == 'completed' and x.get('report_ids') == [r['id']]]
        assert len(receipt) == 1 and receipt[0]['trigger'] == 'scheduled'
        assert datetime.fromisoformat(receipt[0]['started_at']) <= datetime.fromisoformat(receipt[0]['completed_at']) <= now
        assert r['planned_entry_date'] == '2026-11-02' and r['earliest_legal_exit_date_if_bought'] == '2026-11-03'
        assert r['candidate_count'] == 0 and r['recommendation_ids'] == []
    combined = report_by['combined-pair-20261030-close-v1']
    assert len(combined['dependency_report_ids']) == 4
    assert all(report_by[rid]['date'] == '2026-10-30' and report_by[rid]['eligible_for_integrated_research'] for rid in combined['dependency_report_ids'])
    assert one_observation('backend/data/recommendations.json', 'results') == 31
    assert len(load('backend/data/recommendations.json')['items']) == 31
    assert one_observation('backend/data/low_position_samples.json', 'observations') == 50
    assert len(load('backend/data/low_position_samples.json')['items']) == 52
    old_vp = old('backend/data/volume_price_samples.json')['items']
    new_vp = load('backend/data/volume_price_samples.json')['items']
    assert new_vp[:len(old_vp)] == old_vp and len(new_vp) == len(old_vp) + 3
    for date_tag in ['20261029', '20261030']:
        path = f'docs/research/shadow-experiments-{date_tag}-v1.json'
        a, b = old(path), load(path)
        for key in ['signals', 'controls', 'formal_cash_observations']:
            assert len(a[key]) == len(b[key])
            for x, y in zip(a[key], b[key]):
                assert {k: v for k, v in x.items() if k != 'results'} == {k: v for k, v in y.items() if k != 'results'}
                assert y['results'][:-1] == x['results'] and len(y['results']) == len(x['results']) + 1
        assert b['results'][:-1] == a['results']
        assert {k: v for k, v in a.items() if k not in ['signals', 'controls', 'formal_cash_observations', 'results']} == {
            k: v for k, v in b.items() if k not in ['signals', 'controls', 'formal_cash_observations', 'results']}
    validation = load('docs/research/shadow-validation-20261030-v1.json')
    assert validation['summary']['necessary_conditions_disproved_n'] == 3 and validation['summary']['verified_fill_n'] == 0
    assert validation['independent_planned_sessions_observed_total'] == 2
    assert all(r['entry_triggered'] is False and r['executable_net_return_pct'] is None for r in validation['signals'])
    exp = load('docs/research/shadow-experiments-20261102-v1.json')
    assert [s['code'] for s in exp['signals']] == ['000568', '600510', '600258']
    assert exp['T'] == '2026-10-30' and exp['planned_D'] == '2026-11-02'
    for s in exp['signals']:
        assert not s['is_recommendation'] and not s['formal_buy_signal'] and not s['send_trade_notification']
        assert s['signal_frozen_at'] == manifest['analysis_completed_at'] and s['entry_fill_verified'] is None
        assert s['earliest_legal_exit_if_bought_at'] == '2026-11-03T09:30:00+08:00'
        assert s['signal_T_horizon_dates'] == {'1': '2026-11-02', '2': '2026-11-03', '5': '2026-11-06', '10': '2026-11-13'}
        assert s['planned_D_horizon_dates'] == {'1': '2026-11-03', '2': '2026-11-04', '5': '2026-11-09', '10': '2026-11-16'}
        assert not s['weekend_overnight_sample'] and s['signal_weekend_gap']
        assert all(datetime.fromisoformat(e['retrieved_at']) <= frozen for e in s['evidence_available_at'])
    assert [h['id'] for h in exp['hypotheses']] == ['H1', 'H2', 'H3']
    assert exp['hypotheses'][0]['treatment_codes'] == ['600510']
    assert exp['hypotheses'][0]['partial_low_position_codes'] == ['000568']
    assert len(exp['formal_cash_observations']) == 2
    assert all(len(r['comparison_pool_codes']) == 28 and r['formal_candidate_count'] == 0 for r in exp['formal_cash_observations'])
    assert (ROOT / 'backend/data/tasks.json').read_bytes() == subprocess.check_output(['git', 'show', BASE + ':backend/data/tasks.json'], cwd=ROOT)
    assert (ROOT / 'backend/data/research_stocks.json').read_bytes() == (ROOT / 'app/src/main/assets/research_stocks.json').read_bytes()
    catalog = load('backend/data/research_stocks.json')['items']
    by_code = {s['code']: s for s in catalog}
    for s in old('backend/data/research_stocks.json')['items']:
        assert by_code[s['code']]['history'][:len(s['history'])] == s['history']
    assert len(catalog) == 48
    assert all(by_code[c]['default_watch'] is False for c in ['000568', '600510', '600258'])
    print(json.dumps(dict(passed=True, same_T_full_reports=6, preserved_old_low_samples=50,
                          new_low_samples=2, original_formal_recommendations=31, new_formal_recommendations=0,
                          prior_experiment_files_appended=2, prior_D30_not_triggered=3,
                          research_only_new_shadows=3, actual_freeze_at=exp['frozen_at'], catalog_count=len(catalog)), ensure_ascii=False))


if __name__ == '__main__':
    main()
