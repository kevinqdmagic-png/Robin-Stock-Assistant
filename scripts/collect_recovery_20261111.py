"""Manual same-day evidence collection. Does not reconstruct intraday signals."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from daily_snapshot import validate_snapshot
from sina_snapshot import parse_close_snapshot
sys.path.insert(0, str(ROOT / 'scripts'))
from research_evidence_io import load_evidence

T = '2026-11-11'
OUT = ROOT / 'docs/research/recovery-20261111-evidence.json'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def get(url, params=None, encoding=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=14)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    try:
        data = r.json()
    except ValueError:
        data = r.text
    return {'url': r.url, 'retrieved_at': now(), 'data': data}


def capture(job):
    key, url, params, encoding = job
    try:
        return key, get(url, params, encoding)
    except Exception as e:
        return key, {'url': url, 'error': type(e).__name__ + ':' + str(e)[:180], 'retrieved_at': now()}


def save(ev):
    OUT.write_text(json.dumps(ev, ensure_ascii=False) + '\n')


def main():
    ev = {'date': T, 'started_at': now(), 'manual': True, 'not_original_intraday_signal': True}
    prior = json.loads((ROOT / 'backend/data/baostock/2026-11-10.json').read_text())
    codes = sorted({r['code'] for r in prior['rows'] + prior['errors'] if re.fullmatch(r'(sh\.6|sz\.[03])\d{5}', r['code'])})
    target = ROOT / 'docs/research/recovery-20261111-sina-close.json'
    rows, failures = {}, {}
    cache = ROOT / 'docs/research/recovery-20261111-close-progress.json'
    if cache.exists():
        cached = json.loads(cache.read_text())
        rows = {r['code']: r for r in cached['rows']}
    if '--context-only' in sys.argv:
        snapshot = {'coverage': None}
    elif target.exists():
        snapshot = validate_snapshot(load_evidence(target), T, 'sina_close_snapshot')
    else:
        wanted = [c for c in codes if c not in rows]
        batches = [wanted[i:i+45] for i in range(0, len(wanted), 45)]
        def batch(batch_codes):
            d = get('https://hq.sinajs.cn/list=' + ','.join(c.replace('.', '') for c in batch_codes), encoding='gb18030')
            return parse_close_snapshot(d['data'], batch_codes, T)
        with ThreadPoolExecutor(max_workers=4) as ex:
            fs = {ex.submit(batch, b): b for b in batches}
            for n, f in enumerate(as_completed(fs)):
                try:
                    rows.update({r['code']: r for r in f.result()})
                except Exception as e:
                    failures.update({c: str(e)[:100] for c in fs[f]})
                if n % 20 == 0:
                    cache.write_text(json.dumps({'rows': list(rows.values()), 'failures': failures}, ensure_ascii=False))
                    print('close_batches', n+1, 'valid', len(rows), flush=True)
        missing = [{'code': c, 'reason': failures.get(c, 'missing_suspended_stale_or_invalid')} for c in codes if c not in rows]
        snapshot = {'provider': 'sina_close_snapshot', 'trade_date': T, 'status': 'historical_observation_only',
                    'exchange_scope': 'Shanghai+Shenzhen; Beijing excluded', 'collected_at': now(),
                    'collection_method': 'timestamped_post_close_sina_quote_batches',
                    'coverage': {'checked': len(codes), 'verified': len(rows), 'errors': len(missing),
                                 'coverage_ratio': round(len(rows)/len(codes), 6)},
                    'rows': sorted(rows.values(), key=lambda r: r['code']), 'errors': missing}
        ev['close_collection'] = snapshot['coverage']
        save(ev)
        cache.write_text(json.dumps(snapshot, ensure_ascii=False))
        try:
            validate_snapshot(snapshot, T, 'sina_close_snapshot')
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(snapshot, ensure_ascii=False) + '\n')
        except ValueError as e:
            ev['snapshot_error'] = str(e)
            ev['partial_close_path'] = str(cache.relative_to(ROOT))
            print('snapshot_partial', snapshot['coverage'], list(failures.items())[:3], flush=True)
    ev['snapshot_path'] = str(target.relative_to(ROOT)) if target.exists() else None
    ev['snapshot_coverage'] = snapshot['coverage']
    print('snapshot', snapshot['coverage'], flush=True)
    em = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    jobs = [
        ('lhb', em, {'reportName': 'RPT_DAILYBILLBOARD_DETAILS', 'columns': 'ALL', 'filter': f"(TRADE_DATE='{T}')", 'pageSize': 500, 'source': 'WEB', 'client': 'WEB'}, None),
        ('indices', 'https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688', None, 'gb18030'),
        ('sectors', 'https://push2.eastmoney.com/api/qt/clist/get', {'pn': 1, 'pz': 100, 'fs': 'm:90+t:2', 'fltt': 2, 'fields': 'f12,f14,f2,f3,f6,f104,f105,f124', 'fid': 'f3', 'po': 1}, None),
        ('limitup', 'https://push2ex.eastmoney.com/getTopicZTPool', {'ut': '7eea3edcaed734bea9cbfc24409ed9893', 'dpt': 'wz.ztzt', 'Pageindex': 0, 'pagesize': 1000, 'sort': 'fbt:asc', 'date': T.replace('-', '')}, None),
        ('sse', 'https://query.sse.com.cn/infodisplay/showTradePublicFile.do', {'jsonCallBack': '', 'isPagination': 'false', 'dateTx': T, 'pageHelp.pageSize': 200, 'pageHelp.pageNo': 1}, None),
        ('szse', 'https://www.szse.cn/api/report/ShowReport/data', {'SHOWTYPE': 'JSON', 'CATALOGID': '1802_xxpl', 'txtStart': T, 'txtEnd': T, 'tab1PAGENO': 1}, None),
    ]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, d in ex.map(capture, jobs):
            ev[k] = d
            print(k, d.get('error', 'ok'), flush=True)
            save(ev)
    lhb = ev.get('lhb', {}).get('data', {}).get('result', {}).get('data', [])
    ev['seats'] = {}
    seat_jobs = []
    for code in sorted({r['SECURITY_CODE'] for r in lhb if r['SECURITY_CODE'].startswith(('0', '3', '6'))}):
        for side in ['BUY', 'SELL']:
            seat_jobs.append((code + ':' + side, em, {'reportName': 'RPT_BILLBOARD_DAILYDETAILS' + side, 'columns': 'ALL', 'filter': f"(TRADE_DATE='{T}')(SECURITY_CODE=\"{code}\")", 'pageSize': 100, 'source': 'WEB', 'client': 'WEB'}, None))
    with ThreadPoolExecutor(max_workers=10) as ex:
        for n, (k, d) in enumerate(ex.map(capture, seat_jobs)):
            code, side = k.split(':')
            ev['seats'].setdefault(code, {})[side] = d
            if n % 20 == 0:
                print('seat_queries', n+1, flush=True)
                save(ev)
    ev['completed_at'] = now()
    save(ev)
    print('context_complete', len(ev['seats']), flush=True)


if __name__ == '__main__':
    main()
