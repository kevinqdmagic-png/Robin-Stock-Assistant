"""Append successful retries beside the frozen first-pass evidence."""
from collect_combined_20261023_weekend import ROOT, OUT, TMP, TARGETS, now, parallel, request_api, announcements, download_pdf
import json


def main():
    destination = ROOT / 'docs/research/combined-pair-20261023-weekend-supplement.json'
    if destination.exists():
        raise RuntimeError('Supplement already collected; do not overwrite')
    original = json.loads(OUT.read_text(encoding='utf-8'))
    started = now()
    api_paths = [('health', '/health'), ('tasks', '/api/tasks'),
                 ('reports_t23', '/api/research?date=2026-10-23&limit=100'),
                 ('receipts', '/api/task-runs?limit=100')]
    api = parallel([(k, p) for k, p in api_paths if original['api_readback'][k].get('error')], request_api, workers=2)
    queries = parallel([(c, n) for c, n in TARGETS.items()
                        if original['official_announcement_queries'][c].get('error')], announcements, workers=3)
    # The source list uses “三季度” for this filing; use its verified original URL.
    pdfs = {'300503-project': 'https://static.cninfo.com.cn/finalpage/2026-10-21/1225612462.PDF',
            '300184-q3': 'https://static.cninfo.com.cn/finalpage/2026-10-23/1225615680.PDF'}
    for code, item in queries.items():
        relevant = [r for r in item.get('rows', []) if any(s in r['plain_title'] for s in
                    ('第三季度报告', '三季度报告', '减持', '异常波动', '风险提示', '招商引资', '业绩预告'))]
        for row in relevant[:2]:
            if code == '002241' and '第三季度报告' in row['plain_title']:
                continue
            pdfs[code + '-' + row['adjunctUrl'].split('/')[-1].split('.')[0]] = row['official_pdf_url']
    for key, item in original['official_pdf_documents'].items():
        if item.get('error'):
            pdfs[key] = item['source']
    documents = parallel(pdfs.items(), download_pdf, workers=3)
    record = {'started_at': started, 'completed_at': now(), 'supplements': str(OUT.relative_to(ROOT)),
              'purpose': 'Bounded retry of transient timeouts; first-pass errors remain immutable.',
              'api_readback': api, 'official_announcement_queries': queries, 'official_pdf_documents': documents}
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(destination.relative_to(ROOT)),
          'api': {k:v.get('error','ok') for k,v in api.items()},
          'announcements': {k:{'matched':v.get('matched_count'),'error':v.get('error'),
                                 'titles':[r['plain_title'] for r in v.get('rows',[])]} for k,v in queries.items()},
          'pdfs': {k:{'bytes':v.get('bytes'),'error':v.get('error')} for k,v in documents.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
