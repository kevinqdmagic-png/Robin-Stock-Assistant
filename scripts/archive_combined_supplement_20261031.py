"""Append reviewed weekend evidence without changing any frozen trade signal."""
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import copy
import gzip
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from learning_loop import is_session, latest_completed_session, nth_session_after

START = '2026-10-30T17:12:08+00:00'
T = '2026-10-30'
D = '2026-11-02'
DAY = '2026-10-31'
TAG = '20261031'
TMP = 'tmp/recheck-20261030T1712/'
EVIDENCE = 'docs/research/combined-weekend-20261031-evidence.json.gz'
EXPERIMENT = 'docs/research/shadow-experiments-20261102-v1.json'
IDS = {'combined_pair': 'combined-pair-20261031-weekend-supplement-v1',
       'limitup_single': 'limitup-single-20261031-weekend-supplement-v1'}


def load(path):
    return json.loads((ROOT / path).read_text())


def table(headers, rows):
    return '\n'.join(['|' + '|'.join(headers) + '|', '|' + '|'.join(['---'] * len(headers)) + '|'] +
                     ['|' + '|'.join(str(v).replace('|', '/').replace('\n', '；') for v in row) + '|' for row in rows])


def main():
    review = load(TMP + 'analyst-supplement.json')
    assert review['analysis_reviewed']
    now = datetime.now(timezone.utc)
    cn = now.astimezone(ZoneInfo('Asia/Shanghai'))
    stamp = cn.isoformat(timespec='seconds')
    assert cn.date().isoformat() == DAY and not is_session(cn.date())
    assert latest_completed_session(cn).isoformat() == T
    assert nth_session_after(date.fromisoformat(T), 1).isoformat() == D
    assert nth_session_after(date.fromisoformat(D), 1).isoformat() == '2026-11-03'
    filings = load(TMP + 'new-original-filings.json')
    queries = load(TMP + 'announcements.json')
    assert queries['ok'] == queries['requested_codes'] == 20
    assert len(filings) == 10 and all(f['ok'] for f in filings.values())
    assert all(datetime.fromisoformat(f['retrieved_at_utc']) <= now for f in filings.values())
    research = load('backend/data/research.json')
    runs = load('backend/data/task_runs.json')
    catalog = load('backend/data/research_stocks.json')
    assert not any(r['id'] in IDS.values() for r in research['items']), 'reuse existing supplement'
    freeze_paths = ['docs/research/shadow-experiments-' + s + '-v1.json'
                    for s in ['20261029', '20261030', '20261102']]
    freeze_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in freeze_paths}
    exp = load(EXPERIMENT)
    assert exp['frozen_at'] == '2026-10-30T18:20:11+08:00'
    assert [s['code'] for s in exp['signals']] == ['000568', '600510', '600258']
    before_reports = copy.deepcopy(research['items'])
    original_full = {r['task_id']: r['id'] for r in research['items'] if r['date'] == T and
                     r.get('report_type') in ['full_daily_research', 'full_trading_research']}
    assert set(original_full) >= {'market_review', 'volume_price', 'low_position', 'dragon_tiger',
                                  'combined_pair', 'limitup_single'}
    common = (
        f'这是{DAY}休市维护中的原公告补证，不是休市日正常交易复盘。实际完成北京时间{stamp}；'
        f'最近已收盘市场T={T}，原计划D={D}，若D入场最早2026-11-03可卖。'
        '原始行情截止T日15:00，本次没有新报价、成交或收益。'
        '原四模块及两个裁决均已完成并有真实回执，复用原版，不新造同T完整报告。'
        '原影子于10月30日18:20:11冻结，以下是本轮实际取得后才追加的证据，不反向填入原冻结理由。'
    )
    boundary = (
        '核验范围为20只原信号、对照或参照公司的10月30—31日公告查询；精确代码过滤，20/20查询成功。'
        '其中10份新增核验原PDF均HTTP成功，逐份URL、哈希、元数据日期、实际取得时间保留；'
        '并非全A重新扫描、全行业成分或风险穷尽。URL/公告标注日期不证明精确首次公开时刻，'
        '不能推定这些材料在原18:20冻结前一定不可得；只按本轮实际可得时间使用。'
        '非重要会议通知、募集专户核查等查询行原样保存，未假装全部形成独立选股结论。'
    )
    unchanged = (
        '正式综合和正式打板原裁决仍各0只；不重选、不换排序、不新增买入许可。'
        '综合影子泸州老窖000568（T参考77.07）和黑牡丹600510（6.46）、打板影子首旅酒店600258（12.43）'
        '仍按原清单、原同伴、原触发/失效/放弃与固定退出规则检验，参考价不是成交价。'
        '三只均为普通主板10%研究样本，D真实证券状态、涨停价和竞价/盘口仍须届时核实。'
        '财报、融资注册或风险提示均不能单独证明D已触发或已买到。'
        'H1/H2/H3、combined_limitup_watch_v5和limitup_single_v2原版本保持；本次不作规则优化。'
    )
    previous = (
        '上一批中国卫星600118、景津装备603279、桂林三金002275在D30的原必要条件均未满足，'
        '已核实成交0；更早D29纽威股份603699、铁流股份603926、泰山石油000554的原未触发结论保留。'
        '本次没有新的已完成交易日或价格节点，不重复追加T30价格结果、不新增量价/低位或影子样本。'
        '独立计划日观察仍为2日；新D1102尚未开市。T+1/T+2/T+5/T+10未到节点保持待验证，'
        '没有分钟/逐笔、队列、费用和成交证据就不计算可执行净收益，也不以涨停或日最高价代替盈利。'
    )
    technical = (
        '同时核验现有观察台账的真实故障：GitHub Daily forward learning运行41096518918的观察计算步骤成功，'
        '提交步骤因binascii.Error: Only base64 data is allowed失败。'
        'safe_github_update原先去除字面反斜杠n，未去除GitHub Base64内的真实LF/CRLF。'
        '修复只去除CR/LF，仍保持strict Base64、原blob SHA并发比较、历史只追加和分支冲突保护；'
        '不忽略非法字符，不强推、不绕过权限。新增4项回归验证覆盖LF/CRLF、空inline后的Blob回退、'
        '历史删除阻断及非法字符不写入；旧版可复现失败，修复后11项针对性测试与216项全部后端测试通过。'
        '此处仅记录本轮发布前的修复验证；真实工作流恢复须在修复上线后另查实际运行、提交和API，'
        '不能提前称旧失败运行成功。未改变任何调度，也未恢复量化研究、训练权重或自动下单。'
    )
    sources = [EVIDENCE, EXPERIMENT,
               'docs/research/shadow-validation-20261030-v1.json',
               'https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/actions/runs/41096518918'] + [f['source'] for f in filings.values()]
    bodies = {}
    for task in IDS:
        facts = review['facts'] if task == 'combined_pair' else [f for f in review['facts'] if f['code'] in
                                                               {'603131', '600754', '002275', '600715'}]
        judgments = table(['核验对象', '原公告事实', '对原研究的支持、反证及边界'],
                          [[f['code'] + ' ' + f['name'], f['verified_fact'], f['research_impact']] for f in facts])
        bodies[task] = '\n\n'.join([common, '一、去重及信息边界\n' + boundary,
                                    '二、原公告核验与逐项影响\n' + judgments,
                                    '三、正式空仓与原影子条件\n' + unchanged,
                                    '四、上一批和样本计数\n' + previous,
                                    '五、归档故障及修复的实际状态\n' + technical,
                                    '六、下一实际交易日\n11月2日只按原冻结卡核验竞价、回踩/承接、'
                                    '同伴及高标状态；证券状态、真实上限、连续窗口或成交证据缺失则不确认触发/成交。'
                                    '20—30个实际交易日首轮复核仍未到，不宣称收益优势。'
                                    '本补证eligible=false，不能替代任何同T完整前置、原最终裁决或正式推荐。'])
        rid = IDS[task]
        run_id = task.replace('_', '-') + '-' + TAG + '-scheduled-supplement-v1'
        title = ('休市综合补证｜黑牡丹融资注册、酒店同伴财报与高标风险' if task == 'combined_pair' else
                 '休市打板v2补证｜酒店同伴财报及高标风险，原D1102冻结不变')
        summary = ('核验20只公告查询及10份原PDF；17.1亿注册不等于资金到账，原正式0和影子冻结不变。'
                   if task == 'combined_pair' else
                   '锦江酒店经营补证与高标风险追加；不替代D盘口/成交证据，首旅原影子卡和正式0不变。')
        research['items'].append(dict(id=rid, date=DAY, market_date=T, task_id=task, track='market_review',
                                     run_id=run_id, title=title, summary=summary, body=bodies[task], sources=sources,
                                     report_type='research_supplement', eligible_for_integrated_research=False,
                                     analysis_completed=True, status='completed', published_at=stamp, recorded_at=stamp,
                                     market_data_cutoff_at=T + 'T15:00:00+08:00', data_cutoff_at=stamp,
                                     planned_entry_date=D, earliest_legal_exit_date_if_bought='2026-11-03',
                                     provenance='new_evidence_reviewed_after_original_freeze',
                                     candidate_count=0, recommendation_ids=[], original_report_ids=[original_full[task]],
                                     maintained_shadow_experiment_file=EXPERIMENT, new_shadow_candidates=0,
                                     new_price_observations=0, original_freeze_preserved=True,
                                     not_a_new_trading_day_report=True, evidence_file=EVIDENCE,
                                     research_rule_version='weak_market_shadow_v1',
                                     parent_rule_version='limitup_single_v2' if task == 'limitup_single' else 'combined_limitup_watch_v5'))
        runs['items'].append(dict(id=run_id + '-completed', run_id=run_id, task_id=task, date=DAY, market_date=T,
                                  trigger='scheduled', started_at=START, completed_at=stamp, recorded_at=stamp,
                                  status='completed', analysis_completed=True, eligible_for_integrated_research=False,
                                  summary=summary, report_ids=[rid], recommendation_ids=[],
                                  delivery_status='repository_prepared_not_yet_verified',
                                  sources=[EVIDENCE, EXPERIMENT], does_not_replace_original_full_research=True))
    fact_by = {f['code']: f for f in review['facts']}
    history_ids = []
    for code in review['catalog_codes_for_new_history']:
        stock = next(s for s in catalog['items'] if s['code'] == code)
        fact_code = {'000568': '000596', '600258': '600754'}.get(code, code)
        fact = fact_by[fact_code]
        parent_task = 'limitup_single' if code == '600258' else 'combined_pair'
        ep = dict(id=f'research-stock-{code}-20261031-filing-supplement-v1', date=DAY, market_date=T,
                  recorded_at=stamp, title='原公告补证，原冻结信号不回写',
                  reason=stock['name'] + '新增原公告核验或原同伴补证，保持正式空仓与原研究条件。',
                  evidence_status='original_peer_filing_verified' if fact_code != code else 'original_company_filing_verified',
                  fact_note=(('此处财务/公告对象为原同伴' + fact['name'] + '，不是' + stock['name'] + '自身财务。')
                             if fact_code != code else '') + fact['verified_fact'],
                  validation=[fact['research_impact'], '按原D1102卡继续核验；未到价格节点不填未来结果'],
                  risk='未改变原风险、价格、排序和退出条件；融资注册/财报/异动均不构成买入、成交或净收益证明。',
                  report_ids=[IDS[parent_task]], sources=[filings[k]['source'] for k in fact['filing_keys']] + [EVIDENCE])
        stock['history'].append(ep)
        history_ids.append({'code': code, 'history_id': ep['id'], 'report_id': IDS[parent_task]})
    catalog['updated_at'] = stamp
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    evidence = dict(base_main=base, actual_started_at_utc=START, actual_completed_at=stamp, market_T=T,
                    maintenance_date_cn=DAY, planned_D=D, original_freeze_hashes=freeze_hashes,
                    original_signal_ids=[s['id'] for s in exp['signals']], original_full_report_ids=original_full,
                    preflight_online=load(TMP + 'online-proof.json'), announcement_queries=queries,
                    original_filings=filings, analyst_review=review, existing_stock_history_updates=history_ids,
                    targeted_regression_tests_passed=11, all_backend_tests_passed=216,
                    real_failed_workflow_retry_status='not_yet_run',
                    PDF_visual_pages_reviewed=['600510-mtn:1', '603131-risk:1', '600754-q3:1', '603699-q3:1'],
                    original_price_and_trade_results_unchanged=True)
    encoded = gzip.compress(json.dumps(evidence, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode(), mtime=0)
    manifest = dict(base_main=base, actual_started_at_utc=START, completed_at=stamp, market_T=T,
                    maintenance_date_cn=DAY, planned_D=D, report_ids=list(IDS.values()),
                    existing_stock_history_updates=history_ids, new_recommendations=0, new_shadow_candidates=0,
                    new_sample_cohorts=0, new_price_or_trade_results=0, original_freeze_hashes=freeze_hashes,
                    task_registry_and_schedules_changed=False, quant_research_restored=False,
                    evidence_file=EVIDENCE, evidence_sha256=hashlib.sha256(encoded).hexdigest())
    docs = {'backend/data/research.json': research, 'backend/data/task_runs.json': runs,
            'backend/data/research_stocks.json': catalog, 'app/src/main/assets/research_stocks.json': catalog,
            'docs/research/combined-weekend-20261031-publication-manifest.json': manifest,
            'docs/research/combined-weekend-20261031-analyst-review.json': review}
    assert research['items'][:len(before_reports)] == before_reports
    assert datetime.fromisoformat(START) <= datetime.fromisoformat(stamp) <= datetime.now(timezone.utc)
    for path, value in docs.items():
        (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (ROOT / EVIDENCE).write_bytes(encoded)
    for task, body in bodies.items():
        (ROOT / ('docs/research/' + IDS[task] + '.md')).write_text(
            '# ' + next(r['title'] for r in research['items'] if r['id'] == IDS[task]) + '\n\n' + body +
            '\n\n来源：\n\n' + '\n'.join('- ' + source for source in sources) + '\n')
    assert freeze_hashes == {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in freeze_paths}
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
