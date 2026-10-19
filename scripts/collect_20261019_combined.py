#!/usr/bin/env python3
"""Collect dated, non-trading evidence for the three missing full modules.

Shared public raw evidence is linked, not counted as extra independent signals.
No daily range or minute price point establishes an executed transaction.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import json
from pathlib import Path
import statistics
import urllib.parse
import urllib.request

import pandas as pd
import collect_20261015_combined as h
from collect_20261016_context import ladder
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
T, PREV, COMPACT = '2026-10-19', '2026-10-16', '20261019'
TARGET = ROOT / 'docs/research/combined-pair-2026-10-19-evidence.json'
h.T, h.T_COMPACT = T, COMPACT


def load(name):
    return json.loads((ROOT / name).read_text())


def get_seats(key):
    code, side = key
    p = {'reportName': 'RPT_BILLBOARD_DAILYDETAILS' + side, 'columns': 'ALL',
         'filter': f'''(TRADE_DATE='{T}')(SECURITY_CODE="{code}")''',
         'pageNumber': 1, 'pageSize': 500, 'sortTypes': '-1', 'sortColumns': side,
         'source': 'WEB', 'client': 'WEB'}
    payload = h.request_json(h.LHB_EM, p, attempts=2)
    if not payload.get('success'):
        raise ValueError(payload.get('message'))
    rows = (payload.get('result') or {}).get('data') or []
    assert all(r['SECURITY_CODE'] == code and r['TRADE_DATE'].startswith(T) for r in rows)
    return {'code': code, 'side': side, 'source': h.LHB_EM + '?' + urllib.parse.urlencode(p), 'rows': rows}


def notices(pair):
    code, name = pair
    p = {'pageNum': 1, 'pageSize': 50, 'column': 'szse' if code.startswith(('00', '30')) else 'sse',
         'tabName': 'fulltext', 'seDate': '2026-08-01~' + T, 'sortName': 'time',
         'sortType': 'desc', 'isHLtitle': 'true', 'searchkey': name}
    url = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
    req = urllib.request.Request(url, data=urllib.parse.urlencode(p).encode(), headers={
        'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    return {'code': code, 'name': name, 'source': url, 'query': p,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'total_query_hits': payload.get('totalAnnouncement'),
            'announcements': [{k: r.get(k) for k in ('secCode', 'announcementTitle', 'announcementTime', 'adjunctUrl')}
                              for r in payload.get('announcements', []) if r.get('secCode') == code]}


def validate(codes, raw, minutes):
    out = []
    for code in codes:
        bars = raw.get(code, [])
        base, cur = h.by_date(bars, PREV), h.by_date(bars, T)
        if not base or not cur:
            out.append({'code': code, 'status': 'missing_target_or_reference_daily_bar'})
            continue
        out.append({'code': code, 'reference_date': PREV, 'validation_date': T,
                    'reference_close': base['close'], **cur,
                    'open_return_pct': h.pct(cur['open'], base['close']),
                    'close_return_pct': h.pct(cur['close'], base['close']),
                    'high_observation_pct': h.pct(cur['high'], base['close']),
                    'low_observation_pct': h.pct(cur['low'], base['close']),
                    'minute_checkpoints': h.minute_checkpoints(minutes.get(code, {}).get(COMPACT, []), base['close']),
                    'observation_type': 'price_observation', 'executed_trade': False,
                    'trigger_status': 'no_fill_or_complete_frozen_sequence_verified',
                    'executable_net_return_pct': None,
                    'sources': [h.DAILY + '?param=' + h.symbol(code) + ',day,,,180,none',
                                h.FIVE_DAY + '?code=' + h.symbol(code)]})
    return out


def stats(rows):
    valid = [r for r in rows if 'close_return_pct' in r]
    result = {'expected': len(rows), 'verified': len(valid),
              'positive_close_count': sum(r['close_return_pct'] > 0 for r in valid),
              'price_positive_fraction': sum(r['close_return_pct'] > 0 for r in valid) / len(valid) if valid else None,
              'executable_sample_count': 0, 'strategy_win_rate': None,
              'net_return_pct': None, 'payoff_ratio': None}
    for k in ('open_return_pct', 'close_return_pct', 'high_observation_pct', 'low_observation_pct'):
        result['mean_' + k] = h.mean([r[k] for r in valid])
        result['median_' + k] = h.median([r[k] for r in valid])
    return result


def enrich(rows, qfq, raw, minutes):
    enriched = h.enrich_deep(rows, qfq)
    for s in enriched:
        code = s['code']; bars = qfq[code]
        s['distance_ma20_pct'] = h.pct(s['close'], s['ma']['20'])
        s['prior5_high'] = max(b['high'] for b in bars[-6:-1])
        s['prior20_low'] = min(b['low'] for b in bars[-21:-1])
        s['intraday_volume_ratio'] = None
        s['intraday_volume_ratio_note'] = '收盘相对均量不等于盘中同一时点量比；没有盘中量比原快照。'
        s['moving_average_alignment'] = 'MA5>MA20>MA60' if s['ma']['5'] > s['ma']['20'] > s['ma']['60'] else 'not_full_bullish_alignment'
        points = minutes.get(code, {}).get(COMPACT, [])
        s['minute_checkpoints'] = h.minute_checkpoints(points, s['previous_close'])
        at14 = next((p for p in points if p['clock']=='1400'), None)
        closept = next((p for p in reversed(points) if p['clock']=='1500'), None)
        s['tail_return_1400_to_1500_pct'] = h.pct(closept['price'], at14['price']) if at14 and closept else None
        totalv = closept['cumulative_volume_provider_units'] if closept else 0
        s['tail_volume_share_pct'] = round((totalv-at14['cumulative_volume_provider_units'])/totalv*100,3) if at14 and totalv else None
        s['minute_source'] = h.FIVE_DAY + '?code=' + h.symbol(code)
        if not points:
            s['missing'].append('same_day_minute_price_points')
        s['turnover_change_pct_points'] = None
        cur = h.by_date(raw.get(code, []), T)
        s['daily_crosscheck'] = {'source': 'Sina frozen close versus Tencent unadjusted daily',
                                'max_ohlc_difference': max(abs(cur[k]-s[k]) for k in ('open','high','low','close')) if cur else None}
        rate = Decimal('.20') if code.startswith(('30','68')) else Decimal('.10')
        upper = float((Decimal(str(s['previous_close']))*(1+rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        s['board_limit_regime'] = '20%' if rate == Decimal('.20') else '10%'
        s['calculated_upper_reference'] = upper
        s['calculated_upper_verified_exchange_quote'] = False
        if abs(s['close']-upper)<.011:
            s['structure'] = '封板观察/次日普通成交待核验'
        elif s['clv'] is not None and (s['clv'] < .65 or (s['tail_return_1400_to_1500_pct'] is not None and s['tail_return_1400_to_1500_pct'] < -1.5)):
            s['structure'] = '放量冲高回落/承接不足'
        elif s['rvol']['20'] >= 3 and s['distance_ma20_pct'] > 20:
            s['structure'] = '高乖离高量/分歧风险'
        elif s['range_position_pct']['120'] is not None and s['range_position_pct']['120'] <= 55:
            s['structure'] = '低中位放量推进/待次日承接'
        else:
            s['structure'] = '放量推进/待次日承接'
    return enriched


def summarize_seats(row, fetched):
    code, tid = row['SECURITY_CODE'], str(row['TRADE_ID'])
    buys = [r for r in fetched.get((code, 'BUY'), {}).get('rows', []) if str(r.get('TRADE_ID')) == tid]
    sells = [r for r in fetched.get((code, 'SELL'), {}).get('rows', []) if str(r.get('TRADE_ID')) == tid]
    union = {(str(r.get('OPERATEDEPT_CODE')), float(r.get('BUY') or 0), float(r.get('SELL') or 0), str(r.get('TRADE_ID'))): r for r in buys+sells}
    b = sum(float(r.get('BUY') or 0) for r in buys)
    s = sum(float(r.get('SELL') or 0) for r in sells)
    ub = sum(float(r.get('BUY') or 0) for r in union.values())
    us = sum(float(r.get('SELL') or 0) for r in union.values())
    ab, ass = float(row['BILLBOARD_BUY_AMT']), float(row['BILLBOARD_SELL_AMT'])
    top_match = abs(b-ab)<1 and abs(s-ass)<1
    union_match = abs(ub-ab)<1 and abs(us-ass)<1
    return {'code': code, 'name': row['SECURITY_NAME_ABBR'], 'close': row['CLOSE_PRICE'],
            'daily_change_pct': row['CHANGE_RATE'], 'turnover_pct': row['TURNOVERRATE'],
            'selected_trade_id': tid, 'selected_period_reason': row['EXPLANATION'],
            'buy_cny': ab, 'sell_cny': ass, 'net_cny': row['BILLBOARD_NET_AMT'],
            'buy_seats_em': buys, 'sell_seats_em': sells,
            'buy_concentration_top1_pct': round(max((float(r.get('BUY') or 0) for r in buys),default=0)/b*100,3) if b else None,
            'sell_concentration_top1_pct': round(max((float(r.get('SELL') or 0) for r in sells),default=0)/s*100,3) if s else None,
            'seat_reconciliation': {'buy_count':len(buys),'sell_count':len(sells), 'top5_buy_sum_cny':b,
                                    'top5_sell_sum_cny':s,'union_buy_cny':ub,'union_sell_cny':us,
                                    'aggregate_buy_cny':ab,'aggregate_sell_cny':ass,
                                    'aggregate_basis':'union_of_top5_buy_and_sell_rows' if union_match and not top_match else 'top5_each_side',
                                    'matched': bool(buys and sells and (top_match or union_match))}}


def main():
    started = datetime.now(timezone.utc).isoformat()
    market = load('docs/research/market-review-2026-10-19-evidence.json')
    prior = load_evidence(ROOT/'docs/research/combined-pair-2026-10-16-evidence.json')
    lowdoc = load('backend/data/low_position_samples.json')
    previous_volume = prior['volume_price']['deep_samples']
    previous_dragon = prior['dragon_tiger']['selected_observations']
    failures = {}
    p = {'reportName':'RPT_DAILYBILLBOARD_DETAILSNEW','columns':'ALL',
         'filter':f"(TRADE_DATE='{T}')",'pageNumber':1,'pageSize':500,'source':'WEB','client':'WEB'}
    payload = h.request_json(h.LHB_EM, p, attempts=2)
    lhb = (payload.get('result') or {}).get('data') or []
    if not lhb:
        failures['lhb_list'] = 'empty_same_day_list'
    ths = {}
    try:
        tables = pd.read_html(BytesIO(h.request_bytes(f'https://data.10jqka.com.cn/market/longhu/date/{T}/',timeout=30)))
        ths = {'table_count':len(tables),'summary_rows':tables[5].to_dict(orient='records') if len(tables)>5 else [],
               'source':f'https://data.10jqka.com.cn/market/longhu/date/{T}/',
               'join_policy':'summary crosscheck only; seats require exact dated TRADE_ID join'}
    except Exception as exc:
        failures['lhb_ths'] = f'{type(exc).__name__}:{exc}'
    candidates = market['broad_pool']
    listed = [r['SECURITY_CODE'] for r in lhb if r['SECURITY_CODE'].startswith(('00','30','60','68'))]
    recs = load('backend/data/recommendations.json')['items']
    historic_rec_codes = [r['code'] for r in recs if r.get('strategy')=='combined_limitup_watch' and r.get('code')]
    codes = sorted(set([r['code'] for r in candidates]+[r['code'] for r in previous_volume+previous_dragon+lowdoc['items']]+listed+historic_rec_codes+['000099','002085','000887','sh000001']))
    codes = [c for c in codes if len(c)==6]
    print(json.dumps({'collecting_codes':len(codes),'lhb_reason_rows':len(lhb),'lhb_unique':len(set(listed))}), flush=True)
    qfq, eq = h.fetch_parallel(codes, lambda c: h.daily_bars(c,True), workers=8)
    raw, er = h.fetch_parallel(codes, lambda c: h.daily_bars(c,False), workers=8)
    minute_codes = sorted(set([r['code'] for r in market['deep_pool']+previous_volume+previous_dragon]+['000887','000099','002085']+historic_rec_codes))
    minutes, em = h.fetch_parallel(minute_codes,h.five_day_minutes,workers=5)
    # All public daily bars are cut off at T, even if a provider returns more.
    qfq = {c:[b for b in bs if b['date']<=T] for c,bs in qfq.items()}
    raw = {c:[b for b in bs if b['date']<=T] for c,bs in raw.items()}
    broad = enrich(candidates,qfq,raw,minutes)
    deep_codes = {r['code'] for r in market['deep_pool']}
    deep = [r for r in broad if r['code'] in deep_codes]
    previous_map = {r['code']:r for r in previous_volume}
    for s in deep:
        prev = previous_map.get(s['code'])
        if prev:s['turnover_change_pct_points']=round(s['turnover_pct']-prev['turnover_pct'],3)
    vv = validate([r['code'] for r in previous_volume],raw,minutes)
    dv = validate([r['code'] for r in previous_dragon],raw,minutes)
    lv = h.low_validations(lowdoc['items'],raw)
    for r in lv:r['report_ids']=['low-position-20261019-close-v1']
    low_new = h.choose_new_low(broad,{r['code'] for r in lowdoc['items']})
    extra_minutes, extra_minute_errors = h.fetch_parallel([s['code'] for s in low_new if s['code'] not in minutes], h.five_day_minutes, workers=3)
    minutes.update(extra_minutes); em.update(extra_minute_errors)
    if extra_minutes:
        broad = enrich(candidates,qfq,raw,minutes)
        deep = [r for r in broad if r['code'] in deep_codes]
        for s in deep:
            prev = previous_map.get(s['code'])
            if prev:s['turnover_change_pct_points']=round(s['turnover_pct']-prev['turnover_pct'],3)
        low_new = h.choose_new_low(broad,{r['code'] for r in lowdoc['items']})
    # Select balanced observation/negative examples, not mechanically net-buy winners.
    ranked = sorted(lhb,key=lambda r:float(r.get('BILLBOARD_NET_AMT') or 0),reverse=True)
    chosen = []
    for code in ['002903','002683','002134','000530','002343','600825']:
        same = [r for r in ranked if r['SECURITY_CODE']==code]
        if same and len(chosen)<5:chosen.append(same[0])
    for r in ranked:
        if r['SECURITY_CODE'] in deep_codes and r['SECURITY_CODE'] not in {x['SECURITY_CODE'] for x in chosen}:
            chosen.append(r)
        if len(chosen)>=5:break
    seat_queries, seat_errors = h.fetch_parallel([(r['SECURITY_CODE'],s) for r in chosen for s in ('BUY','SELL')],get_seats,workers=3)
    selected = [summarize_seats(r,seat_queries) for r in chosen]
    # Include all proposed low samples in announcement retrieval, not just displayed stocks.
    names = {r['code']:r['name'] for r in broad}
    names['000887']='中鼎股份'
    notice_codes = sorted(set([r['code'] for r in low_new]+[r['code'] for r in selected]+['002683','002903','000887']))
    issuer, notice_errors = h.fetch_parallel([(c,names.get(c,c)) for c in notice_codes],notices,workers=3)
    contexts, context_errors = h.fetch_parallel(['2026-10-14','2026-10-15',PREV,T],ladder,workers=3)
    e = {'market_date':T,'previous_trading_day':PREV,'collection_started_at_utc':started,
         'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
         'market_review_reused':{'report_id':'market-review-20261019-close-v1','coverage':market['coverage'],'market':market['market']},
         'volume_price':{'rule_version':'volume_price_close_v4','broad_verified':len(broad),'broad_samples':broad,
                         'deep_expected':28,'deep_samples':deep,'previous_cohort_id':'volume-price-20261016-close-v1-cohort',
                         'previous_validations':vv,'previous_statistics':stats(vv)},
         'low_position':{'rule_version':'low_position_30d_v1','existing_expected':len(lowdoc['items']),
                         'existing_validations':lv,'new_candidates':low_new},
         'dragon_tiger':{'rule_version':'dragon_tiger_close_v2','raw_reason_rows_data':lhb,
                         'reason_rows':len(lhb),'unique_codes':len({r['SECURITY_CODE'] for r in lhb}),
                         'ths_crosscheck':ths,'selected_observations':selected,
                         'raw_seat_queries':list(seat_queries.values()),'previous_validations':dv,'previous_statistics':stats(dv)},
         'prior_combined':validate(historic_rec_codes,raw,minutes),
         'raw_daily_histories':raw,'qfq_daily_histories':qfq,'minute_price_paths':minutes,
         'issuer_notices':{str(k[0]):v for k,v in issuer.items()},'limitup_market_contexts':contexts,
         'provider_failures':{'misc':failures,'qfq':eq,'raw':er,'minutes':em,'seats':{str(k):v for k,v in seat_errors.items()},
                              'notices':{str(k):v for k,v in notice_errors.items()},'contexts':context_errors},
         'sources':['docs/research/market-review-2026-10-19-evidence.json',h.DAILY,h.FIVE_DAY,h.LHB_EM,
                    f'https://data.10jqka.com.cn/market/longhu/date/{T}/','https://www.cninfo.com.cn/new/hisAnnouncement/query'],
         'limits':['No auction, verified minute OHLC, order book, ticks or fills; no executable return inferred',
                   'Public seat labels describe disclosed channels, not beneficial owner or capital identity',
                   'Daily-history mining today is not a contemporaneous intraday recommendation',
                   'Relative volume uses only the preceding completed sessions; moving averages include T']}
    TARGET.write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'file':str(TARGET),'volume_previous':stats(vv),'deep':len(deep),'broad':len(broad),
                      'low_verified':len(lv),'new_low':[(r['code'],r['name']) for r in low_new],
                      'dragon_previous':stats(dv),'seats':[(r['code'],r['seat_reconciliation']['matched']) for r in selected],
                      'failures':e['provider_failures']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
