#!/usr/bin/env python3
"""Read back exact bundle reports and receipts, never infer full study completion."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import urlopen

BASE = 'https://robin-stock-api-production.up.railway.app'

def read(path):
    with urlopen(BASE + path, timeout=12) as response:
        result = json.load(response)
    if result.get('ok') is not True:
        raise ValueError('production_payload_not_ok:' + path)
    return result

def check(reports, receipts):
    health = read('/health')
    for expected in reports:
        actual = read('/api/research/' + expected['id'])['report']
        if any(actual.get(k) != v for k, v in expected.items()):
            raise ValueError('report_not_deployed:' + expected['id'])
    tasks = {row['task_id'] for row in receipts}
    by_id = {}
    for task in tasks:
        offset = 0
        while True:
            page = read('/api/task-runs?task=' + task + '&limit=100&offset=' + str(offset))
            by_id.update({row['id']: row for row in page['items']})
            if not page.get('has_more'):
                break
            offset += len(page['items'])
            if not page['items']:
                raise ValueError('receipt_pagination_stalled')
    for expected in receipts:
        actual = by_id.get(expected['id'], {})
        if any(actual.get(k) != v for k, v in expected.items()):
            raise ValueError('receipt_not_deployed:' + expected['id'])
    return {'ok': True, 'build_commit': health.get('build_commit'),
            'report_ids': [r['id'] for r in reports], 'receipt_ids': [r['id'] for r in receipts],
            'meaning': 'exact archived bodies and receipts read back; full research is separately audited'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait', type=int, default=60)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundles = [json.loads(p.read_text(encoding='utf-8')) for p in (root/'research_backfills').glob('linked-*.json')]
    reports = [r for b in bundles for r in b['research']]
    receipts = [r for b in bundles for r in b['task_runs']]
    if not bundles or not reports or not receipts:
        raise ValueError('linked_bundle_required')
    deadline = time.monotonic() + args.wait
    while True:
        try:
            result = check(reports, receipts)
            break
        except Exception as exc:
            result = {'ok': False, 'error': type(exc).__name__ + ':' + str(exc)[:240]}
            if time.monotonic() >= deadline:
                break
            time.sleep(10)
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    (root/'bundle-readback.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
