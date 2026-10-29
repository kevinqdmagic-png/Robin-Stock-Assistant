"""Bounded, checkpointed collection after the first exec transport was lost.

Frozen unadjusted T28 histories may be extended only with an independently
dated T29 provider OHLCV bar. Those are sourced quotes, never estimated prices.
New symbols receive their own unadjusted history. Each response is saved before
the next phase, so an interrupted connection cannot erase completed evidence.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import Request,urlopen
import gzip,json,re,sys
from collect_combined_20261029 import ROOT,T,PREV,START,stamp,page,get,lhb,seat,symbol,daily,minute
CACHE=ROOT/'tmp/t29-inputs'
def load(p):return json.loads(p.read_text())
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.writing');q.write_text(json.dumps(d,ensure_ascii=False));q.replace(p)
def records(group):return {p.stem:load(p) for p in (CACHE/group).glob('*.json')}
def run(group,keys,fn,workers=4):
    keys=[str(k) for k in keys];missing=[k for k in keys if not (CACHE/group/(k+'.json')).exists()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(fn,k):k for k in missing}
        for job in as_completed(jobs):save(CACHE/group/(jobs[job]+'.json'),job.result())
    rs=records(group);print(json.dumps({'phase':group,'requested':len(keys),'newly_collected':len(missing),'ok':sum(v.get('ok',False) for v in rs.values()),'saved':len(rs)},ensure_ascii=False),flush=True)
def pool(day):
    return get('https://push2ex.eastmoney.com/getTopicZTPool',{'ut':'7eea3edcaed734bea9cbfc24409ed989','dpt':'wz.ztzt','Pageindex':0,'pagesize':1000,'sort':'fbt:asc','date':day.replace('-',''),'_':''},timeout=12)
def batch(cs):
    u='https://qt.gtimg.cn/q='+','.join(symbol(c) for c in cs)
    try:
        with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=12) as f:b=f.read()
        s=b.decode('gb18030',errors='replace');fs={k:v.split('~') for k,v in re.findall(r'v_([a-zA-Z0-9]+)="([^"]*)";',s)}
        return {'ok':True,'source':u,'retrieved_at':stamp(),'provider_fields':fs,'raw_text':s}
    except Exception as e:return {'ok':False,'source':u,'retrieved_at':stamp(),'error':repr(e)}
def prior():return json.loads(gzip.decompress((ROOT/'docs/research/combined-pair-20261028-evidence.json.gz').read_bytes()))
def universe():
    prev=prior();market=load(ROOT/'docs/research/market-review-2026-10-29-evidence.json')
    codes=set(prev['daily_histories'])|{r['code'] for r in market['broad_pool']}
    for name in ['low_position_samples','recommendations']:
        codes.update(r['code'] for r in load(ROOT/f'backend/data/{name}.json')['items'])
    for r in load(ROOT/'backend/data/volume_price_samples.json')['items']:
        codes.update(s['code'] for s in r.get('samples',[]) if isinstance(s,dict) and s.get('code'))
    for r in records('lhb').values():
        codes.update(s['SECURITY_CODE'] for s in (r.get('payload',{}).get('result') or {}).get('data') or [])
    for r in records('pools').values():codes.update(s['c'] for s in (r.get('payload',{}).get('data') or {}).get('pool') or [])
    codes.update(['600118','300900','600643','002275','603279','603382','002149','000678','001219','002708'])
    return codes
def quotes():
    qs={q['code']:q for r in records('sina').values() for q in r.get('payload',[]) if isinstance(r.get('payload'),list)}
    return qs
def bulk():
    wanted=universe()
    for c,q in quotes().items():
        if not c.startswith(('00','60')) or 'ST' in q['name'].upper() or '退' in q['name']:continue
        ref=float(q.get('settlement') or 0);hi=float(q.get('high') or 0);lo=float(q.get('low') or 0)
        if ref and (hi/ref>=1.095 or 0<lo/ref<=.905):wanted.add(c)
    wanted=sorted(wanted);batches={str(n//35):wanted[n:n+35] for n in range(0,len(wanted),35)}
    run('bulk',batches,lambda k:batch(batches[k]),workers=3)
    save(CACHE/'requested-bulk.json',wanted)
    prev=prior();bs=records('bulk');fs={s:(f,r) for r in bs.values() for s,f in r.get('provider_fields',{}).items() if len(f)>48}
    focused=load(ROOT/'tmp/shadow-inputs-20261029.json')
    for c in universe():
        if c in focused['daily_histories'] and focused['daily_histories'][c].get('ok'):
            save(CACHE/'daily'/(c+'.json'),focused['daily_histories'][c]);continue
        old=prev['daily_histories'].get(c,{});bars=[b for b in old.get('bars',[]) if b['date']<=PREV]
        f,r=fs.get(symbol(c),(None,None))
        if not bars or not f or not f[30].startswith('20261029'):continue
        if not all(float(f[n] or 0)>0 for n in [3,5,6,33,34]):continue
        bar={'date':T,'open':float(f[5]),'close':float(f[3]),'high':float(f[33]),'low':float(f[34]),'volume':float(f[6])}
        assert bar['low']<=bar['open']<=bar['high'] and bar['low']<=bar['close']<=bar['high']
        save(CACHE/'daily'/(c+'.json'),{'ok':True,'source':r['source'],'retrieved_at':r['retrieved_at'],'bars':bars+[bar],
            'latest_date':T,'adjustment':'unadjusted','volume_unit':'provider_lots',
            'history_source_archive':'docs/research/combined-pair-20261028-evidence.json.gz','original_history_source':old['source'],
            'history_last_date':bars[-1]['date'],'current_bar_source':'dated Tencent fields 3/5/6/33/34, not estimated',
            'provider_timestamp':f[30],'prior_unadjusted_close_vs_current_settlement_difference':round(bars[-1]['close']-float(f[4]),5),
            'volume_field_crosscheck':'fields 6/36 equal dated direct daily volume for all eight separately fetched shadow/control series'})
def new_histories():
    missing=sorted(c for c in universe() if not (CACHE/'daily'/(c+'.json')).exists())
    # Known delisting is not silently dropped or assigned a zero return.
    run('daily',missing,daily,workers=4)
def focus():
    keys=['000678','001219','002708','002943','603382','600643','002275','603279','300900','600728','002149','600118','001379','605179','600501','603703','600715','000530','002086','002172','001400','600838','603028','603528']
    rows=(records('lhb')[T].get('payload',{}).get('result') or {}).get('data') or []
    return [c for c in keys if c in {r['SECURITY_CODE'] for r in rows}]
def minutes():
    m=load(ROOT/'docs/research/market-review-2026-10-29-evidence.json');codes={s['code'] for s in m['deep_pool']+m['previous_pool_validation']}
    codes.update(s['code'] for s in load(ROOT/'backend/data/low_position_samples.json')['items']);codes.update(focus())
    focused=load(ROOT/'tmp/shadow-inputs-20261029.json')
    for c,r in focused['minute_price_points'].items():save(CACHE/'minute'/(c+'.json'),r)
    codes.update(focused['minute_price_points']);run('minute',sorted(codes),minute,workers=4)
def assemble():
    out={'market_date':T,'previous_session':PREV,'planned_entry_date':'2026-10-30','actual_started_at_utc':START,
        'reused_market_report':'market-review-20261029-close-v1','reused_market_evidence':'docs/research/market-review-2026-10-29-evidence.json',
        'sina_pages':records('sina'),'quotes':quotes(),'lhb_lists':records('lhb'),'limit_up_pools':records('pools'),
        'daily_histories':records('daily'),'seat_queries':records('seats'),'minute_price_points':records('minute'),
        'actual_collection_completed_at_utc':stamp(),'collection_method':'checkpointed raw responses; published T28 unadjusted histories extended by independently dated T29 OHLCV quotes',
        'initial_transport_failure':{'first_collector_started_after':START,'result_file_created':False,'resume_error':'exec-server transport disconnected; recovery timed out; original process no longer running','prices_from_interrupted_process_used':False}}
    save(ROOT/'tmp/combined-20261029-raw.json',out)
    bs=list(records('bulk').values());fs={s:f for r in bs for s,f in r.get('provider_fields',{}).items() if len(f)>48}
    save(ROOT/'tmp/combined-20261029-quote-upper-check.json',{'market_date':T,'source':'See original batch URLs in batches','requested_codes':load(CACHE/'requested-bulk.json'),
         'batches':bs,'provider_fields':fs,'upper_field':47,'lower_field':48,'timestamp_field':30,'interpretation':'dated provider limits; not queue fills'})
    save(ROOT/'tmp/combined-20261029-extension.json',{'daily_histories':{},'minute_price_points':{},'seat_queries':{},'limit_up_pools':{},'transport_failure_recorded':True})
    print(json.dumps({'raw_quotes':len(out['quotes']),'daily_n':len(out['daily_histories']),'daily_ok':sum(r.get('ok',False) for r in out['daily_histories'].values()),'daily_missing_symbols':sorted(universe()-set(out['daily_histories'])),
          'minute_n':len(out['minute_price_points']),'seat_n':len(out['seat_queries']),'focus_codes':focus(),'sina_errors':[k for k,r in out['sina_pages'].items() if not r.get('ok')]},ensure_ascii=False))
if __name__=='__main__':
    phase=sys.argv[1]
    if phase=='quotes':run('sina',range(1,61),lambda n:page(int(n)))
    elif phase=='disclosures':
        run('lhb',['2026-10-27',PREV,T],lhb,workers=3);run('pools',['2026-10-27',PREV,T],pool,workers=3)
    elif phase=='bulk':bulk()
    elif phase=='histories':new_histories()
    elif phase=='minutes':minutes()
    elif phase=='seats':run('seats',[c+':'+s for c in focus() for s in ['BUY','SELL']],seat)
    elif phase=='assemble':assemble()
    else:raise ValueError(phase)
