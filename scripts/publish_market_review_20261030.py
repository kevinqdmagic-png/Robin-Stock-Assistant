"""Append the actual T30 full review before the combined decision is frozen.

This program serializes the separately completed analyst review. It does not
create rankings, trades, historical timestamps, or an independent shadow trade.
The atomic publication includes this report together with all other modules.
"""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json

ROOT = Path(__file__).resolve().parents[1]
T = '2026-10-30'
D = '2026-11-02'
EXIT = '2026-11-03'
START = '2026-10-30T09:38:34+00:00'
RID = 'market-review-20261030-close-v1'
RUN = 'market-review-20261030-scheduled-close-v1'
EVIDENCE = 'docs/research/market-review-2026-10-30-evidence.json'
FULL = 'docs/research/combined-pair-20261030-evidence.json.gz'
EXPERIMENT = 'docs/research/shadow-experiments-20261102-v1.json'


def load(path):
    return json.loads((ROOT / path).read_text())


def table(headers, rows):
    def cell(value):
        if value is None:
            return 'N/A'
        if isinstance(value, float):
            value = round(value, 3)
        return str(value).replace('|', '/').replace('\n', '；')
    return '\n'.join(['|' + '|'.join(headers) + '|', '|' + '|'.join(['---'] * len(headers)) + '|'] +
                     ['|' + '|'.join(cell(v) for v in row) + '|' for row in rows])


def main():
    research = load('backend/data/research.json')
    runs = load('backend/data/task_runs.json')
    assert not any(r['id'] == RID for r in research['items']), 'reuse existing completed review'
    assert not any(r['id'] == RUN + '-completed' for r in runs['items'])
    review = load('tmp/analyst-combined-20261030.json')
    assert review['analysis_reviewed'] and review['T'] == T and review['planned_D'] == D
    market = load(EVIDENCE)
    de = load('tmp/combined-20261030-derived.json')
    exact = load('tmp/combined-20261030-exact-main-limit-check.json')
    stats = load('tmp/combined-20261030-statistics.json')
    validation = load('tmp/shadow-validation-20261030.json')
    official = load('tmp/combined-20261030-official-files.json')
    deep = de['deep_recomputed']
    assert len(deep) == 28 and len(de['broad_recomputed']) == 120
    assert not de['crosscheck']['ohlc_mismatches']
    stamp = datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    assert datetime.fromisoformat(validation['recorded_at']) < datetime.fromisoformat(stamp)
    sectors = review['sectors']
    price_rows = [[s['code'] + ' ' + s['name'], sectors[s['code']], s['close'], s['daily_change_pct'],
                   '/'.join(str(s['rvol'][str(n)]) for n in (5, 10, 20)), s['turnover_pct'],
                   '/'.join(str(s['range_position_pct'][str(n)]) for n in (20, 60, 120)),
                   '/'.join(str(s['ma'][str(n)]) for n in (5, 10, 20, 60)),
                   s['clv'], s['tail_1400_close_pct']] for s in deep]
    judgments = [[s['code'] + ' ' + s['name'], review['deep_reviews'][s['code']]['model'],
                  review['deep_reviews'][s['code']]['support'], review['deep_reviews'][s['code']]['against']]
                 for s in deep]
    prior_rows = [[s['code'] + ' ' + s['name'], s['open_pct'], s['mfe_pct'], s['mae_pct'], s['close_pct']]
                  for s in de['previous_whole_pool']]
    vrows = [[s['code'] + ' ' + s['name'], s['close_observation_pct'], s['MFE_price_observation_pct'],
              s['MAE_price_observation_pct'], '；'.join(s['trigger_evidence'])]
             for s in validation['signals']]
    older_rows = [[s['planned_D'], s['code'] + ' ' + s['name'], s['close_observation_pct'],
                   s['entry_status']] for batch in validation['all_frozen_experiment_followups'] for s in batch['signals']]
    separate_rows = [[s['planned_D'], s['code'] + ' ' + s['name'], s['close_observation_pct'],
                     s['shared_market_event_with_combined']] for s in validation['independent_market_shadow']]
    day_rows = []
    for day in ('2026-10-28', '2026-10-29', T):
        m = load(f'docs/research/market-review-{day}-evidence.json')['market']
        day_rows.append([day, m['advance'], m['decline'], m['flat'], m['amount_yuan_full_scan'] / 1e8,
                         m['standard_non_st_limit_up_sealed'], m['standard_non_st_failed_boards'],
                         m['standard_non_st_limit_down']])
    ladder = table(['主板正常10%连续梯队', '家数', '股票'], [[k, len(v), '、'.join(s['code'] + s['name'] for s in v)]
                    for k, v in de['board_ladder'][T]['layers'].items()])
    progression = table(['晋级', 'T29原逐股分母', '晋级', '断板', '缺失', '比例%'],
                        [[k, v['prior_full_denominator'], v['advanced'], v['broken'], v['missing'],
                          v['verified_advancement_pct']] for k, v in de['progression_main_10pct'].items()])
    denominator_rows = [[k, s['code'] + ' ' + s['name'], s['status'], s['T_close']]
                        for k, v in de['progression_main_10pct'].items() for s in v['rows']]
    lookup = {s['code']: s for s in de['broad_recomputed']}
    alternatives = table(['实际备选', '当前/计划板与角色', '支持与否决'],
                         [[r['code'] + ' ' + lookup[r['code']]['name'], r['role'], r['reason']]
                          for r in review['comparisons']])
    shadow_rows = [[s['code'] + ' ' + lookup[s['code']]['name'], s['rank'], lookup[s['code']]['close'],
                   s['selection_reason'], s['formal_rejection_reason']]
                  for s in review['shadows'] if s['parent_task_id'] == 'combined_pair']
    financial_rows = [[f['code'], f['fact']] for f in review['facts']]
    sp = stats['twenty_prior_sessions_space_reference']
    p = de['previous_whole_pool_summary']
    body = '\n\n'.join([
        f'研究已收盘T={T}；价格截止北京时间15:00，实际分析完成{stamp}。计划D={D}；如D真实买入，最早{EXIT}可卖。当前为独立market_review完整研究，综合裁决另有四模块前置。正式候选0；研究提名与实际成交分开。',
        '一、市场、三日情绪与前次情景核验\n' + review['market_findings'],
        table(['日期', '上涨', '下跌', '平盘', '同源成交亿元', '主板封板代理', '炸板代理', '跌停代理'], day_rows),
        '正价入口5574条中4条没有当日有效OHLCV（688121、601326、688496、605258）单列；5570条当日成交报价。892涨/4602跌/80平保留原正价入口可比口径，活跃平盘76。成交为同源覆盖求和，并非另一个官方全市场口径。普通非ST主板9.5%阈值是代理，不能当实际涨停价。',
        f"实际报价上下限逐股核验入口{exact['price_limit_verified_n']}/{exact['candidate_count']}：封板{exact['closed_at_upper_n']}、触板{exact['touched_upper_n']}、触板未封{exact['touched_not_sealed_n']}、跌停收盘{exact['closed_at_lower_n']}。该入口与代理42/77/35/104分母不同，不混算。下跌占涨跌家数83.764%、代理炸板35/77=45.455%，沿用原冻结规则归为弱。",
        '可见板块研究：白酒、酒店、食品、航运及部分银行相对成长方向强；成长指数及机器人/通信等原活跃池负反馈明显。完整统一行业成分/涨跌幅总表缺失，不把研究标签篮子称全行业最强/最弱排名，也不把消费少数封板当主线持续性已确认。',
        ladder, progression,
        table(['原层级', '原冻结分母股票', 'T30结果', '收盘'], denominator_rows),
        f"空间参照为T之前20个实际交易日，仅{sp['available_pools']}/20可核池；缺{sp['missing_session_pools']}，可见最高{sp['visible_maximum_boards']}板。完整20日最高/周期起点未知，不宣称已打开空间。青岛食品五板、沪工/澳洋三板、四板断层；东贝/文投跌停和光洋断板是隔夜风险。",
        '二、全A入口、量价定义与完整深筛\n5576原始条目→5574正价入口（5570当日有效OHLCV）→160条流动性活跃入口→120广泛池→28深筛。入口辅助排序仅用于覆盖，不是经过校准的收益分数；最终选择为逐只证据裁决。覆盖至少五个板块，所有实际研究标签逐只列明。',
        'RVOL=当日全量/此前5、10、20个完整交易日均量，分母不含T；与盘中量比不同。区间位置/MA使用未复权且含T口径。CLV=(收盘−最低)/(最高−最低)，高低相同记N/A；14时后为离散价格变化，不确认尾盘承接账户或队列成交。',
        table(['代码/名称', '研究板块', '收盘', '涨跌%', 'RVOL5/10/20', '换手%', '20/60/120位置%', 'MA5/10/20/60', 'CLV', '14时后%'], price_rows),
        table(['股票', '模型/角色', '支持', '反证及未入选理由'], judgments),
        '三、先验证上一完整28池\n' +
        f"T29原28只全部核验，收红{p['positive_n']}；收盘观察均值{p['mean_pct']}%、中位{p['median_pct']}%，平均最高{p['mean_mfe_pct']}%、最低{p['mean_mae_pct']}%，低于−5%共{p['mae_le_minus5_n']}只。以T29收盘为锚，不是T30买入收益；保留全部失败，跨报告不重复计交易。",
        table(['股票', '开盘观察%', '最高观察%', '最低观察%', '收盘观察%'], prior_rows),
        '四、先验证原影子、对照和长期节点\nD30原中国卫星600118、景津装备603279、桂林三金002275均有必要条件被否定，已核成交0、可执行净收益N/A。桂林封板仍未满足原同伴条件，不能记作赚取涨停。全部原对照和旧批次跟踪见独立验证清单，原冻结条件不改。',
        table(['D30原影子', '收盘观察%', 'MFE价格%', 'MAE价格%', '原条件反证'], vrows),
        table(['更早计划D', '原信号', '至T30收盘观察%', '入场状态原样延续'], older_rows),
        table(['独立市场影子D', '原信号', '收盘观察%', '与综合共用事件'], separate_rows),
        '已观察2个独立计划交易日、6个综合/打板股票-D事件；中国卫星同股D与综合关联，独立市场横河/广联另保留，不当成额外已成交交易。T+1/T+2/T+5/T+10按原信号T和计划D双轴区分，未到节点不估算。全旧低位50条自然日/交易日验证、旧量价14批369条和历史正式31条结果继续追加；日线不证明9:50/14:40、盘中止损先后或可执行退出。',
        '五、量价发现、反例、资金与隔夜\n' + review['volume_findings'],
        review['dragon_findings'], review['low_findings'],
        '放量后价格能否推进和次日承接仍是待检验核心。公开席位只表示该营业部披露，不确认资金身份、锁仓或做T；逐只资金结构缺证据时明确未知。六类原模型继续分别研究，不因单一K线或资金标签给买入许可。',
        '六、两轨提名、替代与正式空仓\n' + review['formal_cash_reason'],
        table(['综合研究提名，非买入建议', '相对排序', 'T参考价非成交', '相对依据', '正式否决/风险'], shadow_rows),
        f'本独立市场研究提名与本轮综合影子共用同一股票-D事件，最终真实冻结时间、逐只触发/失效/放弃/退出区间与所有原始来源在{EXPERIMENT}。本报告完成时间不冒充该实验稍后冻结时间。新D为周一，信号跨周末；D买入至D+1为周一至周二，不是周末持仓。',
        alternatives,
        '深筛池5交易日代码并集重复率39.286%（5/5日期）；10日仅6/10日期可核，可得池并集42.857%，严格10日率N/A。定义为本次28代码与原同口径池并集交集/28，不是正式推荐重复率；正式0只的推荐重复率N/A。重选保留新证据与否决，不为降重复率更换。',
        '七、原公告、题材和财务反证\n' + table(['代码', '可核原公告及风险'], financial_rows),
        '32份原PDF的URL、哈希、HTTP成功取证时间与正文/文件路径日期分别保留。少数路径标10月31日但本轮10月30日已实际HTTP可取，仅用于之后D计划，不补作T30盘中催化，也不推定精确首次公开时刻。黑牡丹经营亏损与库存减值是重大独立风险，研究价格结构不改变正式否决。公告查询非穷尽风险证明。',
        '八、D=11月2日三情景与下次验证\n' + '\n'.join(review['market_scenarios']),
        review['next_validation'],
        '情景仅可证伪对照，不给未经校准概率。所有分钟只有109条日期合格的离散价格点序列，不是分钟OHLC/逐笔/竞价/买卖队列；六时窗仍保留，缺成交时不排名最佳可实现买卖时段。按模型、板块、资金结构、位置、信号版本及情绪累计原样本，缺可执行净收益不报胜率或盈亏比。',
        'H1低位量能与尾盘价格代理对照高位放量加速；H2首次分歧回封对照直接追高，同股同D是配对而非两笔交易；H3逆势板块篮子对照绝对涨幅。20—30个独立实际计划日首轮复核，披露缺失、未触发、未成交和下行尾部；目前样本不足。主基准沪深300，严格行业流动性匹配不足明确保留，不只统计幸存者。',
        '研究影子非买入建议，不写正式recommendations、不触发买入通知；量化模块不恢复，不变调度。APP不内置大模型/自动权重训练/自动下单。A股T+1、费用、涨跌停与停牌约束保留。原报告和条件只追加后续结果，发布必须经CI/容器、准确SHA的Railway SUCCESS与公开API核验。',
    ])
    sources = [EVIDENCE, FULL, EXPERIMENT, 'docs/research/shadow-validation-20261030-v1.json',
               'https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml',
               market['index_quotes']['source']] + [f['source'] for f in official.values() if f.get('ok')]
    report = dict(id=RID, date=T, market_date=T, task_id='market_review', track='market_review', run_id=RUN,
                  title='每日复盘｜10月30日放量退潮、旧28全验证与消费结构反证',
                  summary=review['summaries']['market_review'], body=body, sources=list(dict.fromkeys(sources)),
                  report_type='full_daily_research', eligible_for_integrated_research=True,
                  analysis_completed=True, status='completed', published_at=stamp, recorded_at=stamp,
                  data_cutoff_at=stamp, market_data_cutoff_at=T + 'T15:00:00+08:00',
                  provenance='contemporaneous_after_close_research', research_rule_version='market_review_close_v6',
                  candidate_count=0, recommendation_ids=[], research_shadow_codes=['000568', '600510'],
                  shadow_experiment_file=EXPERIMENT, shadow_final_freeze_is_separate=True,
                  evidence_file=EVIDENCE, codes=[s['code'] for s in deep], full_scan_count=5574,
                  active_OHLCV_count=5570, inactive_or_missing_current_OHLCV_count=4,
                  broad_pool_count=120, deep_pool_count=28, previous_pool_verified_count=28,
                  planned_entry_date=D, earliest_legal_exit_date_if_bought=EXIT,
                  prior_scenario_validation='daily necessary downside conditions observed; continuous 30-minute confirmation unavailable')
    research['items'].append(report)
    runs['items'].append(dict(id=RUN + '-completed', run_id=RUN, task_id='market_review', date=T,
                             trigger='scheduled', started_at=START, completed_at=stamp, recorded_at=stamp,
                             status='completed', summary=report['summary'], report_ids=[RID], recommendation_ids=[],
                             analysis_completed=True, eligible_for_integrated_research=True,
                             delivery_status='repository_prepared_not_yet_verified', sources=[EVIDENCE, FULL]))
    market['analyst_approval'] = True
    market['analysis_completed_at'] = stamp
    market['analyst_review_file'] = 'docs/research/combined-pair-20261030-analyst-review.json'
    market['note'] = 'Actual independently completed analyst research; entry helper is not calibrated alpha; exact/proxy counts separated.'
    for path, data in [('backend/data/research.json', research), ('backend/data/task_runs.json', runs),
                       (EVIDENCE, market), ('docs/research/' + RID + '.json', report)]:
        (ROOT / path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (ROOT / ('docs/research/' + RID + '.md')).write_text('# ' + report['title'] + '\n\n' + body + '\n\n来源：\n\n' + '\n'.join('- ' + s for s in report['sources']) + '\n')
    print(json.dumps({'report_id': RID, 'completed_at': stamp, 'full_pool_validated': 28,
                      'formal_candidates': 0, 'publication_pending': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
