"""Build dated research tables, not completed reports or trading decisions."""
from pathlib import Path
from statistics import mean,median
import copy,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from collect_combined_20261030 import CACHE,T,PREV,D,START,records,quotes,save,stamp,run,minute,previous
from prepare_completion_20261023 import snapshot,pct,stats
def load(p):return json.loads(p.read_text())
def market():
    qs=quotes();valid=[q for q in qs.values() if float(q.get('trade') or 0)>0 and float(q.get('settlement') or 0)>0]
    daily=records('daily');entry=load(CACHE/'entry-pool.json')['items'];enriched=[]
    for q in entry:
        r=daily[q['code']]
        if not r.get('ok'):continue
        s=snapshot(q['code'],q['name'],r['bars'])
        x=copy.deepcopy(q)
        x.update(bar_date=T,vol=s['volume'],rvol5=s['rvol']['5'],rvol10=s['rvol']['10'],rvol20=s['rvol']['20'],
            ma20=s['ma']['20'],ma60=s['ma']['60'],dist_ma20=s['distance_ma20_pct'],
            tech_score=q['score']+min(s['rvol']['20'] or 0,5)*4,
            input_adjustment='unadjusted; volume denominators exclude T; MA includes T',source=r['source'])
        enriched.append(x)
    enriched.sort(key=lambda x:x['tech_score'],reverse=True);broad=enriched[:120]
    positive=[x for x in broad if -1.5<=float(x['changepercent'])<=11.5 and (x.get('clv') or 0)>=.45]
    deep=positive[:28]
    if len(deep)<28:
        used={x['code'] for x in deep};deep.extend(x for x in broad if x['code'] not in used);deep=deep[:28]
    main=[q for q in valid if q['code'].startswith(('00','60')) and 'ST' not in q['name'].upper() and '退' not in q['name']]
    sealed=[q for q in main if float(q['changepercent'])>=9.5]
    touched=[q for q in main if float(q['high'])/float(q['settlement'])>=1.095]
    failed=[q for q in touched if q not in sealed]
    m={'advance':sum(float(q['changepercent'])>0 for q in valid),'decline':sum(float(q['changepercent'])<0 for q in valid),
       'flat':sum(float(q['changepercent'])==0 for q in valid),'amount_yuan_full_scan':sum(float(q['amount']) for q in valid),
       'standard_non_st_limit_up_sealed':len(sealed),'standard_non_st_limit_up_touched':len(touched),
       'standard_non_st_failed_boards':len(failed),'standard_non_st_limit_down':sum(float(q['changepercent'])<=-9.5 for q in main),
       'proxy_definition':'ordinary non-ST main board close change >=9.5%; touch high/settlement>=1.095; not exact price-limit counts'}
    prior=load(ROOT/'docs/research/market-review-2026-10-29-evidence.json')['deep_pool'];observations=[]
    for old in prior:
        h=daily[old['code']];by={b['date']:b for b in h.get('bars',[])};bar=by.get(T);ref=float(old['trade'])
        observations.append({'code':old['code'],'name':old['name'],'origin_date':PREV,'validation_date':T,
            'origin_close':ref,**(bar or {}),'open_pct':pct(bar['open'],ref) if bar else None,'mfe_pct':pct(bar['high'],ref) if bar else None,
            'mae_pct':pct(bar['low'],ref) if bar else None,'close_pct':pct(bar['close'],ref) if bar else None,
            'execution_status':'daily_price_observation_only','executed_trade':False,'source':h['source']})
    ix=load(CACHE/'index-quotes.json');indices=[]
    for symbol,f in ix['provider_fields'].items():
        assert f[30].startswith('20261030')
        indices.append({'symbol':symbol,'name':f[1],'close':float(f[3]),'change_pct':float(f[32]),'high':float(f[33]),'low':float(f[34]),'quote_time':f[30]})
    result={'market_date':T,'retrieved_at_utc':stamp(),'coverage':{'full_scan':len(valid),'raw_records':len(qs),'page_errors':[k for k,r in records('sina').items() if not r.get('ok')],
        'broad_pool':len(broad),'deep_pool':len(deep),'entry_helper_count':160,'entry_helper_not_validated_alpha':True},
        'market':m,'broad_pool':broad,'deep_pool':deep,'previous_pool_validation':observations,
        'previous_pool_statistics':{**stats([o['close_pct'] for o in observations]),'mean_mfe_pct':mean(o['mfe_pct'] for o in observations if o['mfe_pct'] is not None),
            'mean_mae_pct':mean(o['mae_pct'] for o in observations if o['mae_pct'] is not None),'mae_le_minus5_count':sum(o['mae_pct'] is not None and o['mae_pct']<=-5 for o in observations)},
        'index_quotes':{'source':ix['source'],'retrieved_at_utc':ix['retrieved_at'],'items':indices},
        'analyst_approval':False,'note':'Coverage/entry helper only; complete analyst reasoning, filings, previous validations and new freeze archived separately.'}
    save(ROOT/'docs/research/market-review-2026-10-30-evidence.json',result)
    print(json.dumps({'coverage':result['coverage'],'market':m,'indices':indices,'deep':[(q['code'],q['name'],q['trade'],q['changepercent'],round(q['rvol20'],3)) for q in deep]},ensure_ascii=False),flush=True)
def minutes():
    m=load(ROOT/'docs/research/market-review-2026-10-30-evidence.json')
    codes={q['code'] for key in ['deep_pool','previous_pool_validation'] for q in m[key]}
    codes.update(s['code'] for s in load(ROOT/'backend/data/low_position_samples.json')['items'])
    codes.update(k.split(':')[0] for k in records('seats'))
    run('minute',sorted(codes),minute,workers=3)
def assemble():
    out={'market_date':T,'previous_session':PREV,'planned_entry_date':D,'actual_started_at_utc':START,
        'market_review_executed_this_run':True,'market_evidence':'docs/research/market-review-2026-10-30-evidence.json',
        'sina_pages':records('sina'),'quotes':quotes(),'lhb_lists':records('lhb'),'limit_up_pools':records('pools'),
        'daily_histories':records('daily'),'seat_queries':records('seats'),'minute_price_points':records('minute'),
        'actual_collection_completed_at_utc':stamp(),'collection_method':'checkpointed exact raw responses; published T29 unadjusted histories extended only with date-verified T30 OHLCV; new codes queried directly'}
    # Fresh full histories supply independent current-bar/volume/anchor checks.
    direct=records('direct-shadow');cross=[]
    for c,r in direct.items():
        if r.get('ok') and out['daily_histories'].get(c,{}).get('ok'):
            a=out['daily_histories'][c]['bars'][-1];b=r['bars'][-1]
            cross.append({'code':c,'max_difference':max(abs(a[k]-b[k]) for k in ['open','close','high','low','volume'])})
            assert cross[-1]['max_difference']<=.011,(c,'direct/history extension mismatch')
    out['independent_direct_bar_checks']=cross
    save(ROOT/'tmp/combined-20261030-raw.json',out)
    batches=list(records('bulk').values());fields={s:f for r in batches for s,f in r.get('provider_fields',{}).items() if len(f)>48}
    save(ROOT/'tmp/combined-20261030-quote-upper-check.json',{'market_date':T,'source':'Tencent original URLs in batches; date-verified provider upper/lower fields',
        'requested_codes':load(CACHE/'requested-bulk.json'),'batches':batches,'provider_fields':fields,'upper_field':47,'lower_field':48,'timestamp_field':30})
    save(ROOT/'tmp/combined-20261030-extension.json',{'daily_histories':{},'minute_price_points':{},'seat_queries':{},'limit_up_pools':{},'transport_failure_recorded':False})
    print(json.dumps({'daily':len(out['daily_histories']),'valid_daily':sum(r.get('ok',False) for r in out['daily_histories'].values()),'minute':len(out['minute_price_points']),'seats':len(out['seat_queries']),'independent_direct_checks':len(cross)}),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
