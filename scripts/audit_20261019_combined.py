#!/usr/bin/env python3
"""Recompute unpublished derived fields and archive time-bounded issuer facts."""
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import collect_20261019_combined as c
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT/'docs/research/combined-pair-2026-10-19-evidence.json'


def main():
    e = load_evidence(PATH)
    market = c.load('docs/research/market-review-2026-10-19-evidence.json')
    raw, qfq, minutes = (e[k] for k in ('raw_daily_histories','qfq_daily_histories','minute_price_paths'))
    offline='--offline' in sys.argv
    retry = [] if offline else [code for code, error in e['provider_failures']['qfq'].items() if 'URLError' in error]
    if retry:
        recovered, still_failed = c.h.fetch_parallel(retry,lambda code:c.h.daily_bars(code,True),workers=3)
        qfq.update(recovered)
        e['qfq_retry_audit']={'retried':retry,'recovered':list(recovered),'still_failed':still_failed,
                              'recorded_at':datetime.now(timezone.utc).isoformat()}
        # Original provider failures remain an immutable description of the first attempt.
    previous = c.load('backend/data/volume_price_samples.json')['items'][-1]['samples']
    pmap = {s['code']:s for s in previous}
    broad = c.enrich(market['broad_pool'],qfq,raw,minutes)
    dc = {s['code'] for s in market['deep_pool']}
    deep = [s for s in broad if s['code'] in dc]
    for s in deep:
        if s['code'] in pmap:s['turnover_change_pct_points']=round(s['turnover_pct']-pmap[s['code']]['turnover_pct'],3)
    lowdoc = c.load('backend/data/low_position_samples.json')
    lowmap = {r['id']:r for r in lowdoc['items']}
    for observation in e['low_position']['existing_validations']:
        sample=lowmap[observation['origin_cohort_id']]
        after=[b for b in raw.get(sample['code'],[]) if sample['date']<b['date']<=c.T]
        observation['legacy_signal_day_inclusive_mfe_pct']=observation['path_mfe_pct']
        observation['legacy_signal_day_inclusive_mae_pct']=observation['path_mae_pct']
        observation['path_mfe_pct']=c.h.pct(max(b['high'] for b in after),sample['day0_close']) if after else None
        observation['path_mae_pct']=c.h.pct(min(b['low'] for b in after),sample['day0_close']) if after else None
        invalid=sample.get('invalid_close_below')
        broken=[b['date'] for b in after if invalid is not None and b['close']<invalid]
        observation['first_verified_close_below_original_invalid']=broken[0] if broken else None
        observation['ever_verified_close_below_original_invalid']=bool(broken)
        observation['path_definition']='after frozen reference close; exclude earlier intraday range on signal day'
        observation['calculation_version']='low_price_observation_v2_20261019'
    lownew = c.h.choose_new_low(broad,{r['code'] for r in lowdoc['items']})
    missing = [r['code'] for r in lownew if not minutes.get(r['code'],{}).get(c.COMPACT)]
    if missing:
        extra, errors = c.h.fetch_parallel(missing,c.h.five_day_minutes,workers=3)
        minutes.update(extra); e['provider_failures']['minutes'].update(errors)
        broad = c.enrich(market['broad_pool'],qfq,raw,minutes)
        deep = [s for s in broad if s['code'] in dc]
        for s in deep:
            if s['code'] in pmap:s['turnover_change_pct_points']=round(s['turnover_pct']-pmap[s['code']]['turnover_pct'],3)
        lownew = c.h.choose_new_low(broad,{r['code'] for r in lowdoc['items']})
    e['volume_price']['broad_samples']=broad
    e['volume_price']['broad_verified']=len(broad)
    e['volume_price']['deep_samples']=deep
    e['low_position']['new_candidates']=lownew
    # Statistics retain the frozen T-1 categories; never classify them by the outcome.
    groups=defaultdict(list)
    for r in e['volume_price']['previous_validations']:
        groups[pmap[r['code']]['structure']].append(r)
    e['volume_price']['previous_by_frozen_structure']={k:c.stats(v) for k,v in groups.items()}
    secondary=[]
    for p in previous:
        code=p['code']; bs=qfq.get(code,[]); cur=c.h.by_date(bs,c.T)
        if not cur or len(bs)<21:continue
        prev=bs[-2]; vol=c.h.volume_mean(bs,20)
        secondary.append({'code':code,'name':p['name'],'date':c.T,
                          'change_pct':c.h.pct(cur['close'],prev['close']),
                          'volume_vs_previous_session':round(cur['volume']/prev['volume'],3) if prev['volume'] else None,
                          'rvol20':round(cur['volume']/vol,3) if vol else None,
                          'clv':round((cur['close']-cur['low'])/(cur['high']-cur['low']),3) if cur['high']>cur['low'] else None,
                          'role':'validation-day diagnostic, not a newly frozen recommendation'})
    e['volume_price']['prior_pool_validation_day_structures']=secondary
    prior=[]
    for rec in c.load('backend/data/recommendations.json')['items']:
        if rec.get('strategy')!='combined_limitup_watch':continue
        bs=raw.get(rec['code'],[]); ref=float(rec['reference_price']); aft=[b for b in bs if rec['date']<b['date']<=c.T]
        cur=c.h.by_date(bs,c.T)
        if not cur:continue
        horizons=[]
        for n in (1,3,5,10,20,30):
            if len(aft)<n:continue
            node=aft[n-1]; path=aft[:n]
            horizons.append({'trading_horizon':n,'date':node['date'],'close':node['close'],
                             'close_return_pct':c.h.pct(node['close'],ref),
                             'mfe_price_observation_pct':c.h.pct(max(b['high'] for b in path),ref),
                             'mae_price_observation_pct':c.h.pct(min(b['low'] for b in path),ref)})
        prior.append({'recommendation_id':rec['id'],'code':rec['code'],'name':rec['name'],'reference_date':rec['date'],
                      'reference_price':ref,'as_of':c.T,'ohlc':cur,'horizons':horizons,
                      'price_return_to_T_pct':c.h.pct(cur['close'],ref),
                      'executed_trade':False,'executable_net_return_pct':None})
    e['combined_horizon_validation']=prior
    zd=next(r for r in prior if r['code']=='000887' and r['reference_date']==c.PREV)
    assert zd['ohlc']['open']<17.40
    zd['trigger_status']='not_triggered_open_below_frozen_lower_bound'
    zd['entry_fill_status']='no_strategy_fill'
    zd['reason']='10月19日开17.12低于冻结开盘下界17.40；无需倒推后续高低顺序即可否决，全天高17.18亦低于17.78收复条件。'
    # Exact six-digit issuer checks are independent of noisy text-search hit totals.
    facts=e.get('issuer_primary_pdf_checks',[]) if offline else []
    for code, node in ([] if offline else e.get('issuer_notices',{}).items()):
        for item in node.get('announcements',[])[:2]:
            url='https://static.cninfo.com.cn/'+item['adjunctUrl']
            try:
                pdf=c.h.request_bytes(url,timeout=25)
                text=subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
                facts.append({'code':code,'title':item['announcementTitle'],'source':url,
                              'sha256':hashlib.sha256(pdf).hexdigest(),'bytes':len(pdf),
                              'text_excerpt':text[:3800],'verified_at':datetime.now(timezone.utc).isoformat()})
            except Exception as exc:facts.append({'code':code,'source':url,'error':f'{type(exc).__name__}:{exc}'})
    e['issuer_primary_pdf_checks']=facts
    e['audit_completed_at_utc']=datetime.now(timezone.utc).isoformat()
    PATH.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'broad':len(broad),'deep':len(deep),'new_low':[(s['code'],s['name']) for s in lownew],
                      'prior_combined':zd,'pdf_checks':[(f['code'],f.get('title'),f.get('error')) for f in facts],
                      'frozen_structure_stats':e['volume_price']['previous_by_frozen_structure']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
