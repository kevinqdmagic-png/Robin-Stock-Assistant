#!/usr/bin/env python3
"""Dated evidence for Oct20 missing full modules; no inferred executions.

Reuses the immutable full-A scan, then independently fetches dated histories,
checks the entire previous cohorts and records public seat/issuer evidence.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import urllib.parse
import urllib.request

import pandas as pd
import collect_20261015_combined as h
import collect_20261019_combined as previous_helpers
from collect_20261016_context import ladder
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
T, PREV, COMPACT = '2026-10-20', '2026-10-19', '20261020'
TARGET = ROOT / 'docs/research/combined-pair-2026-10-20-evidence.json'
START = '2026-10-20T17:19:57+00:00'
CACHE = ROOT / 'docs/research/combined-pair-2026-10-20-collection-checkpoint.json'
COLLECTED_CACHE = json.loads(CACHE.read_text()) if CACHE.exists() else {}
SEAT_CODES = ['002929', '600148', '002164', '000530', '300115']
h.T, h.T_COMPACT = T, COMPACT
previous_helpers.T, previous_helpers.PREV, previous_helpers.COMPACT = T, PREV, COMPACT


def load(path):
    return json.loads((ROOT / path).read_text())


def sym(code):
    if code.startswith(('sh', 'sz', 'bj')):
        return code
    if code.startswith(('920', '4', '8')):
        return 'bj' + code
    return ('sh' if code.startswith(('6', '9')) else 'sz') + code


def request(url, params=None, timeout=22):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': h.UA, 'Referer': 'https://data.eastmoney.com/'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def jrequest(url, params=None):
    return json.loads(request(url, params))


def parallel(keys, func, workers=6, label=''):
    result, errors = {}, {}
    cached = COLLECTED_CACHE.setdefault(label, {}) if label else {}
    def token(key):
        return json.dumps(key, ensure_ascii=False)
    for key in keys:
        if token(key) in cached:
            result[key] = cached[token(key)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fs = {pool.submit(func, k): k for k in keys if k not in result}
        for i, future in enumerate(as_completed(fs), 1):
            key = fs[future]
            try:
                result[key] = future.result()
                cached[token(key)] = result[key]
            except Exception as exc:
                errors[key] = f'{type(exc).__name__}:{exc}'
            if label and (i % 30 == 0 or i == len(fs)):
                CACHE.write_text(json.dumps(COLLECTED_CACHE, ensure_ascii=False))
                print(json.dumps({'phase': label, 'done': i, 'expected': len(fs), 'errors': len(errors)}), flush=True)
    return result, errors


def daily(key):
    code, adjusted = key
    mode = 'qfq' if adjusted else 'none'
    s = sym(code)
    p = jrequest(h.DAILY, {'param': f'{s},day,,,180,{mode}'})
    node = (p.get('data') or {}).get(s) or {}
    rows = node.get('qfqday' if adjusted else 'day') or []
    bs = [{'date': str(r[0]), 'open': float(r[1]), 'close': float(r[2]), 'high': float(r[3]),
           'low': float(r[4]), 'volume': float(r[5])} for r in rows if len(r) >= 6 and str(r[0]) <= T]
    if not bs or bs[-1]['date'] != T:
        raise ValueError('missing_target_daily_bar')
    return bs


def minutes(code):
    s = sym(code)
    p = jrequest(h.FIVE_DAY, {'code': s})
    groups = (((p.get('data') or {}).get(s) or {}).get('data') or [])
    out = {}
    for group in groups:
        day = str(group.get('date') or '')
        if day > COMPACT:
            continue
        pts = []
        for row in group.get('data') or []:
            r = str(row).split()
            if len(r) >= 4:
                pts.append({'clock': r[0], 'price': float(r[1]), 'cumulative_volume_provider_units': float(r[2]),
                            'cumulative_amount_cny': float(r[3])})
        if pts:
            out[day] = pts
    if COMPACT not in out:
        raise ValueError('missing_target_minute_price_points')
    return out


def seats(key):
    code, side = key
    p = {'reportName': 'RPT_BILLBOARD_DAILYDETAILS' + side, 'columns': 'ALL',
         'filter': f'''(TRADE_DATE='{T}')(SECURITY_CODE="{code}")''',
         'pageNumber': 1, 'pageSize': 500, 'sortTypes': '-1', 'sortColumns': side, 'source': 'WEB', 'client': 'WEB'}
    payload = jrequest(h.LHB_EM, p)
    if not payload.get('success'):
        raise ValueError(payload.get('message'))
    rows = (payload.get('result') or {}).get('data') or []
    assert rows and all(r['SECURITY_CODE'] == code and r['TRADE_DATE'].startswith(T) for r in rows)
    return {'code': code, 'side': side, 'source': h.LHB_EM + '?' + urllib.parse.urlencode(p), 'rows': rows}


def enrich(rows, qfq, raw, paths):
    out = []
    for quote in rows:
        code = quote['code']
        bs, rb = qfq.get(code, []), raw.get(code, [])
        cur, rcur = h.by_date(bs, T), h.by_date(rb, T)
        if not cur or not rcur or len(bs) < 21 or len(rb) < 2:
            continue
        prev = rb[-2]
        ma = {str(n): round(statistics.fmean(b['close'] for b in bs[-n:]), 3) if len(bs) >= n else None for n in (5, 10, 20, 60)}
        rv = {str(n): round(cur['volume'] / h.volume_mean(bs, n), 3) if h.volume_mean(bs, n) else None for n in (5, 10, 20)}
        pts = [p for p in paths.get(code, {}).get(COMPACT, []) if '0930' <= p['clock'] <= '1500']
        at14 = next((p for p in pts if p['clock'] == '1400'), None)
        closept = next((p for p in reversed(pts) if p['clock'] == '1500'), None)
        clv = round((rcur['close'] - rcur['low']) / (rcur['high'] - rcur['low']), 3) if rcur['high'] > rcur['low'] else None
        differences = {k: round(rcur[k] - float(quote[k if k != 'close' else 'trade']), 6)
                       for k in ('open', 'high', 'low', 'close') if (k if k != 'close' else 'trade') in quote}
        s = {'code': code, 'name': quote['name'], 'date': T, **rcur, 'previous_close': prev['close'],
             'daily_change_pct': round(float(quote['changepercent']), 3), 'amount_cny': float(quote['amount']),
             'turnover_pct': round(float(quote['turnoverratio']), 3), 'rvol': rv, 'ma': ma,
             'range_position_pct': {str(n): h.range_position(bs, n) for n in (20, 60, 120)},
             'prior5_high': max(b['high'] for b in bs[-6:-1]), 'prior20_high': max(b['high'] for b in bs[-21:-1]),
             'prior20_low': min(b['low'] for b in bs[-21:-1]), 'clv': clv,
             'amplitude_pct': h.pct(rcur['high'], prev['close']) - h.pct(rcur['low'], prev['close']),
             'distance_ma20_pct': h.pct(cur['close'], ma['20']),
             'volume_vs_previous_session': round(cur['volume'] / bs[-2]['volume'], 3) if bs[-2]['volume'] else None,
             'intraday_volume_ratio': None, 'intraday_volume_ratio_note': '缺原时点盘中量比；RVOL分母不含T。',
             'turnover_change_pct_points': None,
             'moving_average_alignment': 'MA5>MA20>MA60' if ma['60'] and ma['5'] > ma['20'] > ma['60'] else 'not_full_bullish_alignment',
             'minute_checkpoints': h.minute_checkpoints(pts, prev['close']),
             'tail_return_1400_to_1500_pct': h.pct(closept['price'], at14['price']) if at14 and closept else None,
             'tail_volume_share_pct': round((closept['cumulative_volume_provider_units'] - at14['cumulative_volume_provider_units']) / closept['cumulative_volume_provider_units'] * 100, 3) if at14 and closept and closept['cumulative_volume_provider_units'] else None,
             'daily_crosscheck': {'source': 'Tencent raw daily versus archived Sina scan', 'fields': list(differences), 'differences': differences,
                                 'max_ohlc_difference': max(map(abs, differences.values())) if len(differences) == 4 else None,
                                 'max_available_field_difference': max(map(abs, differences.values())) if differences else None},
             'daily_source': h.DAILY + '?param=' + sym(code) + ',day,,,180,none',
             'minute_source': h.FIVE_DAY + '?code=' + sym(code), 'evidence_status': 'dated_daily_history_with_explicit_crosscheck_scope',
             'missing': ['auction_0925', 'intraday_volume_ratio_snapshot', 'verified_minute_OHLC', 'order_book', 'ticks', 'verified_fill']}
        if not pts:
            s['missing'].append('same_day_minute_price_points')
        rate = Decimal('.30') if code.startswith(('920', '4', '8')) else Decimal('.20') if code.startswith(('30', '68')) else Decimal('.10')
        s['board_limit_regime'] = str(int(rate * 100)) + '%'
        upper = float((Decimal(str(prev['close'])) * (1 + rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        s['calculated_upper_reference'], s['calculated_upper_verified_exchange_quote'] = upper, False
        if abs(s['close'] - upper) < .011:
            s['structure'] = '封板观察/次日普通成交待核验'
        elif clv is not None and (clv < .65 or (s['tail_return_1400_to_1500_pct'] is not None and s['tail_return_1400_to_1500_pct'] < -1.5)):
            s['structure'] = '放量冲高回落/承接不足'
        elif rv['20'] >= 3 and s['distance_ma20_pct'] > 20:
            s['structure'] = '高乖离高量/分歧风险'
        elif s['range_position_pct']['120'] is not None and s['range_position_pct']['120'] <= 55:
            s['structure'] = '低中位放量推进/待次日承接'
        else:
            s['structure'] = '放量推进/待次日承接'
        out.append(s)
    return out


def checkpoint(e):
    TARGET.write_text(json.dumps(e, ensure_ascii=False, indent=2) + '\n')


def main():
    market = load('docs/research/market-review-2026-10-20-evidence.json')
    prior = load_evidence(ROOT / 'docs/research/combined-pair-2026-10-19-evidence.json')
    lowdoc = load('backend/data/low_position_samples.json')
    recs = load('backend/data/recommendations.json')['items']
    priorv = prior['volume_price']['deep_samples']
    priord = prior['dragon_tiger']['selected_observations']
    p = {'reportName': 'RPT_DAILYBILLBOARD_DETAILSNEW', 'columns': 'ALL', 'filter': f"(TRADE_DATE='{T}')",
         'pageNumber': 1, 'pageSize': 500, 'source': 'WEB', 'client': 'WEB'}
    payload = jrequest(h.LHB_EM, p)
    lhb = (payload.get('result') or {}).get('data') or []
    assert lhb and all(r['TRADE_DATE'].startswith(T) for r in lhb)
    listed = [r['SECURITY_CODE'] for r in lhb if r['SECURITY_CODE'].startswith(('00', '30', '60', '68'))]
    combined = [r for r in recs if r.get('strategy') == 'combined_limitup_watch']
    comparison = ['000099', '002085', '000887', '600592', '300458', '300825', '603273', '002917', '688795']
    codes = sorted(set([r['code'] for r in market['broad_pool'] + priorv + priord + lowdoc['items'] + combined] + listed + comparison))
    keys = [(c, adj) for c in codes + ['sh000001'] for adj in (False, True)]
    collected, errs = parallel(keys, daily, workers=8, label='daily_histories')
    qfq = {c: bs for (c, adj), bs in collected.items() if adj}
    raw = {c: bs for (c, adj), bs in collected.items() if not adj}
    qerrors = {c: er for (c, adj), er in errs.items() if adj}
    rerrors = {c: er for (c, adj), er in errs.items() if not adj}
    minute_codes = sorted(set([r['code'] for r in market['deep_pool'] + priorv + priord + combined] + comparison + SEAT_CODES))
    paths, minute_errors = parallel(minute_codes, minutes, workers=3, label='minute_price_paths')
    # Broad scan rows are compact snapshots. Preserve explicit full-OHLC crosschecks only where raw Sino fields exist.
    deepquotes = {s['code']: s for s in market['deep_pool']}
    broadquotes = [{**s, **deepquotes.get(s['code'], {})} for s in market['broad_pool']]
    broad = enrich(broadquotes, qfq, raw, paths)
    lownew = h.choose_new_low(broad, {r['code'] for r in lowdoc['items']})
    extra, extra_errors = parallel([s['code'] for s in lownew if s['code'] not in paths], minutes, workers=3)
    paths.update(extra); minute_errors.update(extra_errors)
    broad = enrich(broadquotes, qfq, raw, paths)
    deep = [s for s in broad if s['code'] in deepquotes]
    prevmap = {s['code']: s for s in priorv}
    for s in broad:
        if s['code'] in prevmap:
            s['turnover_change_pct_points'] = round(s['turnover_pct'] - prevmap[s['code']]['turnover_pct'], 3)
    lownew = h.choose_new_low(broad, {r['code'] for r in lowdoc['items']})
    vv = previous_helpers.validate([s['code'] for s in priorv], raw, paths)
    dv = previous_helpers.validate([s['code'] for s in priord], raw, paths)
    for r in vv + dv:
        r['minute_checkpoints'] = {k: v for k, v in r.get('minute_checkpoints', {}).items() if k <= '1500'}
    lowvals = h.low_validations(lowdoc['items'], raw)
    lowmap = {s['id']: s for s in lowdoc['items']}
    for v in lowvals:
        if not v.get('origin_cohort_id'):
            continue
        sample = lowmap[v['origin_cohort_id']]
        aft = [b for b in raw.get(sample['code'], []) if sample['date'] < b['date'] <= T]
        v['path_mfe_pct'] = h.pct(max(b['high'] for b in aft), sample['day0_close']) if aft else None
        v['path_mae_pct'] = h.pct(min(b['low'] for b in aft), sample['day0_close']) if aft else None
        broken = [b['date'] for b in aft if sample.get('invalid_close_below') is not None and b['close'] < sample['invalid_close_below']]
        v.update({'report_ids': ['low-position-20261020-close-v1'],
                  'first_verified_close_below_original_invalid': broken[0] if broken else None,
                  'ever_verified_close_below_original_invalid': bool(broken),
                  'path_definition': 'after frozen reference close; exclude signal-day intraday range',
                  'calculation_version': 'low_price_observation_v2_20261019'})
    chosen = []
    for code in SEAT_CODES:
        same = [r for r in lhb if r['SECURITY_CODE'] == code]
        same.sort(key=lambda r: ('连续' in r['EXPLANATION'], str(r['TRADE_ID'])))
        if same:
            chosen.append(same[0])
    queries, seat_errors = parallel([(r['SECURITY_CODE'], side) for r in chosen for side in ('BUY', 'SELL')], seats, workers=3, label='exact_period_seats')
    selected = [previous_helpers.summarize_seats(r, queries) for r in chosen]
    groups = defaultdict(list)
    for v in vv:
        groups[prevmap[v['code']]['structure']].append(v)
    e = {'market_date': T, 'previous_trading_day': PREV, 'execution_started_at_utc': START,
         'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
         'market_review_reused': {'report_id': 'market-review-20261020-close-v1', 'coverage': market['coverage'], 'market': market['market']},
         'volume_price': {'rule_version': 'volume_price_close_v4', 'broad_expected': 120, 'broad_verified': len(broad), 'broad_samples': broad,
                          'deep_expected': 28, 'deep_samples': deep, 'previous_cohort_id': 'volume-price-20261019-close-v1-cohort',
                          'previous_validations': vv, 'previous_statistics': previous_helpers.stats(vv),
                          'previous_by_frozen_structure': {k: previous_helpers.stats(rows) for k, rows in groups.items()}},
         'low_position': {'rule_version': 'low_position_30d_v1', 'existing_expected': len(lowdoc['items']),
                          'existing_validations': lowvals, 'new_candidates': lownew},
         'dragon_tiger': {'rule_version': 'dragon_tiger_close_v2', 'raw_reason_rows_data': lhb, 'reason_rows': len(lhb),
                          'unique_codes': len({r['SECURITY_CODE'] for r in lhb}), 'mainland_a_unique_codes': len(set(listed)),
                          'selected_observations': selected, 'raw_seat_queries': list(queries.values()),
                          'previous_validations': dv, 'previous_statistics': previous_helpers.stats(dv)},
         'raw_daily_histories': raw, 'qfq_daily_histories': qfq, 'minute_price_paths': paths,
         'provider_failures': {'qfq': qerrors, 'raw': rerrors, 'minutes': minute_errors,
                               'seats': {str(k): v for k, v in seat_errors.items()}},
         'sources': ['docs/research/market-review-2026-10-20-evidence.json', h.DAILY, h.FIVE_DAY, h.LHB_EM,
                     f'https://data.10jqka.com.cn/market/longhu/date/{T}/', 'https://www.cninfo.com.cn/new/hisAnnouncement/query',
                     'https://www.sse.com.cn/disclosure/dealinstruc/closed/'],
         'limits': ['No orderbook, ticks, verified minute OHLC or fills; price observations are not net strategy returns.',
                    'Public seat channels do not establish beneficial owner or capital identity.',
                    'RVOL denominator excludes T; close MAs include T; post-15:00 price points excluded.']}
    checkpoint(e)
    print(json.dumps({'broad': len(broad), 'deep': len(deep), 'lownew': [(s['code'], s['name']) for s in lownew],
                      'volume_previous': e['volume_price']['previous_statistics'], 'dragon_previous': e['dragon_tiger']['previous_statistics'],
                      'seats_matched': [(s['code'], s['seat_reconciliation']['matched']) for s in selected]}, ensure_ascii=False), flush=True)
    try:
        ts = pd.read_html(BytesIO(request(f'https://data.10jqka.com.cn/market/longhu/date/{T}/')))
        e['dragon_tiger']['ths_crosscheck'] = {'source': f'https://data.10jqka.com.cn/market/longhu/date/{T}/',
            'table_count': len(ts), 'summary_rows': ts[5].to_dict(orient='records') if len(ts) > 5 else [],
            'join_policy': 'Date/period/reason may overlap; not an additive sample count.'}
    except Exception as exc:
        e['provider_failures']['ths'] = f'{type(exc).__name__}:{exc}'
    names = {r['code']: r['name'] for r in market['broad_pool']}
    names.update({r['SECURITY_CODE']: r['SECURITY_NAME_ABBR'] for r in lhb})
    names.update({r['code']: r['name'] for r in lowdoc['items']})
    notice_codes = sorted(set([s['code'] for s in lownew] + SEAT_CODES + ['300458', '300825', '603273', '002917', '688795', '002343']))
    issuer, notice_errors = parallel([(code, names.get(code, code)) for code in notice_codes], previous_helpers.notices, workers=3, label='issuer_notices')
    e['issuer_notices'] = {key[0]: v for key, v in issuer.items()}
    e['provider_failures']['notices'] = {str(k): v for k, v in notice_errors.items()}
    checkpoint(e)
    contexts, context_errors = parallel(['2026-10-16', PREV, T], ladder, workers=3, label='public_ladder')
    e['limitup_market_contexts'], e['provider_failures']['contexts'] = contexts, context_errors
    pdfkeys = [(code, r) for code, node in e['issuer_notices'].items() for r in node.get('announcements', [])[:2]]
    def pdfcheck(key):
        code, r = key
        url = 'https://static.cninfo.com.cn/' + r['adjunctUrl']
        pdf = request(url, timeout=22)
        text = subprocess.run(['pdftotext', '-', '-'], input=pdf, check=True, capture_output=True).stdout.decode()
        return {'code': code, 'title': r['announcementTitle'], 'source': url, 'sha256': hashlib.sha256(pdf).hexdigest(),
                'bytes': len(pdf), 'text_excerpt': text[:6000], 'verified_at': datetime.now(timezone.utc).isoformat()}
    # Dict-bearing keys cannot be dictionary indices, so preserve stable numerical IDs.
    facts, ferr = parallel(list(range(len(pdfkeys))), lambda i: pdfcheck(pdfkeys[i]), workers=3, label='primary_pdf_facts')
    e['issuer_primary_pdf_checks'] = list(facts.values())
    e['provider_failures']['pdf'] = {str(k): v for k, v in ferr.items()}
    e['collection_completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    checkpoint(e)
    print(json.dumps({'evidence': str(TARGET), 'broad': len(broad), 'deep': len(deep), 'low_existing_verified': len([r for r in lowvals if r.get('full_validation_completed')]),
                      'new_low': [(s['code'], s['name']) for s in lownew], 'pdf_count': len(facts),
                      'failures': e['provider_failures']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
