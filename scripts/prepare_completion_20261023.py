#!/usr/bin/env python3
"""Recompute observations from frozen origins; never infer orders from candles."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
import gzip, importlib.util, json, sys
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT.parent/'task_audit_20261023'
sys.path.insert(0,str(ROOT/'backend'))
from learning_loop import build_snapshot, is_session
from low_position_learning import extract_observations
T='2026-10-23'
TD=date.fromisoformat(T)

def load(p):return json.loads(p.read_text())
def pct(a,b):return round((a/b-1)*100,3) if b else None
def stats(vals):
    vals=[v for v in vals if v is not None]
    return {'n':len(vals),'mean_pct':round(mean(vals),3) if vals else None,
            'median_pct':round(median(vals),3) if vals else None,
            'positive_n':sum(v>0 for v in vals),'min_pct':min(vals) if vals else None,'max_pct':max(vals) if vals else None}
def snapshot(c,n,bars):
    b=bars[-1];closes=[x['close'] for x in bars];v=b['volume']
    ma={str(k):round(mean(closes[-k:]),5) if len(bars)>=k else None for k in (5,10,20,60)}
    pos={}
    for k in (20,60,120):
        if len(bars)<k:pos[str(k)]=None;continue
        hi=max(x['high'] for x in bars[-k:]);lo=min(x['low'] for x in bars[-k:])
        pos[str(k)]=round((b['close']-lo)/(hi-lo)*100,3) if hi>lo else None
    return {'code':c,'name':n,**b,'daily_change_pct':pct(b['close'],bars[-2]['close']) if len(bars)>1 else None,
            'rvol':{str(k):round(v/mean(x['volume'] for x in bars[-k-1:-1]),5) if len(bars)>k else None for k in (5,10,20)},
            'ma':ma,'range_position_pct':pos,'distance_ma20_pct':pct(b['close'],ma['20']) if ma['20'] else None,
            'clv':round((b['close']-b['low'])/(b['high']-b['low']),4) if b['high']>b['low'] else None}

def main():
    raw=load(AUDIT/'completion_raw.json');su=load(AUDIT/'completion_supplement.json')
    scan=load(ROOT/'docs/research/low-dragon-2026-10-23-market-scan.json')
    research=load(ROOT/'backend/data/research.json')['items']
    low=load(ROOT/'backend/data/low_position_samples.json')['items']
    recs=load(ROOT/'backend/data/recommendations.json')['items']
    prior=load(ROOT/'docs/research/completion-2026-10-22-evidence.json')['dragon_tiger']
    stamp=datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    daily=raw['daily'];bs={c:r['bars'] for c,r in daily.items() if 'bars' in r}
    assert all(a[-1]['date']==T for a in bs.values())
    def getdaily(c):return bs.get(c,[]),'tencent_unadjusted_daily',[] if c in bs else ['missing']
    learning=build_snapshot(recs,getdaily,now=datetime.fromisoformat(T+'T23:59:00+08:00'),
                            low_position_observations=extract_observations(research,TD))
    learning.update(recorded_at=stamp,evaluated_as_of=T,execution_mode='retrospective_recalculation_with_original_rules',
                    market_data_cutoff_at=T+'T15:00:00+08:00')
    lv=[]
    for s in low:
        c=s['code'];bars=bs[c];day=date.fromisoformat(s['date']);ref=float(s['day0_close'])
        path=[b for b in bars if s['date']<b['date']<=T];cur=bars[-1];byday={b['date']:b for b in bars}
        expected=[];d=day+timedelta(days=1)
        while d<=TD:
            if is_session(d):expected.append(d.isoformat())
            d+=timedelta(days=1)
        missing=[d for d in expected if d not in byday]
        anchor=byday.get(s['date']);match=anchor is not None and abs(anchor['close']-ref)<=0.011
        peak=ref;dd=0
        for b in path:peak=max(peak,b['close']);dd=min(dd,b['close']/peak-1)
        invalid=s.get('invalid_close_below');broken=[b['date'] for b in path if invalid is not None and b['close']<invalid]
        calendars=[]
        for n in (1,3,5,10,15,20,30):
            target=day+timedelta(days=n)
            if target>TD:calendars.append({'day':n,'status':'pending','target_date':target.isoformat()});continue
            observed=max((b for b in bars if b['date']<=target.isoformat()),key=lambda b:b['date'],default=None)
            calendars.append({'day':n,'status':'price_observed' if observed else 'missing','target_date':target.isoformat(),
                              'quote_date':observed['date'] if observed else None,'close_pct':pct(observed['close'],ref) if observed else None})
        trading=[]
        for n in (5,10,20,30):
            mature=len(expected)>=n;bar=byday.get(expected[n-1]) if mature else None
            trading.append({'session':n,'status':'observed' if bar else 'missing' if mature else 'pending',
                            'date':expected[n-1] if mature else None,'close_pct':pct(bar['close'],ref) if bar else None})
        lv.append({'id':s['id']+'-close-20261023-v1','origin_cohort_id':s['id'],'code':c,'name':s['name'],'date':T,
                   'reference_date':s['date'],'reference_close':ref,'original_reference_matches_unadjusted_daily':match,
                   'original_snapshot_verified':s.get('original_snapshot_verified',False),
                   'eligible_for_model_statistics':bool(s.get('eligible_for_model_statistics') and match and not missing),
                   'price_observation':cur,'close_return_pct':pct(cur['close'],ref),
                   'path_mfe_pct':pct(max(b['high'] for b in path),ref) if path else None,
                   'path_mae_pct':pct(min(b['low'] for b in path),ref) if path else None,
                   'max_close_to_close_drawdown_pct':round(dd*100,3),'elapsed_natural_days':(TD-day).days,
                   'elapsed_trading_sessions':len(expected),'observed_trading_sessions':len(path),'missing_sessions':missing,
                   'thirty_natural_days_matured':(TD-day).days>=30,'thirty_sessions_matured':len(expected)>=30,
                   'first_verified_close_below_original_invalid':broken[0] if broken else None,
                   'ever_verified_close_below_original_invalid':bool(broken),'original_invalid_close_below':invalid,
                   'calendar_milestones':calendars,'trading_milestones':trading,
                   'current_structure':snapshot(c,s['name'],bars),'report_ids':['low-position-20261023-close-v1'],
                   'recorded_at':stamp,'executed_trade':False,'executable_net_return_pct':None,
                   'calculation_version':'low_price_observation_v3_including_anchor_in_close_drawdown',
                   'full_validation_completed':not missing,'evidence_status':'single_provider_unadjusted_daily_path',
                   'sources':[daily[c]['source']],'missing':['historical_minute_OHLC','order_and_fill_evidence']})
    broad=[]
    for q in scan['broad_pool']:
        c=q['code']
        if c not in bs:continue
        x=snapshot(c,q['name'],bs[c]);x.update(turnover_pct=q['turnoverratio'],amount_yi=round(q['amount']/1e8,4),
                                           daily_quote_crosscheck={k:round(x[k]-float(q['trade' if k=='close' else k]),5) for k in ('open','high','low','close')})
        orig=next((v for v in scan['deep_pool'] if v['code']==c),{})
        x.update(price_points=orig.get('price_points',{}),tail_1400_close_pct=orig.get('tail_1400_close_pct'))
        broad.append(x)
    spec=importlib.util.spec_from_file_location('seat_helpers',ROOT/'scripts/collect_20261019_combined.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    lh=raw['other_sources']['lhb_details']['payload']['result']['data']
    queries={(r['code'],r['side']):r for r in su['seat_queries']};seats=[]
    for c in sorted({r['code'] for r in su['seat_queries']}):
        options=[r for r in lh if r['SECURITY_CODE']==c];options.sort(key=lambda r:('连续' in r['EXPLANATION'],str(r['TRADE_ID'])))
        x=mod.summarize_seats(options[0],queries)
        union={(str(r.get('OPERATEDEPT_CODE')),r.get('BUY'),r.get('SELL'),str(r.get('TRADE_ID'))):r for r in x['buy_seats_em']+x['sell_seats_em']}
        for tag,term in [('institution','机构专用'),('stock_connect','股通')]:
            rows=[r for r in union.values() if term in str(r.get('OPERATEDEPT_NAME',''))]
            x[tag+'_net_wan']=round(sum(float(r.get('BUY') or 0)-float(r.get('SELL') or 0) for r in rows)/1e4,3)
        x['price_structure']=snapshot(c,x['name'],bs[c]);seats.append(x)
    priorcodes={r['code']:r for r in prior['institution_rows']+prior['stock_connect_rows']}
    dv=[]
    for c,s in sorted(priorcodes.items()):
        b=bs.get(c,[]);by={x['date']:x for x in b};base=by.get('2026-10-22');cur=by.get(T)
        if not base or not cur:dv.append({'code':c,'name':s['name'],'status':'missing_daily'});continue
        dv.append({'code':c,'name':s['name'],'status':'price_observed','base_date':'2026-10-22','base_close':base['close'],
                   'open_pct':pct(cur['open'],base['close']),'close_pct':pct(cur['close'],base['close']),
                   'mfe_pct':pct(cur['high'],base['close']),'mae_pct':pct(cur['low'],base['close']),
                   'daily':cur,'source':daily[c]['source'],'executed_trade':False,'executable_net_return_pct':None,
                   'scope':'previous_published_institution_or_connect_comparison_list_not_recommendation'})
    frozen_dates=sorted({x['date'] for x in research if x.get('task_id')=='market_review' and x.get('codes') and x['date']<T},reverse=True)
    repeats={}
    deepcodes={x['code'] for x in scan['deep_pool']}
    sessions=[];d=TD-timedelta(days=1)
    while len(sessions)<10:
        if is_session(d):sessions.append(d.isoformat())
        d-=timedelta(days=1)
    for n in (5,10):
        covered=sorted(set(frozen_dates)&set(sessions[:n]));old={c for r in research if r.get('task_id')=='market_review' and r['date'] in covered for c in r.get('codes',[])}
        repeats[str(n)]={'expected_session_dates':sessions[:n],'covered_dates':covered,'current_deep_n':28,
                         'overlap_codes':sorted(deepcodes&old),'overlap_pct_available_archive':round(len(deepcodes&old)/28*100,2),
                         'coverage_complete':len(covered)==n,'recommendation_repeat_rate':None}
    out={'market_date':T,'recorded_at':stamp,'learning_snapshot':learning,'low_validations':lv,
         'low_summary':{'count':len(lv),'unique_codes':len({x['code'] for x in lv}),
                        'mature_calendar_30':sum(x['thirty_natural_days_matured'] for x in lv),
                        'eligible_mature_calendar_30':sum(x['thirty_natural_days_matured'] and x['eligible_for_model_statistics'] for x in lv),
                        'anchor_mismatch_n':sum(not x['original_reference_matches_unadjusted_daily'] for x in lv)},
         'broad_recomputed':broad,'dragon_selected':seats,'dragon_previous_validations':dv,
         'dragon_previous_summary':stats([x.get('close_pct') for x in dv]),'repeat_audit':repeats}
    (AUDIT/'completion_derived.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({'low':out['low_summary'],'learn':learning['status_counts'],'validation':learning['validation'],
                      'low_learning':learning['low_position_summary'],'broad_n':len(broad),
                      'lhb':[(x['code'],x['institution_net_wan'],x['stock_connect_net_wan'],x['seat_reconciliation']['matched']) for x in seats],
                      'dragon_previous':out['dragon_previous_summary'],
                      'low_near_ma20':[(x['code'],x['name'],x['distance_ma20_pct'],x['rvol']['20'],x['clv']) for x in broad if x['distance_ma20_pct'] is not None and abs(x['distance_ma20_pct'])<=8 and x['rvol']['20']>=1.5]},ensure_ascii=False))

if __name__=='__main__':main()
