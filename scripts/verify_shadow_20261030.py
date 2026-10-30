"""Validate every frozen shadow/control first; never infer order fills."""
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean,median
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from learning_loop import nth_session_after,is_session
from prepare_completion_20261023 import pct
import derive_combined_20261030 as derived
T='2026-10-30'; TD=date.fromisoformat(T);CACHE=ROOT/'tmp/t30-inputs'
def load(p):return json.loads(p.read_text())
def main():
    files=sorted((ROOT/'docs/research').glob('shadow-experiments-202610*-v1.json'))
    histories={p.stem:load(p) for p in (CACHE/'daily').glob('*.json')}
    histories.update({p.stem:load(p) for p in (CACHE/'direct-shadow').glob('*.json') if load(p).get('ok')})
    minutes={p.stem:load(p) for p in (CACHE/'minute').glob('*.json')}
    batches=[load(p) for p in (CACHE/'bulk').glob('*.json')]+[load(CACHE/'first-shadow-quotes.json')]
    fs={s:(f,r) for r in batches for s,f in r.get('provider_fields',{}).items() if len(f)>48}
    bench=load(CACHE/'benchmark/sh000300.json');bby={b['date']:b for b in bench['bars']}
    stamp=datetime.now(timezone.utc).isoformat();outputs=[]
    def observe(s,exp,kind):
        c=s['code'];ref=float(s['reference_price']);hist=histories.get(c,{})
        by={b['date']:b for b in hist.get('bars',[])};bar=by.get(T);D=exp['planned_D']
        symbol=('sh' if c.startswith('6') else 'sz')+c;f,batch=fs.get(symbol,(None,None))
        result={'id':s.get('id',c)+'-observation-20261030-v1','code':c,'name':s['name'],'date':T,'recorded_at':stamp,
            'market_event_id':s.get('market_event_id',f'cnA:{D}:{c}'),'origin_signal_T':exp['T'],'planned_D':D,
            'reference_price':ref,'reference_definition':'original frozen signal T close, never an entry fill',
            'entry_triggered':None,'entry_fill_verified':None,'executable_net_return_pct':None,
            'actual_trade_claimed':False,'simulated_entry_recorded':False,'sources':[hist.get('source'),bench['source']],
            'earliest_legal_exit_if_bought_at':s.get('earliest_legal_exit_if_bought_at'),
            'legal_exit_window_reached':T>=str(s.get('earliest_legal_exit_if_bought_at','9999'))[:10]}
        if not bar or not f or not f[30].startswith('20261030'):
            return {**result,'status':'missing_dated_price','entry_status':'unverified'}
        assert abs(float(f[3])-bar['close'])<.011
        upper=float(f[47]);lower=float(f[48]);bp=pct(bby[T]['close'],bby[exp['T']]['close'])
        result.update(daily=bar,open_observation_pct=pct(bar['open'],ref),close_observation_pct=pct(bar['close'],ref),
            MFE_price_observation_pct=pct(bar['high'],ref),MAE_price_observation_pct=pct(bar['low'],ref),
            session_upper_price=upper,session_lower_price=lower,provider_timestamp=f[30],
            session_touched_upper=abs(bar['high']-upper)<.011,session_closed_at_upper=abs(bar['close']-upper)<.011,
            session_touched_upper_not_closed=abs(bar['high']-upper)<.011 and bar['close']<upper-.011,
            CSI300_excess_price_observation_pct=round(pct(bar['close'],ref)-bp,3),benchmark_return_from_signal_T_close_pct=bp,
            status='dated_price_observation_not_trade',no_order_fill_or_intra_minute_sequence_inference=True)
        result['sources'].append(batch['source'])
        reason=[];trigger=None
        if kind=='signals' and D==T:
            cp=derived.checkpoints(minutes.get(c,{}),ref);result['minute_checkpoints']=cp
            result['D_actual_upper_price']=upper;result['D_actual_lower_price']=lower
            if s['parent_task_id']=='combined_pair':
                lo,hi=s['confirmation_range'];pull=s.get('pullback_or_auction_range')
                if pull and bar['low']>pull[1]:
                    trigger=False;reason.append(f"All-day low {bar['low']} above frozen required pullback upper bound {pull[1]}")
                for clock in ['0945','1030']:
                    p=cp.get('points',{}).get(clock)
                    if p and not lo<=p['price']<=hi:
                        trigger=False;reason.append(f"{clock} quote {p['price']} outside original confirmation {lo}..{hi}")
                    if p and p.get('cumulative_amount_cny') is not None and p['cumulative_volume_lots']:
                        vwap=p['cumulative_amount_cny']/(100*p['cumulative_volume_lots']);p['calculated_cumulative_vwap']=vwap
                        if p['price']<vwap:
                            trigger=False;reason.append(f"{clock} quote {p['price']} below same-time cumulative VWAP {vwap:.5f}")
            else:
                if bar['high']<upper-.001:
                    trigger=False;reason.append('All-day high below actual date-verified upper price; no possible reseal')
                # Both original named peers were required >=3% at the trigger.
                # A whole-day high below that threshold disproves necessity
                # without deriving any unknown intra-minute event sequence.
                for peer in ['000999','600329']:
                    peer_by={b['date']:b for b in histories.get(peer,{}).get('bars',[])}
                    a,cur=peer_by.get(exp['T']),peer_by.get(T)
                    if a and cur and cur['high']/a['close']<1.03:
                        trigger=False;reason.append(f"Frozen peer {peer} whole-day high return {pct(cur['high'],a['close'])}% < required +3%")
            result['auction_0925']=None
        elif kind=='signals':
            last=next((r for r in reversed(s.get('results',[])) if r.get('entry_triggered') is False),None)
            if last:
                trigger=False;reason=['Original D necessary-condition failure carried forward; later price does not reopen the old signal']
                result['prior_trigger_validation_id']=last.get('id')
            else:reason=['Original D condition/auction/queue evidence not reconstructed from later daily prices']
        else:reason=['Frozen comparison arm; price observation only, no hypothetical fill']
        if not reason:reason=['Necessary conditions not disproved; auction, sequence, 60-second support and queue fills remain unverified']
        result.update(entry_triggered=trigger,entry_fill_verified=False if trigger is False else None,
            entry_status='not_triggered' if trigger is False else 'full_condition_unverified',trigger_evidence=reason)
        for axis,anchor,hs in [('signal_T',exp['T'],[1,2,5,10]),('planned_D',D,[0,1,2,5,10])]:
            rows=[]
            for h in hs:
                target=(nth_session_after(date.fromisoformat(anchor),h).isoformat() if h else anchor)
                cur=by.get(target);path=[b for b in hist.get('bars',[]) if exp['T']<b['date']<=target]
                rows.append({'h':h,'date':target,'axis':axis,'status':'pending' if target>T else 'price_observed' if cur else 'missing_daily_price',
                    'close_observation_pct':pct(cur['close'],ref) if cur and target<=T else None,
                    'MFE_path_price_pct':pct(max(b['high'] for b in path),ref) if path and cur and target<=T else None,
                    'MAE_path_price_pct':pct(min(b['low'] for b in path),ref) if path and cur and target<=T else None})
            result[axis+'_horizons']=rows
        return result
    for file in files:
        exp=load(file)
        if exp['planned_D']>T:continue
        assert not any(r.get('date')==T for r in exp.get('results',[]))
        out={'date':T,'recorded_at':stamp,'origin_experiment':str(file.relative_to(ROOT)),'original_frozen_at':exp['frozen_at'],
            'origin_signal_T':exp['T'],'planned_D':exp['planned_D'],'benchmark_code':'sh000300','benchmark_source':bench['source'],
            'signals':[observe(s,exp,'signals') for s in exp['signals']], 'controls':[observe(s,exp,'controls') for s in exp['controls']],
            'statistical_unit':'stock and planned D market event; same-stock/report overlaps are not independent trades',
            'cost_status':'No verified orders/quantity/minimum commission/slippage; executable net return unavailable'}
        values=[r['close_observation_pct'] for r in out['signals'] if 'close_observation_pct' in r]
        out['summary']={'frozen_signal_n':len(exp['signals']),'observed_n':len(values),'missing_daily_price_n':len(exp['signals'])-len(values),
            'independent_planned_sessions_n':1,'independent_code_D_events':len({s['market_event_id'] for s in exp['signals']}),
            'necessary_conditions_disproved_n':sum(r.get('entry_triggered') is False for r in out['signals']),
            'full_trigger_unverified_n':sum(r.get('entry_triggered') is None for r in out['signals']),'verified_fill_n':0,
            'close_price_mean_pct':round(mean(values),3) if values else None,'close_price_median_pct':round(median(values),3) if values else None,
            'net_return_mean_pct':None,'strategy_win_rate':None,'review_ready':False,'review_min_independent_sessions':20}
        outputs.append(out)
    latest=next(o for o in outputs if o['planned_D']==T)
    latest['all_frozen_experiment_followups']=outputs[:-1]
    latest['all_frozen_experiment_files']=[o['origin_experiment'] for o in outputs]
    latest['independent_planned_sessions_observed_total']=len(outputs)
    latest['independent_market_shadow']=[]
    for origin,c,n,ref in [('2026-10-29','600118','中国卫星',55.90),('2026-10-29','300900','广联航空',22.65),('2026-10-28','300539','横河精密',20.94)]:
        D=nth_session_after(date.fromisoformat(origin),1).isoformat()
        a=observe({'code':c,'name':n,'reference_price':ref,'results':[]},{'T':origin,'planned_D':D},'market_report')
        a.update(origin_report_id='market-review-'+origin.replace('-','')+'-close-v1',original_market_conditions_not_fully_reconstructed=True,
            shared_market_event_with_combined=(c=='600118'))
        latest['independent_market_shadow'].append(a)
    dest=ROOT/'tmp/shadow-validation-20261030.json';dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(latest,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({'primary_D30_summary':latest['summary'],'prior_experiment_followups':len(outputs)-1,'total_independent_D_days':len(outputs),
        'signals':[{k:r.get(k) for k in ['code','entry_triggered','close_observation_pct','trigger_evidence']} for r in latest['signals']]},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
