#!/usr/bin/env python3
"""Independent data/time/coverage checks for the actual Nov 5 manual recovery."""
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from learning_loop import nth_session_after


def load(path):
    return json.loads((ROOT/path).read_text())


def main():
    e=load('docs/research/recovery-20261105-evidence.json')
    raw=load('docs/research/recovery-20261105-bars.json')
    extra=load('docs/research/recovery-20261105-extra-minutes.json')
    minutes={**raw['five_minute'],**extra['five_minute']}
    snap=load('backend/data/baostock/2026-11-05.json')
    daily={r['code'].split('.')[-1]:r for r in snap['rows']}
    coverage=e['coverage']
    assert coverage['stock_verified']==len(daily)==5217
    assert coverage['stock_universe']==5217+len(e['stock_errors'])==5224
    assert coverage['daily_requested']==len(raw['daily_requested'])==151
    assert coverage['daily_crosschecked']==len(e['metrics'])==147
    for code, m in e['metrics'].items():
        hist=raw['daily'][code]['bars']
        assert all(b['date']<='2026-11-05' for b in hist)
        assert len(hist)>=121 and hist[-1]['date']=='2026-11-05'
        assert max(abs(hist[-1][k]-daily[code][k]) for k in ('open','close','high','low'))<=.011
        expected=hist[-1]['volume']/(sum(b['volume'] for b in hist[-21:-1])/20)
        assert abs(expected-m['rvol20'])<1e-9
    expected_stamps=[f'2026-11-05 {v//60:02d}:{v%60:02d}:00' for start,end in ((575,690),(785,900)) for v in range(start,end+1,5)]
    verified=[]
    for code,item in minutes.items():
        if item.get('validation',{}).get('verified'):
            bars=item['bars']
            assert [b['time'] for b in bars]==expected_stamps
            agg={'open':bars[0]['open'],'close':bars[-1]['close'],'high':max(b['high'] for b in bars),'low':min(b['low'] for b in bars)}
            assert max(abs(agg[k]-daily[code][k]) for k in agg)<=.011
            assert abs(sum(b['volume'] for b in bars)/daily[code]['volume']-1)<=.01
            assert abs(sum(b['amount'] for b in bars)/daily[code]['amount']-1)<=.01
            verified.append(code)
    assert len(verified)==coverage['minute_verified']==67
    assert set(e['original_deep_codes'])<=set(verified)
    assert len(e['original_deep_codes'])==coverage['original_deep_minute_verified']==28
    assert len(minutes)==coverage['minute_requested']==68
    assert not minutes['002529']['validation']['verified'] and len(minutes['002529']['bars'])==47
    lhb=load('docs/research/recovery-20261105-lhb-raw.json')
    rows=lhb['main_list']['rows']
    arows=[r for r in rows if not r['SECURITY_CODE'].startswith(('200','900'))]
    assert len(rows)==69 and len(arows)==68
    assert len({r['SECURITY_CODE'] for r in arows})==len(e['lhb_representative_disclosures'])==62
    for code in e['lhb_representative_disclosures']:
        for side in ('BUY','SELL'):
            part=lhb['seat_queries'][code][side]
            assert part['ok'] and part['rows']
            assert all(r['TRADE_DATE'][:10]=='2026-11-05' and r['SECURITY_CODE']==code for r in part['rows'])
    shadows=load('docs/research/recovery-20261105-shadow-manifest.json')['items']
    assert len(shadows)==len({r['code'] for r in shadows})==3
    assert sum(r['task_id']=='combined_pair' for r in shadows)==2
    assert sum(r['task_id']=='limitup_single' for r in shadows)==1
    for s in shadows:
        frozen=datetime.fromisoformat(s['actual_frozen_at'])
        assert frozen<datetime.fromisoformat('2026-11-06T09:30:00+08:00')<=datetime.fromisoformat(s['earliest_legal_exit_if_D_bought'])
        assert s['reference_price']==daily[s['code']]['close']
        assert s['reference_is_live_quote'] is False and s['is_recommendation'] is False
        assert s['executed_trade'] is False and s['buy_order_allowed'] is False
        assert s['executable_net_return_pct'] is None and s['entry_fill'] is None
        day=datetime.fromisoformat(s['planned_observation_date']).date()
        for h,d in s['next_validation_sessions'].items():
            assert nth_session_after(day,int(h)).isoformat()==d
    reports=load('backend/data/research.json')
    new=[r for r in reports['items'] if r['id'].startswith('recovery-20261105-')]
    assert len(new)==7
    for r in new:
        assert r['eligible_for_integrated_research'] is False
        assert r['analysis_completed']==(r['task_id']=='learning_review')
        assert r['candidate_count']==0 and r['recommendation_ids']==[]
    assert '首板封板' not in next(r for r in new if r['task_id']=='market_review')['summary']
    spec=importlib.util.spec_from_file_location('full_audit',ROOT/'scripts/verify_full_research_delivery.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    audit=gate.audit('2026-11-05',reports,load('backend/data/task_runs.json'),datetime.now(ZoneInfo('Asia/Shanghai')))
    assert len(audit['complete'])==0 and len(audit['missing'])==6
    files=e['source_files']+['docs/research/recovery-20261105-shadow-manifest.json','docs/research/recovery-20261105-evidence.json']
    result={'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'status':'source_bounded_recovery_verified',
            'report_count':7,'full_daily_reports_completed':0,'learning_review_completed':True,
            'daily_crosschecked':147,'minute_verified':67,'deep_minute_verified':28,
            'lhb_a_share_codes':62,'lhb_a_share_reasons':68,'research_shadow_count':3,
            'formal_recommendation_count':0,'trade_fills':0,'production_verified':False,
            'backend_unit_tests':237,'delivery_gate_tests':5,
            'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
    path=ROOT/'docs/research/recovery-20261105-quality-check.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False))


if __name__=='__main__':main()
