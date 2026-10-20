#!/usr/bin/env python3
"""Finish pre-publication crosschecks, fixed-cohort statistics and raw horizons."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import collect_20261020_combined as c
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'docs/research/combined-pair-2026-10-20-evidence.json'


def backup_history(key):
    code, adjusted=key
    endpoint='https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get' if adjusted else 'https://web.ifzq.gtimg.cn/appstock/app/kline/kline'
    param=c.sym(code)+',day,,,180'+(',qfq' if adjusted else '')
    url=endpoint+'?param='+param
    req=urllib.request.Request(url,headers={'User-Agent':c.h.UA,'Referer':'https://gu.qq.com/'})
    with urllib.request.urlopen(req,timeout=20) as response:j=json.load(response)
    node=(j.get('data') or {}).get(c.sym(code)) or {}
    rs=node.get('qfqday' if adjusted else 'day') or []
    bs=[{'date':str(r[0]),'open':float(r[1]),'close':float(r[2]),'high':float(r[3]),'low':float(r[4]),'volume':float(r[5])}
        for r in rs if len(r)>=6 and str(r[0])<=c.T]
    if not bs or bs[-1]['date']!=c.T:raise ValueError('missing_target_or_wrong_adjustment_key')
    return {'source':url,'adjustment':'qfq' if adjusted else 'none','bars':bs}


def sina_quotes(codes):
    url = 'https://hq.sinajs.cn/list=' + ','.join(c.sym(code) for code in codes)
    req = urllib.request.Request(url, headers={'User-Agent': c.h.UA, 'Referer': 'https://finance.sina.com.cn/'})
    with urllib.request.urlopen(req, timeout=22) as r:
        body = r.read().decode('gb18030', errors='replace')
    rows = {}
    for symbol, text in re.findall(r'var hq_str_(\w+)="([^"]*)"', body):
        f = text.split(',')
        if len(f) < 32 or f[30] != c.T:
            continue
        rows[symbol[2:]] = {'code': symbol[2:], 'name': f[0], 'open': float(f[1]), 'previous_close': float(f[2]),
                            'close': float(f[3]), 'high': float(f[4]), 'low': float(f[5]), 'volume': float(f[8]),
                            'amount_cny': float(f[9]), 'quote_date': f[30], 'quote_time': f[31], 'source': url}
    return rows


def latest_notices(pair):
    code,name=pair
    now=datetime.now(timezone.utc)
    end=now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    p={'pageNum':1,'pageSize':50,'column':'szse' if code.startswith(('00','30')) else 'sse',
       'tabName':'fulltext','seDate':'2026-08-01~'+end,'sortName':'time','sortType':'desc','isHLtitle':'true','searchkey':name}
    url='https://www.cninfo.com.cn/new/hisAnnouncement/query'
    req=urllib.request.Request(url,data=urllib.parse.urlencode(p).encode(),headers={'User-Agent':c.h.UA,'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req,timeout=25) as response:j=json.load(response)
    return {'code':code,'name':name,'source':url,'query':p,'retrieved_at':now.isoformat(),
            'announcements':[{k:r.get(k) for k in ['secCode','announcementTitle','announcementTime','adjunctUrl']}
                             for r in j.get('announcements',[]) if r.get('secCode')==code and float(r.get('announcementTime') or 0)<=now.timestamp()*1000]}


def primary_pdf(key):
    code,r=key
    url='https://static.cninfo.com.cn/'+r['adjunctUrl']
    pdf=c.request(url,timeout=22)
    text=subprocess.run(['pdftotext','-','-'],input=pdf,check=True,capture_output=True).stdout.decode()
    return {'code':code,'title':r['announcementTitle'],'source':url,'sha256':hashlib.sha256(pdf).hexdigest(),'bytes':len(pdf),
            'text_excerpt':text[:9000],'verified_at':datetime.now(timezone.utc).isoformat()}


def main():
    e = load_evidence(PATH)
    market = c.load('docs/research/market-review-2026-10-20-evidence.json')
    raw, qfq, paths = (e[k] for k in ('raw_daily_histories', 'qfq_daily_histories', 'minute_price_paths'))
    missing=[(code,adjusted) for adjusted,name in [(False,'raw'),(True,'qfq')] for code in e['provider_failures'][name]]
    recovered,still_failed=c.parallel(missing,backup_history,workers=8,label='public_backup_histories')
    for (code,adjusted),r in recovered.items():
        (qfq if adjusted else raw)[code]=r['bars']
    e['daily_recovery_audit']={'recorded_at':datetime.now(timezone.utc).isoformat(),
        'recovered':[{'code':key[0],'adjusted':key[1],'source':r['source'],'bars':len(r['bars'])} for key,r in recovered.items()],
        'still_failed':{str(k):v for k,v in still_failed.items()},'original_errors_preserved':True}
    codes = [r['code'] for r in market['broad_pool']]
    chunks = [codes[i:i+20] for i in range(0, len(codes), 20)]
    fetched, errors = c.parallel(list(range(len(chunks))), lambda i: sina_quotes(chunks[i]), workers=3)
    sina = {code: r for node in fetched.values() for code, r in node.items()}
    e['sina_same_day_quotes'], e['provider_failures']['sina_crosscheck'] = sina, {str(k): v for k,v in errors.items()}
    deepmap = {s['code']: s for s in market['deep_pool']}
    quotes = []
    for s in market['broad_pool']:
        quote = {**s, **deepmap.get(s['code'], {})}
        if s['code'] in sina:
            r = sina[s['code']]
            quote.update({'open': r['open'], 'high': r['high'], 'low': r['low'], 'trade': r['close'], 'settlement': r['previous_close']})
        quotes.append(quote)
    broad = c.enrich(quotes, qfq, raw, paths)
    previous = c.load('backend/data/volume_price_samples.json')['items'][-1]['samples']
    previous_map = {s['code']: s for s in previous}
    for s in broad:
        if s['code'] in previous_map:
            s['turnover_change_pct_points'] = round(s['turnover_pct'] - previous_map[s['code']]['turnover_pct'], 3)
        if (s['code'],False) in recovered:s['daily_source']=recovered[(s['code'],False)]['source']
        if (s['code'],True) in recovered:s['qfq_daily_source']=recovered[(s['code'],True)]['source']
    e['volume_price']['broad_samples'], e['volume_price']['broad_verified'] = broad, len(broad)
    e['volume_price']['deep_samples'] = [s for s in broad if s['code'] in deepmap]
    e['low_position']['new_candidates'] = c.h.choose_new_low(broad, {s['code'] for s in c.load('backend/data/low_position_samples.json')['items']})
    need_minutes=[s['code'] for s in e['low_position']['new_candidates'] if s['code'] not in paths]
    extra,minute_errors=c.parallel(need_minutes,c.minutes,workers=3,label='new_low_minute_paths')
    paths.update(extra);e['provider_failures']['minutes'].update(minute_errors)
    # Re-enrich only after recovering any newly eligible sample's price path.
    if extra:
        broad=c.enrich(quotes,qfq,raw,paths)
        for s in broad:
            if s['code'] in previous_map:s['turnover_change_pct_points']=round(s['turnover_pct']-previous_map[s['code']]['turnover_pct'],3)
            if (s['code'],False) in recovered:s['daily_source']=recovered[(s['code'],False)]['source']
            if (s['code'],True) in recovered:s['qfq_daily_source']=recovered[(s['code'],True)]['source']
        e['volume_price']['broad_samples'],e['volume_price']['broad_verified']=broad,len(broad)
        e['volume_price']['deep_samples']=[s for s in broad if s['code'] in deepmap]
        e['low_position']['new_candidates']=c.h.choose_new_low(broad,{s['code'] for s in c.load('backend/data/low_position_samples.json')['items']})
    vv=c.previous_helpers.validate([s['code'] for s in previous],raw,paths)
    e['volume_price']['previous_validations'],e['volume_price']['previous_statistics']=vv,c.previous_helpers.stats(vv)
    groups=defaultdict(list)
    for v in vv:groups[previous_map[v['code']]['structure']].append(v)
    e['volume_price']['previous_by_frozen_structure']={k:c.previous_helpers.stats(rows) for k,rows in groups.items()}
    olddragon=load_evidence(ROOT/'docs/research/combined-pair-2026-10-19-evidence.json')['dragon_tiger']['selected_observations']
    dv=c.previous_helpers.validate([s['code'] for s in olddragon],raw,paths)
    e['dragon_tiger']['previous_validations'],e['dragon_tiger']['previous_statistics']=dv,c.previous_helpers.stats(dv)
    lowdoc=c.load('backend/data/low_position_samples.json')
    lowvals=c.h.low_validations(lowdoc['items'],raw)
    lm={s['id']:s for s in lowdoc['items']}
    for v in lowvals:
        if not v.get('origin_cohort_id'):continue
        s=lm[v['origin_cohort_id']];aft=[b for b in raw[s['code']] if s['date']<b['date']<=c.T]
        v['path_mfe_pct']=c.h.pct(max(b['high'] for b in aft),s['day0_close']) if aft else None
        v['path_mae_pct']=c.h.pct(min(b['low'] for b in aft),s['day0_close']) if aft else None
        broken=[b['date'] for b in aft if s.get('invalid_close_below') is not None and b['close']<s['invalid_close_below']]
        v.update({'report_ids':['low-position-20261020-close-v1'],'first_verified_close_below_original_invalid':broken[0] if broken else None,
                  'ever_verified_close_below_original_invalid':bool(broken),'path_definition':'after frozen reference close; exclude signal-day range',
                  'calculation_version':'low_price_observation_v2_20261019'})
    e['low_position']['existing_validations']=lowvals
    e['price_crosscheck_summary'] = {'sina_same_day_quotes': len(sina), 'full_ohlc_compared': sum(s['daily_crosscheck']['max_ohlc_difference'] is not None for s in broad),
        'full_ohlc_exact': sum(s['daily_crosscheck']['max_ohlc_difference'] == 0 for s in broad),
        'differences': [{'code':s['code'],**s['daily_crosscheck']} for s in broad if s['daily_crosscheck']['max_available_field_difference'] != 0]}
    prior = []
    index = raw.get('sh000001', [])
    for rec in c.load('backend/data/recommendations.json')['items']:
        if rec.get('strategy') != 'combined_limitup_watch':
            continue
        bs = raw.get(rec['code'], [])
        cur = c.h.by_date(bs, c.T)
        if not cur:
            prior.append({'recommendation_id':rec['id'],'code':rec['code'],'status':'missing_current_daily'});continue
        ref = float(rec['reference_price'])
        aft = [b for b in bs if rec['date'] < b['date'] <= c.T]
        ibase = c.h.by_date(index, rec['date'])
        hs = []
        for n in (1,3,5,10,20,30):
            if len(aft) < n:continue
            node, path = aft[n-1], aft[:n]
            inode = c.h.by_date(index, node['date'])
            br = c.h.pct(inode['close'], ibase['close']) if ibase and inode else None
            rr = c.h.pct(node['close'], ref)
            hs.append({'trading_horizon':n,'date':node['date'],'close':node['close'],'close_return_pct':rr,
                       'mfe_price_observation_pct':c.h.pct(max(b['high'] for b in path),ref),
                       'mae_price_observation_pct':c.h.pct(min(b['low'] for b in path),ref),
                       'benchmark':'Shanghai Composite same raw-close dates','benchmark_return_pct':br,
                       'excess_price_observation_pct_points':round(rr-br,3) if br is not None else None})
        prior.append({'recommendation_id':rec['id'],'code':rec['code'],'name':rec['name'],'reference_date':rec['date'],
                      'reference_price':ref,'as_of':c.T,'ohlc':cur,'horizons':hs,'price_return_to_T_pct':c.h.pct(cur['close'],ref),
                      'executed_trade':False,'executable_net_return_pct':None,
                      'trigger_status':'original_day_trigger_or_nontrigger_status_unchanged_not_reactivated_today'})
    e['combined_horizon_validation'] = prior
    # Preserve both completed forward cohorts under v4; repeated codes on different signal dates are separate observations.
    vdoc = c.load('backend/data/volume_price_samples.json')
    matured = [r for r in vdoc['items'] if r.get('rule_version') == 'volume_price_close_v4' and r.get('kind') == 'full_forward_price_validation']
    allvalid = [v for r in matured for v in r.get('full_pool_validations', [])] + e['volume_price']['previous_validations']
    e['volume_price']['cumulative_v4_next_day_price_statistics'] = c.previous_helpers.stats(allvalid)
    e['volume_price']['cumulative_v4_period'] = {'signal_start':'2026-10-16','signal_end':'2026-10-19','validation_end':c.T,
            'unit':'frozen cohort plus code plus next-session observation; not completed trades','new_T20_cohort_mature':False}
    diagnostics=[]
    for s in previous:
        bs = qfq.get(s['code'],[])
        if len(bs)<21:continue
        cur=bs[-1]; prev=bs[-2]
        diagnostics.append({'code':s['code'],'name':s['name'],'frozen_previous_structure':s['structure'],
            'date':c.T,'change_pct':c.h.pct(cur['close'],prev['close']),
            'volume_vs_previous_session':round(cur['volume']/prev['volume'],3) if prev['volume'] else None,
            'rvol20':round(cur['volume']/c.h.volume_mean(bs,20),3) if c.h.volume_mean(bs,20) else None,
            'clv':round((cur['close']-cur['low'])/(cur['high']-cur['low']),3) if cur['high']>cur['low'] else None,
            'role':'post-signal diagnostic, not a hindsight recommendation or changed frozen category'})
    e['volume_price']['prior_pool_validation_day_structures']=diagnostics
    for s in e['dragon_tiger']['selected_observations']:
        union={(str(r.get('OPERATEDEPT_CODE')),float(r.get('BUY') or 0),float(r.get('SELL') or 0),str(r.get('TRADE_ID'))):r
               for r in s['buy_seats_em']+s['sell_seats_em']}
        labels={}
        for label, predicate in [('institution_channel',lambda n:'机构专用' in n),('stock_connect_channel',lambda n:'股通专用' in n)]:
            rs=[r for r in union.values() if predicate(r.get('OPERATEDEPT_NAME',''))]
            labels[label]={'disclosed_channel_count':len(rs),'buy_cny':sum(float(r.get('BUY') or 0) for r in rs),
                           'sell_cny':sum(float(r.get('SELL') or 0) for r in rs)}
            labels[label]['net_cny']=labels[label]['buy_cny']-labels[label]['sell_cny']
        s['channel_group_flows']=labels
    prior_e=load_evidence(ROOT/'docs/research/combined-pair-2026-10-19-evidence.json')
    validated={r['code']:r for r in e['dragon_tiger']['previous_validations']}
    portraits=defaultdict(list)
    for s in prior_e['dragon_tiger']['selected_observations']:
        v=validated.get(s['code'],{})
        if 'close_return_pct' not in v:continue
        seen=set()
        for r in s['buy_seats_em']:
            key=(str(r.get('OPERATEDEPT_CODE')),r.get('OPERATEDEPT_NAME',''))
            if key in seen:continue
            seen.add(key)
            portraits[key].append({'signal_date':c.PREV,'code':s['code'],'selected_period_reason':s['selected_period_reason'],
                                   'next_day_close_price_observation_pct':v['close_return_pct'],
                                   'not_account_hold_or_sell_evidence':True})
    e['dragon_tiger']['public_channel_forward_profiles']=[{'public_channel_code':key[0],'public_label':key[1],
        'observations':rows,'N':len(rows),'mean_next_close_price_pct':c.h.mean([r['next_day_close_price_observation_pct'] for r in rows]),
        'holding_period_inference':None,'account_identity_confirmed':False,'strategy_win_rate':None}
        for key,rows in portraits.items()]
    lowmap={r['id']:r for r in c.load('backend/data/low_position_samples.json')['items']}
    for v in e['low_position']['existing_validations']:
        if not v.get('origin_cohort_id'):continue
        s=lowmap[v['origin_cohort_id']];bs=raw[s['code']]
        post=[b for b in bs if s['date']<b['date']<=c.T]
        peak=s['day0_close'];drawdown=0
        for b in post:
            peak=max(peak,b['close']);drawdown=min(drawdown,c.h.pct(b['close'],peak))
        v['max_close_to_close_drawdown_pct']=drawdown
        v['drawdown_definition']='chronological daily close peak-to-trough after frozen reference; not intraday drawdown'
        v['subsequent_volume_expansion_events']=[{'date':bs[i]['date'],'volume_vs_prior_session':round(bs[i]['volume']/bs[i-1]['volume'],3),
             'close_change_pct':c.h.pct(bs[i]['close'],bs[i-1]['close'])} for i in range(1,len(bs))
             if s['date']<bs[i]['date']<=c.T and bs[i-1]['volume']>0 and bs[i]['volume']/bs[i-1]['volume']>=1.5]
    # A night-time completion must inspect notices available by the real time,
    # including the next civil date, while keeping price data strictly at T.
    names={r['code']:r['name'] for r in market['broad_pool']}
    names.update({r['SECURITY_CODE']:r['SECURITY_NAME_ABBR'] for r in e['dragon_tiger']['raw_reason_rows_data']})
    existing_notices=e.get('issuer_notices',{})
    notice_codes=sorted(set(existing_notices)|{s['code'] for s in e['low_position']['new_candidates']})
    nodes,nerrors=c.parallel([(code,names.get(code,existing_notices.get(code,{}).get('name',code))) for code in notice_codes],latest_notices,workers=3,label='latest_issuer_notices')
    e['initial_issuer_notices']=existing_notices
    e['issuer_notices']={key[0]:v for key,v in nodes.items()}
    e['provider_failures']['latest_notices']={str(k):v for k,v in nerrors.items()}
    known={r['source'] for r in e.get('issuer_primary_pdf_checks',[])}
    pdfkeys=[]
    for code,node in e['issuer_notices'].items():
        anns=node['announcements']
        picked=anns[:2]+[r for r in anns if re.search('业绩|减持|解除限售|质押|风险提示|异常波动',r['announcementTitle'])][:3]
        for r in picked:
            url='https://static.cninfo.com.cn/'+r['adjunctUrl']
            if url in known:continue
            known.add(url);pdfkeys.append((code,r))
    fs,ferrors=c.parallel(list(range(len(pdfkeys))),lambda i:primary_pdf(pdfkeys[i]),workers=3,label='latest_primary_pdfs')
    e.setdefault('issuer_primary_pdf_checks',[]).extend(fs.values())
    e['provider_failures']['latest_pdfs']={str(k):v for k,v in ferrors.items()}
    e['audit_completed_at_utc']=datetime.now(timezone.utc).isoformat()
    PATH.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'crosschecks':e['price_crosscheck_summary'],'cumulative_v4':e['volume_price']['cumulative_v4_next_day_price_statistics'],
        'new_low':[(s['code'],s['name'],s['close']) for s in e['low_position']['new_candidates']],
        'prior_combined_count':len(prior)},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
