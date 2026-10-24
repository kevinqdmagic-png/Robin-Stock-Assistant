"""Collect bounded weekend evidence; reuse immutable T23 research, no fresh signals."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json
import re
import subprocess
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/research/combined-pair-20261023-weekend-evidence.json'
TMP = ROOT / 'tmp/pdfs/combined-20261023'
BASE = 'https://robin-stock-api-production.up.railway.app'
T = '2026-10-23'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'}
TARGETS = {'300184': '力源信息', '300503': '昊志机电', '002241': '歌尔股份',
           '002354': '天娱数科', '002747': '埃斯顿', '002009': '天奇股份',
           '002724': '海洋王', '603278': '大业股份'}


def now():
    return datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def request_api(item):
    name, path = item
    started = now()
    try:
        response = requests.get(BASE + path, timeout=28)
        response.raise_for_status()
        payload = response.json()
        if not payload.get('ok'):
            raise ValueError('API did not return ok')
        return name, {'source': BASE + path, 'retrieved_at': now(), 'payload': payload}
    except Exception as exc:
        return name, {'source': BASE + path, 'started_at': started, 'failed_at': now(),
                      'error': type(exc).__name__ + ': ' + str(exc)}


def announcements(item):
    code, name = item
    url = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
    params = {'pageNum': 1, 'pageSize': 30, 'column': 'sse' if code.startswith('6') else 'szse',
              'tabName': 'fulltext', 'stock': '', 'searchkey': name,
              'seDate': '2026-10-01~2026-10-24', 'isHLtitle': 'true'}
    try:
        r = requests.post(url, data=params, headers=HEADERS, timeout=28)
        r.raise_for_status()
        body = r.json()
        rows = [a for a in body.get('announcements') or [] if a.get('secCode') == code]
        for row in rows:
            row['plain_title'] = re.sub('<[^>]+>', '', row.get('announcementTitle', ''))
            row['official_pdf_url'] = 'https://static.cninfo.com.cn/' + row['adjunctUrl']
            row['listing_date_cn'] = datetime.fromtimestamp(row['announcementTime'] / 1000,
                                                            ZoneInfo('Asia/Shanghai')).date().isoformat()
        return code, {'code': code, 'name': name, 'source': url, 'query': params,
                      'retrieved_at': now(), 'totalAnnouncement': body.get('totalAnnouncement'),
                      'matched_count': len(rows), 'has_more': body.get('hasMore'), 'rows': rows}
    except Exception as exc:
        return code, {'code': code, 'name': name, 'source': url, 'query': params,
                      'retrieved_at': now(), 'error': type(exc).__name__ + ': ' + str(exc)}


def download_pdf(item):
    key, url = item
    try:
        r = requests.get(url, headers=HEADERS, timeout=28)
        r.raise_for_status()
        if not r.content.startswith(b'%PDF'):
            raise ValueError('not a PDF response')
        path = TMP / (key + '.pdf')
        path.write_bytes(r.content)
        textpath = path.with_suffix('.txt')
        subprocess.run(['pdftotext', '-layout', str(path), str(textpath)], check=True,
                       timeout=15, capture_output=True)
        text = textpath.read_text(encoding='utf-8')
        return key, {'source': url, 'retrieved_at': now(), 'bytes': len(r.content),
                     'sha256': hashlib.sha256(r.content).hexdigest(), 'text': text,
                     'local_source_path': str(path.relative_to(ROOT)), 'text_extraction': 'pdftotext-layout'}
    except Exception as exc:
        return key, {'source': url, 'retrieved_at': now(), 'error': type(exc).__name__ + ': ' + str(exc)}


def parallel(items, fn, workers=4):
    result = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, x) for x in items]
        for future in as_completed(futures):
            key, value = future.result()
            result[key] = value
    return result


def main():
    if OUT.exists():
        raise RuntimeError('Evidence already collected: do not overwrite a frozen run')
    started = now()
    TMP.mkdir(parents=True, exist_ok=True)
    research = load('backend/data/research.json')
    runs = load('backend/data/task_runs.json')
    expected = {task: f'{task.replace("_", "-")}-20261023-close-v1'
                for task in ('market_review', 'volume_price', 'low_position', 'dragon_tiger')}
    reports = {r['id']: r for r in research['items']}
    dependencies = {}
    for task, report_id in expected.items():
        report = reports[report_id]
        assert report['date'] == T and report['task_id'] == task
        assert report.get('eligible_for_integrated_research') is True
        completed = [r for r in runs['items'] if r['task_id'] == task and r['date'] == T
                     and r['status'] == 'completed' and report_id in r['report_ids']]
        assert completed
        dependencies[task] = {'report_id': report_id, 'date': T,
                              'published_at': report['published_at'],
                              'data_cutoff_at': report.get('data_cutoff_at'),
                              'report_type': report.get('report_type'),
                              'report_rule_version': report.get('rule_version', report.get('research_rule_version')),
                              'body_sha256': hashlib.sha256(report['body'].encode()).hexdigest(),
                              'completed_receipts': completed, 'sources': report['sources']}
    assert not any(r.get('task_id') == 'combined_pair' and r['date'] == T
                   and r.get('eligible_for_integrated_research') is True for r in research['items'])
    prior = reports['limitup-single-20261023-close-v2']
    assert prior['planned_entry_date'] == '2026-10-26' and prior['research_rule_version'] == 'limitup_single_v2'
    vp = load('docs/research/volume-price-20261023-close-evidence.json')
    source_path = ROOT / 'docs/research/completion-20261023-evidence.json.gz'
    complete = json.loads(gzip.decompress(source_path.read_bytes()))
    api = parallel([('health', '/health'), ('tasks', '/api/tasks'),
                    ('reports_t23', '/api/research?date=2026-10-23&limit=100'),
                    ('receipts', '/api/task-runs?limit=100'),
                    ('combined_reports', '/api/research?task=combined_pair&limit=100')], request_api)
    announcements_data = parallel(TARGETS.items(), announcements)
    pdfs = {'002241-q3': 'https://static.cninfo.com.cn/finalpage/2026-10-24/1225619737.PDF'}
    for code, item in announcements_data.items():
        rows = item.get('rows', [])
        relevant = [r for r in rows if any(s in r['plain_title'] for s in
                    ('第三季度报告', '减持', '异常波动', '风险提示', '招商引资', '业绩预告'))]
        for row in relevant[:2]:
            key = code + '-' + row['adjunctUrl'].split('/')[-1].split('.')[0]
            if code == '002241' and '第三季度报告' in row['plain_title']:
                continue
            pdfs[key] = row['official_pdf_url']
    documents = parallel(pdfs.items(), download_pdf)
    recommendation_rows = [r for r in load('backend/data/recommendations.json')['items']
                           if r.get('strategy') == 'combined_limitup_watch'
                           or r.get('task_id') == 'limitup_single']
    evidence = {
        'schema_version': 1, 'research_date': T, 'planned_entry_date': '2026-10-26',
        'earliest_legal_exit_if_bought': '2026-10-27', 'started_at': started,
        'collected_at': now(), 'execution_context': 'weekend_reopening_maintenance_no_weekend_signal',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'dependency_audit': dependencies, 'api_readback': api,
        'reused_limitup_report': {'report_id': prior['id'], 'date': prior['date'],
                                'planned_entry_date': prior['planned_entry_date'], 'published_at': prior['published_at'],
                                'candidate_count': prior['candidate_count'],
                                'completed_receipts': [r for r in runs['items']
                                    if r['task_id'] == 'limitup_single' and r['date'] == T
                                    and r['status'] == 'completed' and prior['id'] in r['report_ids']]},
        'frozen_source_archive': {'path': str(source_path.relative_to(ROOT)),
                                  'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest()},
        'market': vp['market'], 'coverage': vp['coverage'],
        'broad_pool': vp['broad_pool'], 'deep_pool': vp['deep_pool'],
        'recomputed_broad_pool': complete['recomputed_broad_pool'],
        'prior_whole_pool': vp['previous_pool_validation'],
        'prior_pool_statistics': vp['previous_pool_statistics'],
        'dragon_selected': complete['dragon_selected'],
        'low_summary': complete['low_summary'], 'repeat_audit': complete['repeat_audit'],
        'original_recommendations_with_immutable_results': recommendation_rows,
        'official_announcement_queries': announcements_data, 'official_pdf_documents': documents,
        'limitations': ['Frozen T23 source data reused; no T24 trading scan or new market sample.',
                        'Minute price points are not OHLC, order-book queues or actual fills.',
                        'Provider adjustment and MA window methods remain distinct; no backward rule rewrite.',
                        'CNINFO query results cover only the named company/date window, not all risk categories.']}
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(OUT.relative_to(ROOT)), 'started_at': started, 'collected_at': evidence['collected_at'],
          'prerequisites': list(dependencies), 'limitup_reused': prior['id'],
          'api': {k: v.get('error', 'ok') for k, v in api.items()},
          'announcements': {k: {'matched': v.get('matched_count'), 'error': v.get('error'),
                                      'titles': [x['plain_title'] for x in v.get('rows', [])]} for k, v in announcements_data.items()},
          'pdfs': {k: {'bytes': v.get('bytes'), 'error': v.get('error')} for k, v in documents.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
