"""Checkpoint public T30 data; collection never constitutes analyst approval."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
import copy, gzip, json, re, sys
import collect_combined_20261029 as provider
ROOT=Path(__file__).resolve().parents[1]
T='2026-10-30'; PREV='2026-10-29'; D='2026-11-02'
START='2026-10-30T09:38:34+00:00'
provider.T=T; provider.PREV=PREV; provider.START=START
get,stamp,daily,minute,lhb,seat,symbol=provider.get,provider.stamp,provider.daily,provider.minute,provider.lhb,provider.seat,provider.symbol
CACHE=ROOT/'tmp/t30-inputs'
def load(p):return json.loads(p.read_text())
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix('.writing');temp.write_text(json.dumps(d,ensure_ascii=False,allow_nan=False));temp.replace(p)
def records(group):return {p.stem:load(p) for p in (CACHE/group).glob('*.json')}
def run(group,keys,fn,workers=4):
    keys=[str(k) for k in keys]
    pending=[k for k in keys if not (CACHE/group/(k+'.json')).exists()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(fn,k):k for k in pending}
        for future in as_completed(jobs):
            k=jobs[future]
            try:r=future.result()
            except Exception as e:r={'ok':False,'retrieved_at':stamp(),'error':repr(e)}
            save(CACHE/group/(k+'.json'),r)
    rs=records(group)
    print(json.dumps({'phase':group,'requested':len(keys),'new':len(pending),'saved':len(rs),'ok':sum(r.get('ok',False) for r in rs.values())}),flush=True)
def previous():return json.loads(gzip.decompress((ROOT/'docs/research/combined-pair-20261029-evidence.json.gz').read_bytes()))
def quotes():return {q['code']:q for r in records('sina').values() for q in (r.get('payload',[]) if isinstance(r.get('payload'),list) else [])}
def select_entry_pool():
    from collect_market_review_20261022 import enrich_bar,f
    valid=[enrich_bar(q) for q in quotes().values() if f(q.get('trade'))>0 and f(q.get('settlement'))>0]
    # Frozen historical helper prioritizes liquid activity only; it is neither a
    # calibrated return score nor the final shadow/official ranking.
    ranked=sorted(valid,key=lambda q:q['score'],reverse=True)
    entry=[q for q in ranked if f(q.get('amount'))>=80000000 and f(q.get('turnoverratio'))>=1][:160]
    save(CACHE/'entry-pool.json',{'market_date':T,'selection_version':'historical_liquid_activity_entry_helper','not_validated_return_score':True,'valid_count':len(valid),'items':entry})
    return entry
def pool(day):return get('https://push2ex.eastmoney.com/getTopicZTPool',{'ut':'7eea3edcaed734bea9cbfc24409ed989','dpt':'wz.ztzt','Pageindex':0,'pagesize':1000,'sort':'fbt:asc','date':day.replace('-',''),'_':''},timeout=15)
def batch(cs,explicit=False):
    u='https://qt.gtimg.cn/q='+','.join(cs if explicit else [symbol(c) for c in cs])
    try:
        with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=15) as f:b=f.read()
        raw=b.decode('gb18030',errors='replace')
        fields={k:v.split('~') for k,v in re.findall(r'v_([a-zA-Z0-9]+)="([^"]*)";',raw)}
        return {'ok':True,'source':u,'retrieved_at':stamp(),'provider_fields':fields,'raw_text':raw}
    except Exception as e:return {'ok':False,'source':u,'retrieved_at':stamp(),'error':repr(e)}
def universe():
    prev=previous(); codes=set(prev['daily_histories'])|{q['code'] for q in select_entry_pool()}
    for key in ['low_position_samples','recommendations']:
        codes.update(s['code'] for s in load(ROOT/f'backend/data/{key}.json')['items'])
    for s in load(ROOT/'backend/data/volume_price_samples.json')['items']:
        codes.update(r['code'] for r in s.get('samples',[]) if isinstance(r,dict) and r.get('code'))
    for r in records('lhb').values():codes.update(s['SECURITY_CODE'] for s in (r.get('payload',{}).get('result') or {}).get('data') or [])
    for r in records('pools').values():codes.update(s['c'] for s in (r.get('payload',{}).get('data') or {}).get('pool') or [])
    for path in (ROOT/'docs/research').glob('shadow-experiments-202610*-v1.json'):
        exp=load(path)
        codes.update(s['code'] for key in ['signals','controls'] for s in exp.get(key,[]))
    codes.update(['000999','600329','600436','300900','600501'])
    return {c for c in codes if len(c)==6 and not c.startswith(('200','900'))}
def bulk():
    wanted=universe()
    for c,q in quotes().items():
        if not c.startswith(('00','60')) or 'ST' in q['name'].upper() or '退' in q['name']:continue
        ref=float(q.get('settlement') or 0);hi=float(q.get('high') or 0);lo=float(q.get('low') or 0)
        if ref and (hi/ref>=1.095 or 0<lo/ref<=.905):wanted.add(c)
    wanted=sorted(wanted);batches={str(i//35):wanted[i:i+35] for i in range(0,len(wanted),35)}
    run('bulk',batches,lambda k:batch(batches[k]),workers=3)
    save(CACHE/'requested-bulk.json',wanted)
    prev=previous(); fs={s:(f,r) for r in records('bulk').values() for s,f in r.get('provider_fields',{}).items() if len(f)>48}
    for c in universe():
        old=prev['daily_histories'].get(c,{})
        bars=[b for b in old.get('bars',[]) if b['date']<=PREV]
        f,r=fs.get(symbol(c),(None,None))
        if not bars or bars[-1]['date']!=PREV or not f or not f[30].startswith('20261030'):continue
        if not all(float(f[n] or 0)>0 for n in [3,5,6,33,34]):continue
        bar={'date':T,'open':float(f[5]),'close':float(f[3]),'high':float(f[33]),'low':float(f[34]),'volume':float(f[6])}
        if not bar['low']<=bar['open']<=bar['high'] or not bar['low']<=bar['close']<=bar['high']:continue
        save(CACHE/'daily'/(c+'.json'),{'ok':True,'source':r['source'],'retrieved_at':r['retrieved_at'],'bars':bars+[bar],
            'latest_date':T,'adjustment':'unadjusted','volume_unit':'provider_lots',
            'history_source_archive':'docs/research/combined-pair-20261029-evidence.json.gz','original_history_source':old['source'],
            'history_last_date':PREV,'current_bar_source':'date-verified Tencent fields 3/5/6/33/34, not an estimate',
            'provider_timestamp':f[30],'prior_close_vs_settlement_difference':round(bars[-1]['close']-float(f[4]),6)})
def direct(c):return daily(c)
def histories():run('daily',sorted(universe()),daily,workers=4)
def first_shadows():
    codes=set()
    for path in (ROOT/'docs/research').glob('shadow-experiments-202610*-v1.json'):
        exp=load(path)
        codes.update(s['code'] for key in ['signals','controls'] for s in exp.get(key,[]))
    codes.update(['000999','600329','600436','300900','600501','000678','001219','002708'])
    run('direct-shadow',sorted(codes),daily,workers=4)
    run('minute',sorted(codes),minute,workers=4)
def benchmark(s):
    r=get('https://web.ifzq.gtimg.cn/appstock/app/kline/kline',{'param':s+',day,,,180'})
    if r.get('ok'):
        b=r['payload'].get('data',{}).get(s,{}).get('day',[])
        r['bars']=[{'date':x[0],'open':float(x[1]),'close':float(x[2]),'high':float(x[3]),'low':float(x[4]),'volume':float(x[5])} for x in b if x[0]<=T]
        r['ok']=bool(r['bars'] and r['bars'][-1]['date']==T)
    return r
def basic():
    run('sina',range(1,61),lambda n:provider.page(int(n)),workers=4)
def disclosures():
    run('lhb',['2026-10-28',PREV,T],lhb,workers=3)
    run('pools',['2026-10-28',PREV,T],pool,workers=3)
    run('benchmark',['sh000300','sh000001','sz399001','sz399006','sh000688'],benchmark,workers=3)
    save(CACHE/'index-quotes.json',batch(['sh000300','sh000001','sz399001','sz399006','sh000688'],explicit=True))
def main():
    phase=sys.argv[1]
    {'quotes':basic,'disclosures':disclosures,'shadows':first_shadows,'bulk':bulk,'histories':histories}[phase]()
if __name__=='__main__':main()
