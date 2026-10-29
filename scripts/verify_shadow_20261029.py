"""Append only dated observations to the previously frozen D29 experiments.

This does not simulate orders. A necessary price condition can disprove a
trigger; isolated minute prices cannot prove the complete trigger or a fill.
"""
from pathlib import Path
from datetime import date, datetime, timezone
from statistics import mean, median
import copy, json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'scripts')]
from learning_loop import nth_session_after
from prepare_completion_20261023 import pct
from derive_combined_20261029 import checkpoints
T = '2026-10-29'
ORIGINAL = 'docs/research/shadow-experiments-20261029-v1.json'
OUT = 'tmp/shadow-validation-20261029.json'
def load(p): return json.loads((ROOT/p).read_text())
def main():
    original = load(ORIGINAL)
    assert original['T']=='2026-10-28' and original['planned_D']==T
    assert not any(x.get('date')==T for x in original['results']), 'reuse existing validation'
    focused=load('tmp/shadow-inputs-20261029.json')
    raw=load('tmp/combined-20261029-raw.json') if (ROOT/'tmp/combined-20261029-raw.json').exists() else copy.deepcopy(focused)
    extension=load('tmp/combined-20261029-extension.json') if (ROOT/'tmp/combined-20261029-extension.json').exists() else {}
    for k,v in extension.items():
        if k in raw and isinstance(v,dict): raw[k].update(v)
    for k in ['daily_histories','minute_price_points']:
        raw[k].update({c:r for c,r in focused[k].items() if r.get('ok')})
    qs=load('tmp/combined-20261029-quote-upper-check.json') if (ROOT/'tmp/combined-20261029-quote-upper-check.json').exists() else focused['quoted_upper']
    qs['provider_fields'].update(focused['quoted_upper']['provider_fields'])
    bench=load('tmp/combined-20261029-supplement.json')['benchmarks']['sh000300']
    bby={b['date']:b for b in bench['bars']}
    bp=pct(bby[T]['close'],bby[original['T']]['close'])
    stamp=datetime.now(timezone.utc).isoformat()
    out={'date':T,'recorded_at':stamp,'origin_experiment':ORIGINAL,
         'original_frozen_at':original['frozen_at'],'benchmark_code':'sh000300',
         'benchmark_return_from_signal_T_close_pct':bp,'benchmark_source':bench['source'],
         'report_ids':['volume-price-20261029-close-v1','combined-pair-20261029-close-v1','limitup-single-20261029-close-v2'],
         'signals':[],'controls':[],'independent_market_shadow':[],
         'cost_status':'No verified entry/exit orders, quantities, minimum commission or slippage; no net return.',
         'statistical_unit':'code and planned D market event; overlapping research reports are not independent trades'}
    def observation(s, role):
        c=s['code'];ref=s['reference_price'];r=raw['daily_histories'].get(c,{})
        bar=next((b for b in r.get('bars',[]) if b['date']==T),None)
        sym=('sh' if c.startswith('6') else 'sz')+c;f=qs['provider_fields'].get(sym)
        if not bar or not f or not f[30].startswith('20261029'):
            return {'code':c,'date':T,'recorded_at':stamp,'status':'missing_dated_price',
                    'entry_triggered':None,'entry_fill_verified':None,'executable_net_return_pct':None}
        assert abs(bar['close']-float(f[3]))<.011
        cp=checkpoints(raw['minute_price_points'].get(c,{}),ref)
        upper=float(f[47]);lower=float(f[48]);reason=[];trigger=None
        if role=='signal' and s['parent_task_id']=='combined_pair':
            lo,hi=s['confirmation_range']
            for clock in ['0945','1030']:
                p=cp.get('points',{}).get(clock)
                if p and not lo<=p['price']<=hi:
                    trigger=False;reason.append(f'{clock} price {p["price"]} outside frozen confirmation {lo}..{hi}')
                if p and p.get('cumulative_amount_cny') is not None and p['cumulative_volume_lots']>0:
                    vwap=p['cumulative_amount_cny']/(p['cumulative_volume_lots']*100)
                    p['calculated_cumulative_vwap']=vwap
                    if p['price']<vwap:
                        trigger=False;reason.append(f'{clock} price below contemporaneous cumulative VWAP')
        elif role=='signal' and s['parent_task_id']=='limitup_single' and bar['high']<upper-.001:
            trigger=False;reason.append('Dated daily high below provider-reported D upper price: reseal condition impossible')
        if not reason: reason=['Necessary conditions not disproved, but auction, sequence, 60-second support and fills unverified']
        signal_h=[];plan_h=[]
        for h in [1,2,5,10]:
            d=nth_session_after(date.fromisoformat(original['T']),h).isoformat()
            signal_h.append({'h':h,'date':d,'axis':'signal_T','status':'price_observed' if d==T else 'pending',
                             'close_observation_pct':pct(bar['close'],ref) if d==T else None})
        for h in [0,1,2,5,10]:
            d=nth_session_after(date.fromisoformat(T),h).isoformat() if h else T
            plan_h.append({'h':h,'date':d,'axis':'planned_D','status':'price_observed' if d==T else 'pending',
                           'close_observation_pct':pct(bar['close'],ref) if d==T else None})
        return {'id':f'shadow-price-{T.replace("-","")}-{c}-v1','code':c,'name':s['name'],
                'market_event_id':f'cnA:{T}:{c}','date':T,'recorded_at':stamp,
                'reference_price':ref,'reference_definition':'frozen signal T close, not entry price',
                'daily':bar,'open_observation_pct':pct(bar['open'],ref),
                'close_observation_pct':pct(bar['close'],ref),
                'MFE_price_observation_pct':pct(bar['high'],ref),'MAE_price_observation_pct':pct(bar['low'],ref),
                'CSI300_excess_price_observation_pct':round(pct(bar['close'],ref)-bp,3),
                'minute_checkpoints':cp,'auction_0925':None,'D_actual_upper_price':upper,'D_actual_lower_price':lower,
                'provider_timestamp':f[30],'day_touched_upper':abs(bar['high']-upper)<.011,
                'day_closed_at_upper':abs(bar['close']-upper)<.011,
                'day_touched_upper_not_closed':abs(bar['high']-upper)<.011 and bar['close']<upper-.011,
                'sealed_or_failed_after_entry':None,'entry_triggered':trigger,
                'trigger_evidence':reason,'entry_fill_verified':False if trigger is False else None,
                'entry_status':'not_triggered' if trigger is False else 'full_condition_unverified',
                'actual_trade_claimed':False,'simulated_entry_recorded':False,
                'earliest_legal_exit_if_bought_at':'2026-10-30T09:30:00+08:00',
                'legal_exit_window_reached':False,'executable_net_return_pct':None,
                'signal_T_horizons':signal_h,'planned_D_horizons':plan_h,
                'status':'dated_price_observation_not_trade','sources':[r['source'],qs['source'],cp.get('source')],
                'no_order_fill_or_intra_minute_sequence_inference':True}
    for s in original['signals']:out['signals'].append(observation(s,'signal'))
    for s in original['controls']:out['controls'].append(observation(s,'control'))
    # The earlier market report also observed 横河. Preserve it, and link the
    # overlapping 纽威 event rather than count a second trade for the same code/D.
    for c,n,ref in [('603699','纽威股份',38.39),('300539','横河精密',20.94)]:
        s={'code':c,'name':n,'reference_price':ref}
        a=observation(s,'market_shadow');a.update(origin_report_id='market-review-20261028-close-v1',
            shared_market_event_with_combined=c=='603699',entry_triggered=None,entry_fill_verified=None,
            entry_status='original_market_report_conditions_not_reconstructed')
        out['independent_market_shadow'].append(a)
    values=[r['close_observation_pct'] for r in out['signals'] if 'close_observation_pct' in r]
    out['summary']={'frozen_signal_n':len(original['signals']),'observed_n':len(values),
        'independent_planned_sessions_n':1,'independent_code_D_events':len({s['market_event_id'] for s in original['signals']}),
        'necessary_conditions_disproved_n':sum(s['entry_triggered'] is False for s in out['signals']),
        'full_trigger_unverified_n':sum(s['entry_triggered'] is None for s in out['signals']),
        'verified_fill_n':0,'missing_daily_price_n':len(original['signals'])-len(values),
        'close_price_mean_pct':round(mean(values),3) if values else None,
        'close_price_median_pct':round(median(values),3) if values else None,
        'net_return_mean_pct':None,'net_return_median_pct':None,'strategy_win_rate':None,
        'review_ready':False,'review_min_independent_sessions':20,
        'no_supported_weak_market_edge_claim':True}
    (ROOT/OUT).write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    # Archive assembly later appends these results atomically alongside reports.
    print(json.dumps({'summary':out['summary'],'signals':[{k:v for k,v in s.items() if k in ['code','entry_triggered','trigger_evidence','daily','close_observation_pct']} for s in out['signals']]},ensure_ascii=False))
if __name__=='__main__':main()
