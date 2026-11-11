"""Freeze a broad pool, then collect same-date daily and five-minute evidence."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
T = '2026-11-11'
sys.path.insert(0, str(ROOT / 'backend'))
from daily_snapshot import validate_snapshot


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vp = module('scripts/publish_volume_price_20261104.py', 'vp')
minute_helper = module('scripts/collect_recovery_20261105.py', 'minute_helper')
minute_helper.DAY = T


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def fetch(code, scale):
    symbol = ('sh' if code.startswith('6') else 'sz') + code
    url = f'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_manual=/CN_MarketDataService.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen=' + ('150' if scale == 240 else '240')
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}, timeout=15)
    r.raise_for_status()
    match = re.search(r'=\((\[.*\])\)\s*;?\s*$', r.text, re.S)
    if not match:
        raise ValueError('invalid_jsonp')
    raw = json.loads(match.group(1))
    bars = []
    for x in raw:
        if x['day'][:10] > T or (scale == 5 and x['day'][:10] != T):
            continue
        b = {k: float(x[k]) for k in ['open', 'high', 'low', 'close', 'volume']}
        if 'amount' in x:
            b['amount'] = float(x['amount'])
        if not all(math.isfinite(v) for v in b.values()) or not 0 < b['low'] <= min(b['open'], b['close']) <= max(b['open'], b['close']) <= b['high']:
            raise ValueError('invalid_ohlcv')
        bars.append({'date': x['day'][:10], 'time': x['day'], **b})
    if not bars or bars[-1]['date'] != T:
        raise ValueError('same_date_bar_unavailable')
    if scale == 240 and len(bars) < 21:
        raise ValueError('insufficient_history')
    return {'code': code, 'url': url, 'retrieved_at': now(), 'provider': 'Sina unadjusted K-line', 'adjustment': 'none', 'volume_unit': 'shares', 'bars': bars}


def main():
    snap = validate_snapshot(json.loads((ROOT / f'backend/data/sina_daily_full/{T}.json').read_text()), T, 'sina_close_snapshot')
    prior = validate_snapshot(json.loads((ROOT / 'backend/data/baostock/2026-11-10.json').read_text()), '2026-11-10', 'baostock')
    current = {r['code'].split('.')[-1]: r for r in snap['rows']}
    previous = {r['code'].split('.')[-1]: r for r in prior['rows']}
    broad, market = vp.freeze_broad(snap['rows'], previous, set(current))
    ev = {'date': T, 'started_at': now(), 'broad_frozen_at': now(), 'broad_seed': broad, 'market_count': len(market), 'daily': {}, 'errors': {}, 'five_minute': {}}
    path = ROOT / 'docs/research/recovery-20261111-histories.json'
    def save():
        path.write_text(json.dumps(ev, ensure_ascii=False) + '\n')
    save()
    with ThreadPoolExecutor(max_workers=6) as ex:
        fs = {ex.submit(fetch, r['code6'], 240): r['code6'] for r in broad}
        for n, f in enumerate(as_completed(fs)):
            c = fs[f]
            try:
                h = f.result()
                m = vp.metrics(h, current[c])
                m['sina_snapshot_close'] = m.pop('baostock_close')
                m['same_provider_close_crosscheck_abs'] = m.pop('ohlc_close_crosscheck_abs')
                m.update(name=current[c]['name'], amount_yuan=current[c]['amount'])
                if max(abs(h['bars'][-1][k] - current[c][k]) for k in ['open', 'high', 'low', 'close']) > .011:
                    raise ValueError('same_provider_close_ohlc_mismatch')
                ev['daily'][c] = {'history': h, 'metrics': m}
            except Exception as e:
                ev['errors'][c + ':daily'] = str(e)[:180]
            if n % 20 == 0:
                save()
                print('daily', n+1, 'valid', len(ev['daily']), flush=True)
    ev['broad_pool'] = [v['metrics'] for v in ev['daily'].values()]
    ev['deep_pool'] = vp.select_deep(ev['broad_pool'])
    # Moderate positive structures are independent of the extreme-volume risk pool.
    eligible = [r for r in ev['broad_pool'] if 'ST' not in r['name'].upper() and not r['name'].startswith(('N', 'C', '退'))
                and .5 <= r['pct'] <= 7 and r['clv'] is not None and r['clv'] >= .65
                and r['rvol20'] is not None and 1.1 <= r['rvol20'] <= 4
                and r['position120'] is not None and r['position120'] <= .75
                and r['close'] >= r['ma20'] and r['amount_yuan'] >= 100_000_000]
    eligible.sort(key=lambda r: (r['breakout20'], r['clv'], -r['position120'], r['amount_yuan']), reverse=True)
    ev['moderate_structures'] = eligible
    minute_codes = sorted({r['code'] for r in ev['deep_pool']} | {r['code'] for r in eligible[:12]})
    save()
    print('broad_complete', len(ev['broad_pool']), 'moderate', [(r['code'], r['name'], round(r['pct'], 2), round(r['position120'], 3)) for r in eligible], flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fs = {ex.submit(fetch, c, 5): c for c in minute_codes}
        for n, f in enumerate(as_completed(fs)):
            c = fs[f]
            try:
                item = f.result()
                item['validation'] = minute_helper.validate_minutes(item, current[c])
                ev['five_minute'][c] = item
            except Exception as e:
                ev['errors'][c + ':minute'] = str(e)[:180]
            if n % 10 == 0:
                save()
                print('minutes', n+1, flush=True)
    ev['completed_at'] = now()
    save()
    print('histories_complete', len(ev['daily']), len(ev['five_minute']), flush=True)


if __name__ == '__main__':
    main()
