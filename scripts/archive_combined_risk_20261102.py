"""Append verified premarket issuer evidence without changing frozen experiments."""
import copy
import gzip
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from learning_loop import latest_completed_session, nth_session_after

TMP = ROOT / 'tmp/recheck-20261101T1720'
START = '2026-11-01T17:20:26+00:00'
DAY, T, D = '2026-11-02', '2026-10-30', '2026-11-02'
EXPERIMENT = 'docs/research/shadow-experiments-20261102-v1.json'
EVIDENCE = 'docs/research/combined-risk-20261102-evidence.json.gz'
MANIFEST = 'docs/research/combined-risk-20261102-publication-manifest.json'
SOURCE = 'https://static.cninfo.com.cn/finalpage/2026-11-02/1225650401.PDF'
IDS = {'combined_pair': 'combined-pair-20261102-premarket-risk-supplement-v1',
       'limitup_single': 'limitup-single-20261102-premarket-risk-supplement-v1'}


def load(path):
    return json.loads((ROOT / path).read_text())


def main():
    now = datetime.now(timezone.utc)
    cn = now.astimezone(ZoneInfo('Asia/Shanghai'))
    stamp = cn.isoformat(timespec='seconds')
    assert cn.date().isoformat() == DAY and (cn.hour, cn.minute) < (9, 15)
    assert latest_completed_session(cn).isoformat() == T
    assert nth_session_after(date.fromisoformat(T), 1).isoformat() == D
    assert nth_session_after(date.fromisoformat(D), 1).isoformat() == '2026-11-03'
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    meta = json.loads((TMP / '002724-1225650401-metadata.json').read_text())
    assert meta['http_status'] == 200 and meta['url'] == SOURCE
    assert datetime.fromisoformat(meta['retrieved_at_utc']) <= now
    assert hashlib.sha256((TMP / '002724-1225650401.pdf').read_bytes()).hexdigest() == meta['sha256']
    queries = json.loads((TMP / 'announcements.json').read_text())
    online = json.loads((TMP / 'online-proof.json').read_text())
    assert queries['ok'] == queries['requested_codes'] == 20
    new_rows = [(c, a['adjunctUrl']) for c, q in queries['queries'].items()
                for a in q['not_in_original_frozen_query']]
    assert new_rows == [('002724', 'finalpage/2026-11-02/1225650401.PDF')]
    for query in queries['queries'].values():
        assert not query['payload'].get('hasMore')
        assert int(query['payload'].get('totalpages') or 0) <= 1
    assert len(online['full_T30_modules']) == 6 and online['data_revision_matches']
    exp = load(EXPERIMENT)
    assert exp['frozen_at'] == '2026-10-30T18:20:11+08:00'
    assert [s['code'] for s in exp['signals']] == ['000568', '600510', '600258']
    protected = ['backend/data/' + n for n in ['recommendations.json', 'tasks.json',
                 'volume_price_samples.json', 'low_position_samples.json', 'learning.json',
                 'capital_watch.json', 'research_stocks.json']]
    protected += ['app/src/main/assets/research_stocks.json']
    before = {p: (ROOT / p).read_bytes() for p in protected if (ROOT / p).exists()}
    freezes = ['docs/research/shadow-experiments-' + x + '-v1.json'
               for x in ['20261029', '20261030', '20261102']]
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in freezes}
    research, runs = load('backend/data/research.json'), load('backend/data/task_runs.json')
    assert not any(s['code'] == '002724' for s in load('backend/data/research_stocks.json')['items'])
    old_research, old_runs = copy.deepcopy(research['items']), copy.deepcopy(runs['items'])
    assert not any(r['id'] in IDS.values() for r in research['items']), 'reuse existing supplement'
    full = {r['task_id']: r for r in research['items'] if r['date'] == T
            and r.get('analysis_completed') is True and r.get('status') == 'completed'
            and r.get('report_type') in ['full_daily_research', 'full_trading_research']}
    assert set(full) >= {'market_review', 'volume_price', 'low_position', 'dragon_tiger',
                         'combined_pair', 'limitup_single'}
    for task in ['market_review', 'volume_price', 'low_position', 'dragon_tiger']:
        assert full[task]['eligible_for_integrated_research'] is True
    facts = {
        'issuer_code': '002724', 'announcement_number': '2026-054', 'document_date': DAY,
        'observation_period': ['2026-10-19', '2026-10-30'],
        'ten_session_cumulative_closing_return_deviation_pct': 100.02,
        'issuer_static_PE_quoted_in_filing': 94.91,
        'issuer_trailing_PE_quoted_in_filing': 216.79,
        'industry_static_PE_quoted_in_filing': 18.90,
        'industry_trailing_PE_quoted_in_filing': 17.99,
        'PE_underlying_date_quoted_in_filing': '2026-10-29',
        'PE_independently_recalculated': False,
        'five_recent_turnover_pct_in_filing_order': [25.66, 28.85, 24.15, 20.99, 22.85],
        'YTD2026_deducted_net_profit_CNY_10000': -1630.31,
        'YTD2026_deducted_net_profit_yoy_pct': -189.97,
        'issuer_business_clarifications': [
            'AI smart-lighting revenue is limited and not material to overall performance',
            'Radiation-certified lamps are used in nuclear islands but are not core production equipment; issuer denies the nuclear-power concept',
            'No application products capable of ten-thousand-metre deep-sea operation; issuer denies the deep-sea technology concept'],
        'verified_source_pages': [1, 3], 'new_quote_or_fill': False,
    }
    sources = [SOURCE, EVIDENCE, EXPERIMENT, 'docs/research/shadow-validation-20261030-v1.json']
    opening = (f'盘前追加补证，实际完成北京时间{stamp}；T={T}，计划D={D}。'
               '原四模块与综合、打板裁决已完成并核验6/6，本报告eligible_for_integrated_research=false，'
               '不能替代完整前置或视为新一轮选股。资料为海洋王002724公告2026-054。'
               '文件落款和巨潮元数据日期均为11月2日；本轮实际取得PDF为北京时间11月2日01:22:00.969586，'
               '这是本轮可证明的取得时间，互联网首次公开时刻未独立核实。不得把文件日期或本次事实倒填到10月30日18:20:11原冻结。')
    fact_text = ('一、原始公告事实及口径\n'
                 '公告称10月19日至30日连续10个交易日收盘价格涨幅偏离值累计100.02%，达到严重异常波动情形。'
                 '100.02%是相对基准的累计偏离指标，不是原始股价区间收益，也不是十连板。'
                 '公告援引10月29日中证行业数据：公司静态/滚动市盈率94.91/216.79倍，行业18.90/17.99倍；'
                 '本轮核实的是公告如此记载，未独立重算中证估值，不把这些估值口径与扣非利润混为一谈。'
                 '公告按顺序列近五交易日换手25.66%、28.85%、24.15%、20.99%、22.85%，不能凭高换手断言资金身份或筹码锁定。'
                 '前三季扣非净利润为亏损1630.31万元，同比下降189.97%，与原T30研究已记录的盈利质量风险一致。\n'
                 '业务澄清：公司称AI智慧照明收入体量有限，尚不足以显著影响总体业绩；耐辐照灯具虽在核岛使用，'
                 '照明不属于主生产设备，公司否认据此归入核电概念；没有可用于万米深海作业的应用产品，并否认深海科技概念。'
                 '这些是发行人披露的业务边界，不能继续用题材标签代替已确认收入。公司核查称未有应披露未披露重大事项，'
                 '这不是对股价安全、低估或不存在全部风险的保证。')
    interpretation = ('二、对原研究的支持、反证与限制\n'
                      '海洋王原本是高位置、正尾盘但未封板的H1对照和落选对象，并非正式或影子入选。'
                      '公告强化高位换手、盈利质量与题材映射的风险反证，但只是对照股的新证据，'
                      '不能推导11月2日必跌、风险已扩散或低位实验一定胜出。原海洋王对照继续保留，'
                      '其后失败、停牌、无法成交和缺失结果同样进入原分母；不因风险公告把它剔除或事后换成赢家。'
                      '不新增参照股票、阈值或事后放弃规则；原信号中“高标风险扩散”等条件仅按原定参考对象和原窗口验证，'
                      '不能单凭本公告判定三只影子已失效。海洋王不在当前48只研究自选档案，本次不新增自选或默认关注。')
    validation = ('四、先验证、统计与执行边界\n'
                  'D29/D30原必要条件未满足、已核实成交0的结果保持；原完整深筛池与失败样本保留。'
                  '目前仅2个已观察计划交易日，D1102尚未开盘。本补证不新增计划日、证券日、影子候选或成交数；'
                  'T+1/T+2/T+5/T+10、MFE/MAE无新成熟价格窗口，不补写结果。'
                  '正式综合及打板各0只和原空仓事件不变，不再计一个新的空仓策略事件。'
                  '若D真实入场，最早11月3日实际交易日卖出；当日炸板无法当日止损，跌停、停牌或队列可能无法退出。'
                  '缺分钟/逐笔、排队及两侧成交证据只报可核日线观察，涨停价或最高价不能当成可实现盈利。'
                  'H1/H2/H3、combined_limitup_watch_v5与limitup_single_v2不改版；原同口径沪深300及全部对照保留，'
                  '流动性和行业未完全匹配的限制不变。20—30个实际交易日仅为首轮复核节点，不能据此宣称高胜率。')
    scope = ('五、来源覆盖与下一检查\n'
             '本轮20只原候选、同伴与风险参照公司公告查询均成功且无未取完页；新增精确代码公告1份，即本文件。'
             '它是有限对象补证，不是新全A扫描。真实证券状态、当日实际涨停价、竞价、分钟承接及成交队列尚待开市数据，'
             '不得用10月30日报价冒充盘前实时确认。原任务调度和量化取消状态保持；不自动下单、调权或发影子买入通知。')
    records = {}
    for task, rid in IDS.items():
        signals = [s for s in exp['signals'] if s['parent_task_id'] == task]
        structured = [dict(original_signal_id=s['id'], market_event_id=s['market_event_id'],
                           code=s['code'], name=s['name'], original_rank=s['rank'],
                           original_frozen_at=s['signal_frozen_at'], original_reference_price=s['reference_price'],
                           original_reference_price_at=s['reference_price_at'], original_condition_source=EXPERIMENT,
                           not_a_new_signal=True, is_recommendation=False, formal_buy_signal=False) for s in signals]
        table = '|原组别/序|代码/名称|原T日参考价，非新报价|本轮处理|\n|---|---|---|---|\n' + '\n'.join(
            '|'+ '|'.join([task+'/'+str(s['rank']), s['code']+' '+s['name'], str(s['reference_price']),
                          '原触发、失效、放弃、固定同伴和合法退出规则全部保留；非买入建议'])+'|' for s in signals)
        body = '\n\n'.join([opening, fact_text, interpretation,
                             '三、原影子结构化维护清单\n'+table+'\n\n原始精确区间、时间窗与证据链接以原冻结JSON为准，不改写。',
                             validation, scope])
        run_id = task.replace('_', '-')+'-20261102-scheduled-premarket-risk-supplement-v1'
        title = ('盘前综合补证' if task == 'combined_pair' else '盘前打板v2补证')+'｜海洋王严重异动与题材澄清，原冻结不变'
        summary = '核验海洋王严重异动公告及业务边界；保留H1高位对照与原正式0/影子条件，不新增交易或样本。'
        record = dict(id=rid, date=DAY, market_date=T, task_id=task, track='market_review', run_id=run_id,
                      title=title, summary=summary, body=body, sources=sources, report_type='research_supplement',
                      eligible_for_integrated_research=False, analysis_completed=True, status='completed',
                      published_at=stamp, recorded_at=stamp, data_cutoff_at=stamp,
                      market_data_cutoff_at=T+'T15:00:00+08:00', planned_entry_date=D,
                      earliest_legal_exit_date_if_bought='2026-11-03', candidate_count=0, recommendation_ids=[],
                      provenance='verified_issuer_filing_obtained_after_original_freeze_before_planned_D_open',
                      original_report_ids=[full[task]['id']],
                      original_cash_observation_id=next(c['id'] for c in exp['formal_cash_observations'] if c['task_id']==task),
                      maintained_shadow_experiment_file=EXPERIMENT, existing_shadow_conditions=structured,
                      new_shadow_candidates=0, new_price_observations=0, new_trade_observations=0,
                      original_freeze_preserved=True, not_a_new_trading_day_report=True, evidence_file=EVIDENCE,
                      research_rule_version='weak_market_shadow_v1',
                      parent_rule_version='limitup_single_v2' if task=='limitup_single' else 'combined_limitup_watch_v5',
                      codes=['002724']+[s['code'] for s in signals], reference_market_emotion='弱', emotion_as_of=T)
        research['items'].append(record); records[task] = record
        runs['items'].append(dict(id=run_id+'-completed', run_id=run_id, task_id=task, date=DAY, market_date=T,
                                 trigger='scheduled', started_at=START, completed_at=stamp, recorded_at=stamp,
                                 status='completed', summary=summary, report_ids=[rid], recommendation_ids=[],
                                 analysis_completed=True, eligible_for_integrated_research=False,
                                 delivery_status='repository_prepared_not_yet_verified', sources=[EVIDENCE, EXPERIMENT],
                                 does_not_replace_original_full_research=True))
    evidence = dict(base_main=base, actual_started_at_utc=START, completed_at=stamp, T=T, planned_D=D,
                    source_metadata=meta, verified_facts=facts, original_freeze_hashes=hashes,
                    original_full_report_ids={k:v['id'] for k,v in full.items()}, announcement_queries=queries,
                    preflight_online=online, source_availability={'document_date':DAY,
                        'retrieved_at_utc':meta['retrieved_at_utc'], 'first_publication_instant_independently_verified':False},
                    analyst_review={'original_PDF_pages_visually_checked':[1,3], 'web_fetch_failed_original_HTTP_succeeded':True,
                                    'facts_and_inferences_separated':True, 'rules_or_thresholds_changed':False,
                                    'new_existing_catalog_stock_fact_or_judgment':False},
                    original_trade_and_price_outcomes_unchanged=True)
    compressed = gzip.compress(json.dumps(evidence, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode(), mtime=0)
    manifest = dict(base_main=base, actual_started_at_utc=START, completed_at=stamp, market_T=T,
                    maintenance_date_cn=DAY, planned_D=D, report_ids=list(IDS.values()),
                    existing_stock_history_updates=[], original_freeze_hashes=hashes, new_recommendations=0,
                    new_shadow_candidates=0, new_sample_cohorts=0, new_price_or_trade_results=0,
                    task_registry_and_schedules_changed=False, quant_research_restored=False,
                    catalog_changed=False, evidence_file=EVIDENCE, evidence_sha256=hashlib.sha256(compressed).hexdigest())
    assert research['items'][:len(old_research)] == old_research and runs['items'][:len(old_runs)] == old_runs
    assert datetime.fromisoformat(START) <= datetime.fromisoformat(stamp) <= datetime.now(timezone.utc)
    for path, value in {'backend/data/research.json':research, 'backend/data/task_runs.json':runs, MANIFEST:manifest}.items():
        (ROOT/path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (ROOT/EVIDENCE).write_bytes(compressed)
    for task, record in records.items():
        (ROOT/('docs/research/'+IDS[task]+'.md')).write_text('# '+record['title']+'\n\n'+record['body']+
            '\n\n来源：\n\n'+'\n'.join('- '+s for s in sources)+'\n')
    assert all((ROOT/p).read_bytes() == b for p,b in before.items())
    assert hashes == {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in freezes}
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
