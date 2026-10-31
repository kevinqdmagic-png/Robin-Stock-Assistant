"""Append post-freeze macro evidence; never regenerate a frozen stock signal."""
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

START = '2026-10-31T17:02:13+00:00'
DAY, T, D = '2026-11-01', '2026-10-30', '2026-11-02'
TMP = ROOT / 'tmp/recheck-20261031T1702'
EXPERIMENT = 'docs/research/shadow-experiments-20261102-v1.json'
EVIDENCE = 'docs/research/combined-macro-20261101-evidence.json.gz'
MANIFEST = 'docs/research/combined-macro-20261101-publication-manifest.json'
IDS = {'combined_pair': 'combined-pair-20261101-macro-supplement-v1',
       'limitup_single': 'limitup-single-20261101-macro-supplement-v1'}


def load(path):
    return json.loads((ROOT / path).read_text())


def main():
    now = datetime.now(timezone.utc)
    cn = now.astimezone(ZoneInfo('Asia/Shanghai'))
    stamp = cn.isoformat(timespec='seconds')
    assert cn.date().isoformat() == DAY and not is_session(cn.date())
    assert latest_completed_session(cn).isoformat() == T
    assert nth_session_after(date.fromisoformat(T), 1).isoformat() == D
    assert nth_session_after(date.fromisoformat(D), 1).isoformat() == '2026-11-03'
    meta = json.loads((TMP / 'macro-source-metadata.json').read_text())
    assert len(meta) == 2
    for entry in meta.values():
        assert entry['HTTP_status'] == 200
        assert datetime.fromisoformat(entry['retrieved_at_utc']) <= now
        assert hashlib.sha256((ROOT / entry['local_raw']).read_bytes()).hexdigest() == entry['sha256']
    queries = json.loads((TMP / 'announcements.json').read_text())
    online = json.loads((TMP / 'online-proof.json').read_text())
    assert queries['ok'] == queries['requested_codes'] == 20
    assert not any(q['not_in_original_frozen_query'] for q in queries['queries'].values())
    assert len(online['full_T30_modules']) == 6 and online['data_revision_matches']
    exp = load(EXPERIMENT)
    assert exp['frozen_at'] == '2026-10-30T18:20:11+08:00'
    assert [s['code'] for s in exp['signals']] == ['000568', '600510', '600258']
    before = {p: (ROOT / p).read_bytes() for p in
              ['backend/data/recommendations.json', 'backend/data/tasks.json',
               'backend/data/volume_price_samples.json', 'backend/data/low_position_samples.json',
               'backend/data/learning.json', 'backend/data/capital_watch.json'] if (ROOT / p).exists()}
    freeze_paths = ['docs/research/shadow-experiments-' + d + '-v1.json'
                    for d in ['20261029', '20261030', '20261102']]
    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in freeze_paths}
    research, runs, catalog = [load('backend/data/' + p) for p in
                               ['research.json', 'task_runs.json', 'research_stocks.json']]
    originals = {p: copy.deepcopy(d['items']) for p, d in
                 [('research', research), ('runs', runs), ('catalog', catalog)]}
    assert not any(r['id'] in IDS.values() for r in research['items']), 'reuse existing supplement'
    original_full = {r['task_id']: r['id'] for r in research['items'] if r['date'] == T and
                     r.get('analysis_completed') is True and r.get('status') == 'completed' and
                     r.get('report_type') in ['full_daily_research', 'full_trading_research']}
    assert set(original_full) >= {'market_review', 'volume_price', 'low_position', 'dragon_tiger',
                                  'combined_pair', 'limitup_single'}
    for task in ['market_review', 'volume_price', 'low_position', 'dragon_tiger']:
        assert next(r for r in research['items'] if r['id'] == original_full[task])['eligible_for_integrated_research'] is True
    facts = {
        'displayed_release_at': '2026-10-31T09:30:00+08:00',
        'manufacturing_PMI': 49.3, 'manufacturing_PMI_change_pp': -0.8,
        'manufacturing_new_orders': 49.4, 'manufacturing_new_orders_change_pp': -1.1,
        'nonmanufacturing_activity': 49.7, 'nonmanufacturing_activity_change_pp': -0.5,
        'services_activity': 50.0, 'services_activity_change_pp': -0.2,
        'construction_activity': 48.0, 'construction_activity_change_pp': -2.3,
        'consumer_goods_manufacturing_PMI': 48.8, 'consumer_goods_PMI_change_pp': -1.9,
        'accommodation_activity': 'month-on-month improvement; above 50; exact value not disclosed here',
        'real_estate_activity': 'below 50; exact value not disclosed here',
        'units': 'seasonally adjusted diffusion-index points; changes are percentage points',
        'not_company_data': True,
    }
    sources = [EVIDENCE, EXPERIMENT, 'docs/research/shadow-validation-20261030-v1.json'] + [m['url'] for m in meta.values()]
    common = (
        f'这是{DAY}休市宏观补证，实际完成北京时间{stamp}。最近已收盘交易日T={T}，'
        f'原计划D={D}；若D实际买入，最早2026-11-03可卖。原四模块及两个裁决完整交付6/6，'
        '复用原报告和真实回执；本补证不替代任何完整前置，也不是休市日交易复盘。'
        '统计局两页标注10月31日09:30；本轮实际于11月1日01:07:12左右取得原站HTTP正文，'
        '准确UTC、原站URL与SHA256另存证据。页面日期不等于已独立证明互联网首次公开时刻。'
        '它们晚于10月30日18:20:11的原信号冻结，不能反向填入原入选理由。'
    )
    economy = (
        '一、可核验事实与解释边界\n'
        '10月制造业PMI为49.3，环比下降0.8个百分点；新订单49.4，下降1.1个百分点。'
        '非制造业活动49.7，下降0.5个百分点。PMI是调查扩散指数，50为环比景气分界，'
        '这些数值不是企业盈利比例、产值同比增速或股市涨跌概率。宏观回落不能代替T30按市场宽度、'
        '炸板和晋级逐股分母冻结的“弱”情绪判定，也不能作为D开盘已知的价格表现。'
    )
    combined_facts = (
        '消费品制造业PMI为48.8，下降1.9个百分点；建筑业活动48.0，下降2.3个百分点；'
        '房地产行业被列为低于50，但本文未给其单独数值。建筑业48.0不能标为房地产PMI。'
        '这些是行业调查背景，不是泸州老窖000568或黑牡丹600510的订单、去库存、预售或现金流数据。'
    )
    limitup_facts = (
        '服务业活动50.0，下降0.2个百分点；统计局解读同时列住宿业环比改善且仍高于50，'
        '没有在该段披露住宿业具体指数。总量偏弱与住宿分项改善并存。它涉及10月含长假的经营调查，'
        '不等于首旅酒店600258自身入住率、房价或利润改善，更不是11月2日酒店股票板块已经走强。'
    )
    impacts = {
        '000568': '泸州老窖000568：消费品制造业收缩为总需求反证；该口径不是白酒专项调查。原H1/H3量价与逆势强度须由原窗口的报价检验，不能把消费分项当公司订单下降或确定股价下跌。',
        '600510': '黑牡丹600510：建筑与房地产行业调查偏弱增加经营背景风险，不能直接计算个股业绩损失。原财务反证和融资注册不等于到账的边界继续保留；原H1价格代理不因此升级为正式买入。',
        '600258': '首旅酒店600258：住宿分项相对总量改善，为原H3行业分化假设增加支持线索。仍须按原H2首次分歧/回封、原同伴、高标、量价窗口及队列证据检验；不新增阈值、参照股或买入许可。',
    }
    previous = (
        '三、上一批验证、对照与统计\n'
        'D29及D30原影子必要条件未满足、已核实成交0的结论保持；完整深筛池及失败/未触发样本均保留。'
        '尚只有2个已观察计划交易日，D1102未开市。本轮不新增证券日或交易数，'
        '不在周末重复追加T+1/T+2/T+5/T+10、MFE/MAE或封板/炸板结果。'
        '有分钟/逐笔、两侧成交、成本与合法T+1退出证据才计算可执行净收益。'
        '原沪深300和全部冻结对照继续使用；已有题材/流动性不完全匹配的限制保留。'
        'NBS行业分类不是A股行业成分篮子，不能把PMI差异算成股票对照收益。'
    )
    forward = (
        '四、前推规则及下一检查\n'
        '原正式综合与打板各0只及其空仓事件不变，不再生成一个休市空仓交易日。'
        'H1/H2/H3、combined_limitup_watch_v5和limitup_single_v2均不改版。'
        '11月2日沿原窗口核验竞价、真实证券状态/涨停价、承接、固定同伴与高标，'
        '未满足原条件即未触发；缺成交证据即成交待验证，不能从日最高价反推买到或获利。'
        'H3的反证仍是原参照篮子在原窗口无相对强度或原同伴条件失败；宏观支持不能豁免。'
        '原20—30个实际交易日首轮复核节点不变；不足样本不宣称高胜率。'
        '20只原候选/同伴/风险参照公司的公告增量查询均成功，无此前未核查的精确代码公告；'
        '这是有限对象核查，并非全A新扫描或风险穷尽。任务、量化取消状态和自动买入/调权关闭均不变。'
    )
    history_updates, record_by_task = [], {}
    for task, rid in IDS.items():
        signals = [s for s in exp['signals'] if s['parent_task_id'] == task]
        structured = [dict(original_signal_id=s['id'], market_event_id=s['market_event_id'],
                           code=s['code'], name=s['name'], original_rank=s['rank'],
                           original_frozen_at=s['signal_frozen_at'], original_reference_price=s['reference_price'],
                           original_reference_price_at=s['reference_price_at'],
                           original_condition_source=EXPERIMENT, not_a_new_signal=True,
                           is_recommendation=False, formal_buy_signal=False,
                           macro_impact_is_inference=impacts[s['code']]) for s in signals]
        table = '|原组别/序|原信号id|代码/名称|原T日参考价，非新报价|本次影响（推断）|\n|---|---|---|---|---|\n' + '\n'.join(
            '|'+ '|'.join([task+'/'+str(s['rank']),s['id'],s['code']+' '+s['name'],str(s['reference_price']),impacts[s['code']]]) +'|' for s in signals)
        body = '\n\n'.join([common, economy + '\n' + (combined_facts if task == 'combined_pair' else limitup_facts),
                              '二、原影子结构化清单与独立判断\n' + table + '\n\n原触发、失效、放弃、退出、板块制度与同伴全部以原冻结清单为准，不作修改。',
                              previous, forward])
        run_id = task.replace('_','-')+'-20261101-scheduled-macro-supplement-v1'
        title = '休市综合补证｜10月PMI与消费、地产背景反证，原影子冻结不变' if task == 'combined_pair' else '休市打板v2补证｜住宿与总量分化，原首旅影子条件不变'
        summary = '统计局原站PMI补证；总量偏弱与行业分化不改变原正式0及冻结条件，无新增样本或成交。'
        record = dict(id=rid,date=DAY,market_date=T,task_id=task,track='market_review',run_id=run_id,
                      title=title,summary=summary,body=body,sources=sources,
                      report_type='research_supplement',eligible_for_integrated_research=False,
                      analysis_completed=True,status='completed',published_at=stamp,recorded_at=stamp,
                      data_cutoff_at=stamp,market_data_cutoff_at=T+'T15:00:00+08:00',
                      planned_entry_date=D,earliest_legal_exit_date_if_bought='2026-11-03',
                      provenance='new_macro_evidence_reviewed_after_original_freeze',candidate_count=0,
                      recommendation_ids=[],original_report_ids=[original_full[task]],
                      original_cash_observation_id=next(c['id'] for c in exp['formal_cash_observations'] if c['task_id']==task),
                      maintained_shadow_experiment_file=EXPERIMENT,existing_shadow_conditions=structured,
                      new_shadow_candidates=0,new_price_observations=0,new_trade_observations=0,
                      original_freeze_preserved=True,not_a_new_trading_day_report=True,evidence_file=EVIDENCE,
                      research_rule_version='weak_market_shadow_v1',
                      parent_rule_version='limitup_single_v2' if task=='limitup_single' else 'combined_limitup_watch_v5',
                      codes=[s['code'] for s in signals],reference_market_emotion='弱',emotion_as_of=T)
        research['items'].append(record);record_by_task[task]=record
        runs['items'].append(dict(id=run_id+'-completed',run_id=run_id,task_id=task,date=DAY,market_date=T,
                                  trigger='scheduled',started_at=START,completed_at=stamp,recorded_at=stamp,
                                  status='completed',summary=summary,report_ids=[rid],recommendation_ids=[],
                                  analysis_completed=True,eligible_for_integrated_research=False,
                                  delivery_status='repository_prepared_not_yet_verified',sources=[EVIDENCE,EXPERIMENT],
                                  does_not_replace_original_full_research=True))
        for s in signals:
            stock=next(c for c in catalog['items'] if c['code']==s['code'])
            entry=dict(id=f"research-stock-{s['code']}-20261101-macro-supplement-v1",date=DAY,market_date=T,
                       recorded_at=stamp,title='原冻结后的宏观行业补证，非公司经营数据',
                       reason=impacts[s['code']],evidence_status='official_macro_sector_context_verified_company_effect_unverified',
                       fact_note=combined_facts if task=='combined_pair' else limitup_facts,
                       validation=['原影子排序、参考价、同伴、触发/失效/放弃及T+1退出规则全部保留。',
                                   '本次关联是研究推断，需在D原窗口证伪；不产生正式买入或新增交易计数。'],
                       risk='宏观行业数据不是公司订单、现金流或股价预测；不能豁免个股风险或证明成交。',
                       report_ids=[rid],sources=[m['url'] for m in meta.values()]+[EVIDENCE,EXPERIMENT])
            stock['history'].append(entry)
            history_updates.append(dict(code=s['code'],history_id=entry['id'],report_id=rid))
    catalog['updated_at']=stamp
    evidence=dict(base_main=sha_value(),actual_started_at_utc=START,actual_completed_at=stamp,T=T,planned_D=D,
                  original_freeze_hashes=hashes,original_signal_ids=[s['id'] for s in exp['signals']],
                  original_full_report_ids=original_full,source_metadata=meta,verified_facts=facts,
                  source_failure_and_recovery={'data_page_initial_web_fetch':'timeout','both_original_HTTP_fetches':200},
                  analyst_review={'facts_checked_against_original_HTTP_body':True,'inferences_distinguished':True,
                                  'rules_or_thresholds_changed':False,'new_stock_specific_financial_facts':False},
                  announcement_queries=queries,preflight_online=online,
                  original_trade_and_price_outcomes_unchanged=True,existing_stock_history_updates=history_updates)
    compressed=gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)
    manifest=dict(base_main=sha_value(),actual_started_at_utc=START,completed_at=stamp,market_T=T,
                  maintenance_date_cn=DAY,planned_D=D,report_ids=list(IDS.values()),
                  existing_stock_history_updates=history_updates,original_freeze_hashes=hashes,
                  new_recommendations=0,new_shadow_candidates=0,new_sample_cohorts=0,new_price_or_trade_results=0,
                  task_registry_and_schedules_changed=False,quant_research_restored=False,
                  evidence_file=EVIDENCE,evidence_sha256=hashlib.sha256(compressed).hexdigest())
    assert research['items'][:len(originals['research'])]==originals['research']
    assert runs['items'][:len(originals['runs'])]==originals['runs']
    assert len(catalog['items'])==len(originals['catalog'])
    for old,new in zip(originals['catalog'],catalog['items']):
        assert all(new[k]==v for k,v in old.items() if k!='history')
        assert new['history'][:len(old['history'])]==old['history']
    assert datetime.fromisoformat(START)<=datetime.fromisoformat(stamp)<=datetime.now(timezone.utc)
    docs={'backend/data/research.json':research,'backend/data/task_runs.json':runs,
          'backend/data/research_stocks.json':catalog,'app/src/main/assets/research_stocks.json':catalog,
          MANIFEST:manifest}
    for path,value in docs.items():(ROOT/path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (ROOT/EVIDENCE).write_bytes(compressed)
    for task,record in record_by_task.items():
        (ROOT/('docs/research/'+IDS[task]+'.md')).write_text('# '+record['title']+'\n\n'+record['body']+'\n\n来源：\n\n'+'\n'.join('- '+s for s in sources)+'\n')
    assert all((ROOT/p).read_bytes()==b for p,b in before.items())
    assert hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in freeze_paths}
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


def sha_value():
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


if __name__=='__main__':
    main()
