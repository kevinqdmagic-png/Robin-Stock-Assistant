#!/usr/bin/env python3
"""Freeze independently researched T20 modules, D21 plans and append-only evidence.

Prepares an atomic repository publication. CI/deployment are separate readbacks.
No daily price excursion, public seat label or conditional card is a fill.
"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import copy
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import collect_20261020_combined as c
from publish_20261019_combined import tab, f, sg
from publish_market_review_20261020 import SECTOR
from research_evidence_io import load_evidence

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'backend/data'
T, D, EXIT = '2026-10-20', '2026-10-21', '2026-10-22'
EFILE = 'docs/research/combined-pair-2026-10-20-evidence.json'
MARKET = 'market-review-20261020-close-v1'
IDS = {k: k.replace('_', '-') + '-20261020-close-v1'
       for k in ('volume_price', 'low_position', 'dragon_tiger', 'combined_pair')}
RID = 'combined-pair-20261020-300458-close-v1'
SECTOR.update({'301658': '光伏逆变器/储能', '003021': '微型传动/机器人',
               '300314': '医疗器械', '300432': '汽车零部件/锂电材料',
               '000032': '数字基础设施/工程服务', '688084': '军工电子/特种装备',
               '300556': '数字视觉'})


def load(name):
    return json.loads((DATA / name).read_text())


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def clean(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    return obj


def prepare_evidence(e, stamp):
    """Keep two qfq failures visible; never silently substitute adjusted prices."""
    market = json.loads((ROOT / 'docs/research/market-review-2026-10-20-evidence.json').read_text())
    existing = {s['code']: s for s in e['volume_price']['deep_samples']}
    partial = []
    for quote in market['deep_pool']:
        code = quote['code']
        if code in existing:
            continue
        raw = e['raw_daily_histories'].get(code, [])
        assert raw and raw[-1]['date'] == T
        # Raw volume/MA research is explicitly supplemental, not a recovered qfq feed.
        s = c.enrich([quote], {code: raw}, {code: raw}, e['minute_price_paths'])[0]
        s.update(factor_price_basis='unadjusted_supplement_qfq_unavailable',
                 eligible_for_adjusted_position_statistics=False,
                 structure='复权历史缺项/原价补充风险观察', frozen_at=stamp)
        s['missing'].append('independent_qfq_history')
        s['daily_source'] = 'https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param=' + c.sym(code) + ',day,,,180'
        for n in (20, 60, 120):
            if len(raw) < n:
                s['range_position_pct'][str(n)] = None
        s['raw_history_session_count'] = len(raw)
        existing[code] = s
        partial.append(code)
    e['volume_price']['deep_samples'] = [existing[q['code']] for q in market['deep_pool']]
    e['volume_price']['supplemental_raw_basis_codes'] = partial
    e['volume_price']['deep_adjusted_history_verified_count'] = 28 - len(partial)
    for s in e['volume_price']['deep_samples']:
        s['frozen_at'] = stamp
    e['price_crosscheck_summary']['supplemental_deep_ohlc_exact'] = len(partial)
    e['combined_decision'] = {
        'decision_id': IDS['combined_pair'], 'frozen_at': stamp, 'market_date': T,
        'planned_entry_date': D, 'earliest_legal_exit_date_if_bought': EXIT,
        'selected_codes': ['300458'], 'recommendation_ids': [RID],
        'broad_pool_count': 120, 'adjusted_history_verified_count': 108,
        'deep_review_count': 28, 'deep_adjusted_history_verified_count': 26,
        'no_verified_executions_at_publication': True,
        'rationale': '宽度修复但指数分化；只保留未封20%板且尾盘推进的全志条件卡。龙虎榜风险与低位替代者独立否决，不凑第二只。'}
    e['publication_evidence_normalization'] = {
        'recorded_at': stamp, 'nonfinite_provider_table_cells': 'JSON null, not invented zero',
        'original_fetch_errors_preserved': True,
        'raw_supplement_not_merged_into_qfq_history': True}
    return clean(e)


def sources(e):
    return list(dict.fromkeys([EFILE] + e['sources'] +
                             [x['source'] for x in e['issuer_primary_pdf_checks'] if 'error' not in x]))


def report(task, title, summary, body, e, stamp, **extra):
    return {'id': IDS[task], 'date': T, 'market_date': T, 'task_id': task,
            'track': 'market_review' if task == 'combined_pair' else task,
            'title': title, 'summary': summary, 'body': body, 'sources': sources(e),
            'report_type': 'full_daily_research', 'eligible_for_integrated_research': True,
            'published_at': stamp, 'recorded_at': stamp, 'data_cutoff_at': stamp,
            'market_data_cutoff_at': T + 'T15:00:00+08:00',
            'run_id': task.replace('_', '-') + '-20261020-scheduled-close-v1',
            'evidence_file': EFILE, 'provenance': 'contemporaneous_close_research', **extra}


def snapshot_table(ss):
    return tab(['代码/名称', '方向', '收盘/涨跌%', '换手%', 'RVOL5/10/20', '20/60/120位置%',
                'CLV', '距MA20%', '14点后%', '尾盘量占%', '冻结结构'],
               [[s['code'] + ' ' + s['name'], SECTOR.get(s['code'], '行业待细分'),
                 f(s['close']) + '/' + sg(s['daily_change_pct']), f(s['turnover_pct']),
                 '/'.join(f(s['rvol'][str(n)], 3) for n in (5, 10, 20)),
                 '/'.join(f(s['range_position_pct'][str(n)], 1) for n in (20, 60, 120)),
                 f(s['clv'], 3), sg(s['distance_ma20_pct']), sg(s['tail_return_1400_to_1500_pct']),
                 f(s['tail_volume_share_pct']), s['structure']] for s in ss])


def validation_table(rows):
    return tab(['代码/名称', '开盘观察%', '日高观察%', '日低观察%', '收盘观察%'],
               [[r['code'] + ' ' + r.get('name', ''), sg(r.get('open_return_pct')),
                 sg(r.get('high_observation_pct')), sg(r.get('low_observation_pct')),
                 sg(r.get('close_return_pct'))] for r in rows])


def volume_report(e, stamp):
    v = e['volume_price']; p = v['previous_statistics']; a = v['cumulative_v4_next_day_price_statistics']
    groups = tab(['T19冻结结构', 'N/收涨数', '收盘均值/中位%', '日低均值%'],
                 [[k, str(x['verified']) + '/' + str(x['positive_close_count']),
                   sg(x['mean_close_return_pct']) + '/' + sg(x['median_close_return_pct']),
                   sg(x['mean_low_observation_pct'])] for k, x in v['previous_by_frozen_structure'].items()])
    diagnostics = tab(['原样本', 'T20涨跌%', '量/前日', 'RVOL20', 'CLV'],
                      [[x['code'] + ' ' + x['name'], sg(x['change_pct']), f(x['volume_vs_previous_session']),
                        f(x['rvol20']), f(x['clv'], 3)] for x in v['prior_pool_validation_day_structures']])
    body = f'''一、独立覆盖与真实时间

T={T}，D={D}，完成/冻结{stamp}。复用完整市场复盘{MARKET}的5574原始/5568有效全A入口和120只广泛池，非用户自选入口。独立重取原价/前复权历史及分时价格点：120只同日新浪报价，108/120具备足够前复权历史和腾讯原价OHLC交叉核验，108只OHLC差为0；完整研究28个深筛名字，其中26具前复权历史，宇树科技688836、摩尔线程688795前复权接口失败，保留已独立核对的原价日线、分时和原价辅助指标，明确不参与复权位置模型统计。宇树仅39个原价交易日，60/120位置不适用。不能把原价冒充前复权恢复，更不能把120只报价叫120只完整历史。

初始412次日线请求156次失败，备用公开腾讯接口恢复141项，余15项含指数复权/较短历史等，逐条保留原失败和实际恢复URL；没有抹掉失败或伪造缺项。机器人、半导体、软件、消费、医药、军工、能源设备、汽车等多方向独立比对。先验证T19冻结28/28，再冻结T20完整28个研究记录；三个30天新增研究样本独立关联，不重复计数为两组交易。

二、量价研究与验证：全部28个原始快照

{snapshot_table(v['deep_samples'])}

volume_price_close_v4不改阈值。RVOL为T量/此前5、10、20个已完成交易日均量，分母不含T；量/前一日独列，均非盘中量比。MA含T收盘、位置优先前复权、价格观察用原价；上述两只补充明确原价基准。CLV=(C-L)/(H-L)，H=L为N/A。原样本保留O/H/L/C、量额、均线、前5/20高、振幅、检查点和来源。T-1逐股流通股本/换手同口径变化部分缺失留空，不估填。市场复盘采用前一窗口的MA距离与本报含T窗口不可机械拼接；阿尔特本报距MA20为+0.410%，冰山为+41.766%。

9:30、9:45、10:30、11:30、14:00、14:40、15:00价格与累计量检查点已留存；缺9:25、分钟OHLC、逐笔、盘口、真实委托/成交。剔除15:30等盘后点。累计量差可比较区间活跃度，不能证明杀跌逐笔顺序、真实缩量回踩成交或T+1可退出。

三、典型样本及反例

①全志科技300458：28.64、+11.267%，RVOL20=1.821、量/前日2.580，CLV1，14点28.03至收盘28.64约+2.18%；前5高28.18被收复，但仍低于MA20=30.153、MA60=32.603。属于反弹推进而非已确认主升或20%涨停。业绩预告支持产业证据，不等于次日价格保证；综合组只冻结严格回踩再转强条件。

②阿尔特300825：11.52、+9.402%，RVOL20=2.843、CLV0.737，振幅约19.47%、换手12.29%，上影高12.06且近两日反弹较快。MA20=11.473虽已收回，不能以一天收回认定筹码分歧完成；回踩/板块条件未知，综合组不选。精研科技300709收35.70而CLV0.620、天元智能603273 CLV0.679，同为放量但价格推进质量较弱。

③润建股份002929：收51.04封10%板，RVOL20=5.126、量为前日约6.65倍；单日净买仅18.86万元，三日净买5024.54万元是不同区间。单日机构专用和股通通道均净卖，10月21日已可取得的异动公告提示合同履约和财务不确定性；不能把“有AI合同+大成交”机械升级。明日普通成交/后天除息影响均需核对。

④冰山冷热000530：8.17、+4.744%，换手44.41%、RVOL20=5.514、距MA20+41.77%，即使尾盘回收且CLV0.846也不消除高位波动和净卖风险。长春一东600148 RVOL20=14.476、换手22%、封板，但榜净卖和估值风险公告形成强反证。缩量封板、长上影、高位爆量不可统称同一种有效启动。

⑤三个新低位样本首航新能301658、兆威机电003021、戴维医疗300314详见独立low_position报告；满足30天入池不等于综合超短合格。首航相对5日量只有1.079倍，不能称刚首次爆量；戴维已有减持窗口。低位、放量、席位只是条件证据，不是资金身份。

六类结构的全池反证（按T19原结构冻结，不回看重分组）：

{diagnostics}

低位首次放量、突破、缩量上涨、放量下跌、高位滞涨和上影都保留失败/未触发；严格“突破→缩量回踩→再放量突破”的成交级共振尚未形成可确认两侧执行样本，不把K线名称当结论。

四、上一完整28/28及累计验证

{validation_table(v['previous_validations'])}

T19→20收涨11/28；开盘均值{sg(p['mean_open_return_pct'])}%、中位{sg(p['median_open_return_pct'])}%；收盘均值{sg(p['mean_close_return_pct'])}%、中位{sg(p['median_close_return_pct'])}%；日高均值{sg(p['mean_high_observation_pct'])}%、日低均值{sg(p['mean_low_observation_pct'])}%。上证同口径约+0.12%，全池收盘均值相对差约-0.40个百分点，是价格观察，不是净超额或策略盈亏。

{groups}

累计v4信号10月16—19日、验证截至20日，两批56条下一交易日价格观察，20收涨；收盘均值{sg(a['mean_close_return_pct'])}%/中位{sg(a['median_close_return_pct'])}%，日高均值{sg(a['mean_high_observation_pct'])}%/日低均值{sg(a['mean_low_observation_pct'])}%。分母按cohort+code+下一交易日，同股跨日样本相关，不冒充56只独立股票。T20新池尚未成熟，不计分母。v1/2/3、长假和v4分开。可验证策略双侧成交N=0，净胜率、平均/中位净收益、盈亏比、可执行MFE/MAE及退出质量N/A；20bp往返成本只是未校准假设。9:50/14:40缺同口径时序/成交，不能作策略优劣排名。

五、结论与下一假设

事实：宽度从T19下跌占优修复至3777涨/1668跌，但成长指数分化，普通主板代理炸板33/79≈41.8%，不是全市场率。阶段观察：原低中位7条有6收涨、平均+2.152%，但N=7/一天、选择偏差与成交缺项不能证明稳定优势。其余推进组3条全跌及高乖离对照保留，不能只展示成功者。

H3延续、H4影子假设不改权重：良好CLV/尾盘推进须次日缩量承接后重站关键位且同伴与宽度一致；检验全志相较高乖离封板组，及三个30天样本后续承接。次日未满足全部条件即不激活，不能用日高反推买入。T20盘后信号若21日买入，最早22日可卖，21日跌破失效不能当天卖；跌停/停牌可能延后。没有稳定规律、自动训练或涨停概率承诺。'''
    return report('volume_price', '量价完整研究｜10月20日28只深筛、全池前推与分歧承接',
                  '120只报价、108只复权历史复算，28只深研含2只明确原价补充；前池28/28及累计56价格观察验证，策略成交N=0。',
                  body, e, stamp, research_rule_version='volume_price_close_v4', broad_pool_count=120,
                  broad_pool_verified_count=108, deep_pool_count=28, deep_adjusted_history_verified_count=26,
                  previous_pool_verified_count=28, sample_cohort_id='volume-price-20261020-close-v1-cohort',
                  frozen_sample_codes=[s['code'] for s in v['deep_samples']], codes=[s['code'] for s in v['deep_samples']], executable_sample_count=0)


def low_report(e, stamp):
    l = e['low_position']; vals = l['existing_validations']; new = l['new_candidates']
    table = tab(['代码/名称', '原参考', '当前观察%', '信号后高/低观察%', '收盘路径回撤%', '自然/交易日', '曾收破/当前收破'],
                [[r['code'] + ' ' + r['name'], f(r['reference_close']), sg(r['close_return_pct']),
                  sg(r['path_mfe_pct']) + '/' + sg(r['path_mae_pct']), sg(r['max_close_to_close_drawdown_pct']),
                  str(r['elapsed_natural_days']) + '/' + str(r['elapsed_trading_sessions']),
                  str(r['ever_verified_close_below_original_invalid']) + '/' + str(r['observed_close_below_original_invalid'])] for r in vals])
    details = []
    for s in new:
        details.append(f"{s['code']} {s['name']}：收{s['close']:.2f}（{s['daily_change_pct']:+.2f}%），成交{s['amount_cny']/1e8:.2f}亿元、换手{s['turnover_pct']:.2f}%；RVOL5/10/20=" +
                       '/'.join(f(s['rvol'][str(n)], 3) for n in (5, 10, 20)) + '；20/60/120位置=' +
                       '/'.join(f(s['range_position_pct'][str(n)], 1) for n in (20, 60, 120)) + '；MA5/10/20/60=' +
                       '/'.join(f(s['ma'][str(n)], 3) for n in (5, 10, 20, 60)) +
                       f"；CLV{s['clv']:.3f}、尾盘{s['tail_return_1400_to_1500_pct']:+.2f}%。初始失效位{s['low']:.2f}，以未来收盘跌破信号日低点确认，原位不后移。")
    models = Counter(s.get('primary_model', s.get('model', '未标主模型')) for s in load('low_position_samples.json')['items'])
    body = f'''A. 新增样本与固定口径

T={T}，实际冻结{stamp}。全A有效5568入口、120广泛池，108具有足够可复算复权历史；按原low_position_30d_v1筛选，非旧代码、120日位置≤55%、RVOL20=2—6、CLV≥0.72、涨1.5%—8%、距含T的MA20=0—15%。高位加速/纯情绪接力不入；前复权缺项不硬凑。本轮新增3只，独立30天研究，不是每日两只短线或自动加入用户自选。

{chr(10).join(details)}

首航新能301658：120日相对低位但短周期已到区间较高位置、换手20.31%，量/5日均量1.079不支持“今天首次爆量”。逆变器/储能与当日机器人不是同一主线。9月30日子公司担保公告披露实际担保余额约6.55亿元/净资产20.38%、授权额度约14.17亿元/44.13%，另有高负债子公司；不是新增订单或无风险背书。先作30天研究，综合短线不选。

兆威机电003021：微型传动/机器人方向同步，收72.57突破前20高72.30但距日高73.70有上影，含T的MA60约72.587尚未有效收回。9月8日24,800股限制股回购注销为员工离职激励处理，不是市场主动回购信号；9月3日期权自主行权公告所涉潜在稀释、8月解除限售公告均保留，不能说新产业订单。相较全志尾盘绝对推进/无封板可买性证据不占优，不凑第二只。

戴维医疗300314：突破仅盘中高13.58越前20高13.40，收13.23未站稳；医疗主线同步较弱、换手14.41%。10月16日协议转让过户和9月8日控股股东减持预披露均查阅：10月8日—2027年1月7日计划合计不超过3%，实际是否/多少已减持未知。持股转让不等于公司新增经营现金。失效位12.28冻结，保留风险、不升级综合。

所有新样本原价OHLC与Sina同日核对，20%制度和涨停/停牌限制单列；公开资金/换手不能认定机构长期建仓，无同日榜也不能推断无机构。具体分时点、三档RVOL和初始量价快照与独立量价报告关联，不重复计为第二组交易。

B. 全部既有32/32验证，不删失败

{table}

当前4只收破原失效、历史8只曾收破；双环传动002472今天收回原位也保留10月8日收破过程，不能恢复成从未失败。蓝色光标300058当前相对原参考-5.206%、深桑达Ａ000032约-7.58%、天顺风能002531约-14.27%，均不删除；南威软件603636约+12.96%同样不能代替30天结论。全部32条原始模型/初始失效不变，后续只追加。日线参考收盘匹配核验，部分股票只有单一当前日线源，明确缺独立日线交叉，不夸称32条全部双源验证。

C. 到期、路径与节点

最早样本9月23日，截至10月20日仅27自然日，30天到期0；无已完成30天成功/失败归因。自然日1/3/5/10/15/20/30节点遇休市取不晚于目标日最近已闭市数据，同时单列5/10/20交易日，真实录入日期与价格日分离。初始收盘之后的日线极值用于MFE/MAE价格观察，剔除信号日收盘前极值，沿用low_price_observation_v2_20261019；旧记录不改。新增逐日收盘峰到谷回撤为收盘路径回撤，不是日内最大回撤或策略净回撤。量/前日≥1.5的后续事件逐条留档，只是二次放量诊断，不能断言吸筹/资金持续。

D. 统计、验证与下一假设

原32、新增3，原主模型分布{dict(models)}。30天有效N=0，均值/中位、胜率、盈亏比、10%/20%达标比例及可执行净收益N/A；原始参考价缺证或统计不合格者沿用不合格标签，不能以补了今日行情恢复历史资格。自然/交易日、长假与普通隔夜、20%与10%分别保留。

待证伪：同为120日低中位，短期突破（兆威）能否较尚未越前高（戴维）或5日量未显著放大（首航）获得更持续价格推进；分别跟踪原位失效、二次量、板块变化和担保/减持影响，不改阈值凑优胜者。本台账不是实际持有组合，没有买卖成交；若21日真实买入最早22日卖出，买入日无法即时止损，跌停/停牌可使后续退出受阻。不保证收益。'''
    return report('low_position', '低位启动30天｜10月20日32只全路径验证与3只新样本',
                  '32/32原样本继续跟踪，当前4只、历史8只收破原位；新增首航新能、兆威机电、戴维医疗，30天成熟0，均非综合买入指令。',
                  body, e, stamp, research_rule_version='low_position_30d_v1', existing_sample_count=32,
                  new_sample_count=3, mature_30d_count=0, codes=[r['code'] for r in vals + new],
                  observation_calculation_version='low_price_observation_v2_20261019')


def dragon_report(e, stamp):
    d = e['dragon_tiger']; ss = d['selected_observations']
    table = tab(['代码/名称', '所选精确区间原因', '买/卖/净亿元', '买一/卖一占各侧前五%', '机构通道净万元', '股通通道净万元'],
                [[s['code'] + ' ' + s['name'], s['selected_period_reason'],
                  '/'.join(sg(s[k] / 1e8, 4) for k in ('buy_cny', 'sell_cny', 'net_cny')),
                  f(s['buy_concentration_top1_pct']) + '/' + f(s['sell_concentration_top1_pct']),
                  sg(s['channel_group_flows']['institution_channel']['net_cny'] / 1e4),
                  sg(s['channel_group_flows']['stock_connect_channel']['net_cny'] / 1e4)] for s in ss])
    seats = []
    for s in ss:
        for side in ('buy', 'sell'):
            seats.append(s['code'] + ' ' + s['name'] + ('买' if side == 'buy' else '卖') + '侧前五：' +
                         '；'.join(x['OPERATEDEPT_NAME'] + '，买' + f(float(x.get('BUY') or 0) / 1e4) + '万元/卖' +
                                   f(float(x.get('SELL') or 0) / 1e4) + '万元' for x in s[side + '_seats_em']) + '。')
    profiles = tab(['公开营业部/通道标签', 'T19样本N', 'T20平均收盘观察%', '身份/持有期'],
                   [[x['public_label'], x['N'], sg(x['mean_next_close_price_pct']), '未确认/不可推断']
                    for x in d['public_channel_forward_profiles']])
    body = f'''一、完整研究范围与口径

T={T}，完成{stamp}。东方财富82条原因、67去重代码，沪深00/30/60/68开头A股58个；其余含北交所、可转债等制度，不混分母。同花顺同日摘要及明细157张表留档，其摘要包含单日/三日多区间，不把表数当股票数。全部82原行、精确TRADE_ID、区间、金额留存。优先展示5只不同角色，不按净买榜机械推荐；机构专用、股通按披露名称作通道分类，市场游资别名不是确认资金身份。

环境：上证+0.12%、深成-0.14%、创业板-0.26%、科创50+1%，宽度3777/1668；普通非ST主板本地代理46封/79触/33未封/6跌停，炸板代理约41.8%，非全市场。机器人/边缘AI/软件较强，煤炭/贵金属等弱；修复有板块支持，但昨日高换手净买样本没有普遍强隔夜回报。完整逐层名单源403、T前20交易日最高连板参照不全，1进2/2进3/3进4原分母及全层晋级率未知。可见最高与风险公告另列，不能用媒体总体晋级率替代。

二、5只独立观察/风险样本及资金勾稽

{table}

5/5分别按股票+日+TRADE_ID核对；深市买卖前五并集去重与沪市每侧前五不同，金额基准保留。买一集中度分母是买侧前五，卖一同理，不能与整榜并集混用；同名机构专用不等于同一账户。公开买/卖两侧并存仅是交易交换线索，不能确认为做T、对倒、锁仓或量化身份。

{chr(10).join(seats)}

润建股份002929：单日净买18.86万元，不能写成三日5024.54万元；机构专用净卖约7782万元、股通通道约2073万元，与10%封板并存。10月21日异动公告（实际已取得）提示2亿美元服务合同按实际消耗结算、预计不对2026全年整体业绩构成重大影响，存在履约/交付、投入和政策风险，半年度归母净利润同比下降31.72%；10月21登记、22日除息每10股0.18元。21日仅研究非一字、49.60—50.30缩量守住后重站50.70、两只算力同伴同步；高开52.00以上、破49.20、量大价不进/关键盘口缺失放弃。这里只是龙虎榜观察，综合不选。

长春一东600148：RVOL20=14.476、换手22%，榜净卖约2684万元、机构通道净卖约2863万元。21日已公开风险提示披露16—20日累计3个收盘涨停，静态PE243.88 vs同行28.49、基本面无重大变化；故是高位/异常波动风险样本，不因封板晋级而正向推荐。即使19.00—19.40有价格承接也不激活买入；证券状态、估值风险未解消/开板无承接/高开追价均放弃。

宁波东力002164：收16.16、+10.01%、换手12.99%，总榜净买1.152亿元但机构通道净卖约1615万元、股通通道净买4568万元，方向不一致，不能称机构游资统一锁仓。21日异动公告保留；16—20日连续涨停的区间需与具体逐日行情核对，不用三日偏离代替连板。仅观察普通成交15.55—15.85回踩后重站16.05、机器人两同伴和高标无跌停；高开16.80以上、破15.30/一字/爆量不进放弃，综合不追高乖离。

冰山冷热000530：8.17、换手44.41%、距MA20+41.77%，当日净卖4168万元、机构通道净卖2565万元；T19净买转T20净卖不能证明同一账户兑现。仅作高位分歧对照，21日非一字7.80—8.00承接再站8.18、冷链同伴同步且关键盘口完整才研究；高开8.45以上、破7.62、反复开板无承接放弃，不自动推荐。

长盈精密300115：20%封板、24.67，RVOL20=4.039，机构专用通道净买6337万元、股通通道净买1.162亿元，合力线索较强但不能断言锁仓或明日可买。10月16日控股股东/实控人未来6个月不减持承诺和9月30日担保分别核对，承诺不等于全体股东无供给风险。21日仅观察非一字23.40—23.95缩量不破后重站24.25、两只消费电子同伴正向；高开25.40以上、破23.00、排板无普通成交/同伴转弱放弃。20%制度隔夜风险独立，不混普通主板打板。

以上全部是研究条件，不是委托、实际成交或综合最终候选。21日若有真实买入，22日才可卖，21日破位不能当天卖；22日跌停/停牌仍可能无法退出。

三、上一5/5完整前推与画像积累

{validation_table(d['previous_validations'])}

T19→20两只收涨，均值+0.299%/中位-0.097%；开盘均值-1.621%，日高均值+4.547%、日低均值-5.230%。慈文传媒002343前日净买约2.158亿元而20日收10.25（-0.097%），同日榜净卖1.032亿元且异动公告持续；这是强席位标签不能保证次日推进的反例。天津普林002134小幅收涨0.545%，冰山+4.744%、万丰奥威002085约-1.193%、新华传媒600825为其余风险对照，全部保留。

{profiles}

画像按公开营业部编码/原区间关联原样本。小N中只报告价差与角色，首板/趋势/高位接力偏好、常见持有期、做T概率、稳定胜率均待证，不把机构专用代码0当一个持仓人，不删除净卖/次日失败。席位组合×位置×板块×情绪×封板质量×集中度标签逐条留档，分组N不足且无两侧成交，不计算策略净胜率、盈亏比或实际退出质量。

四、下一项可证伪假设

比较同样净买下有无量价推进/普通成交、及机构通道与总榜方向不一致的后续表现。润建单日近零净买、长盈同向净买、冰山/长春净卖与高换手分别冻结，不因事后上涨改标签。龙虎榜只提供综合筛选的支持/反对，未上榜全志不能获得资金加分，也不会因未上榜被伪称无机构；不保证收益。'''
    return report('dragon_tiger', '龙虎榜完整研究｜10月20日精确区间、5只席位勾稽与风险反证',
                  '82原因/67代码、沪深A58；5只精确区间金额勾稽，前5全部验证；润建单日净买18.86万元而非三日5024.54万元，机构身份与成交仍不可推断。',
                  body, e, stamp, research_rule_version='dragon_tiger_close_v2', codes=[s['code'] for s in ss] + [r['code'] for r in d['previous_validations']],
                  observation_count=5, previous_pool_verified_count=5, seat_reconciliation_verified_count=5)


CARD = '''唯一综合条件候选：300458 全志科技，模型combined_limitup_watch_v5（反弹推进/业绩与量价共振，非已确认主升）。T20原收盘参考28.64元，行情日15:00、报告冻结在下列真实时间；该参考不是买价，20%制度，T20涨11.27%不是涨停。

为什么胜过替代：相较润建/长春/宁波的封板可买性与高乖离/公告风险，全志没有封20%板，CLV1、尾盘+2.18%、换手7.86%且含T的MA20下方约5.02%，未处大幅正乖离。10月12日业绩预告预计前三季归母6.4—6.7亿元（同比+129.85%—140.62%）、扣非6.1—6.3亿元，未经审计；上游成本涨价、研发费用增逾30%仍是风险。10月20日工商变更为激励股份归属相关，不是新订单。价在MA20/60下方、当天大涨后回吐与半导体板块分化是反证，不能称趋势已扭转。没有同日龙虎榜席位支持，不推断资金身份。

T+1=10月21日事前冻结条件（全部同时满足，最多一次，不临时换股）：9:25核正常证券状态、复权/停牌、真实当日上限；竞价及实际开盘均须27.90—29.10。09:45—10:30先出现28.00—28.30普通成交回踩，最低不破27.85，回踩五分钟成交量小于紧前上攻五分钟，随后重站28.50并连续五个可核验一分钟价点不低于28.50、向28.70推进；只在28.55—28.85区间出现可验证普通成交时才可记触发，不用限价排队或日高代替成交。回踩区取T20下午约28元平台，27.70失效低于14点后最低价格点27.97及原平台，是事前风险假设非优化回测阈值。

预定同伴002929润建股份、603341龙旗科技均较T20收盘不低于-2%，至少一只上涨、非一字且无高标跌停共振；同口径市场上涨≥2800、普通主板非ST跌停≤14。早盘量比只能用同一时点可比口径另核，不能把RVOL20=1.821套成盘中量比。任何数据缺失/公告风险新增、开盘超范围、价格先破27.85、追至29.30以上、板块/宽度不符或10:30仍未完成顺序，直接放弃，不尾盘补单。不允许用以后分时把当时缺失证据补成已买。

初始失效27.70。若21日实际买入后跌破，A股T+1锁定使当天不能卖；记录实际数量/成交成本与无法卖出的敞口，不加仓摊低，不把止损位当成交保证。最早22日可执行退出：弱开低于实际买入均价或可核价跌破27.70，在首个能证明可成交的时点全部退出；否则50%在开盘首个可成交时点，25%观察30.15（含T MA20压力），25%观察31.20；开盘后若先跌破28.64，余仓在首个可成交时点退出，未成交余仓最迟10:30首个可成交时点退出。两侧数量与先后均留证，跌停无买盘/停牌/委托未成则保留未退出风险、下一交易日首个可成交时点延续，不伪填成交价。成本20bp仅未校准占位，真正净收益须实际费用/滑点与数量，不从观察价直接扣成利润。

涨停路径假设：D先承接再收复29.30、30.15—30.50压力，若边缘AI/半导体同步扩散，才研究更高加速；D按T20昨收算20%上限参考34.37，仍以交易所实际状态为准。T+2上限取决D真实收盘，现在不可预填。反例是D高开后量大价不进、跌回28元平台、同伴下杀、MA20压制或公告风险变化；任一可使路径失败。D涨停若无普通成交不能默认买到，买到也只是浮盈；T+2涨停也不保证流动性或后续溢价。不给涨停概率和收益承诺。'''


def combined_report(e, stamp):
    r = load('research.json')['items']; receipts = load('task_runs.json')['items']
    prior = [x for x in r if x.get('task_id') == 'combined_pair' and x.get('eligible_for_integrated_research')]
    verified_dates = sorted({x['date'] for x in prior if any(y.get('status') == 'completed' and x['id'] in y.get('report_ids', []) for y in receipts)})
    old = tab(['原样本/日期', 'T20收盘', '相对原参考观察%', '到期交易日节点数', '成交状态'],
              [[x['code'] + ' ' + x['name'] + '/' + x['reference_date'], f(x['ohlc']['close']),
                sg(x['price_return_to_T_pct']), len(x['horizons']), '旧状态保留/不由今日价格激活'] for x in e['combined_horizon_validation']])
    body = f'''综合盘后组｜T={T}；计划介入D={D}，最早合法卖出{EXIT}；实际完成/冻结{stamp}。

决定：最多两只中的1只条件观察，全志科技300458；不凑第二只。竞价后再次验证，不是开盘即买，没有真实成交或收益承诺。量化痕迹已取消，不作为前置；自动扫描或配置审计不被计为完整研究。

一、同T四份完整原研报和真实回执

market_review={MARKET}（20日16:56:19北京时间完成，真实completed及生产交付已查）；volume_price={IDS['volume_price']}、low_position={IDS['low_position']}、dragon_tiger={IDS['dragon_tiger']}为本次缺项实际完整补做，实际完成均{stamp}、各自run_id/回执独立。报告、全部原样本、候选条件和回执本次原子追加；本段只说明分析齐备，不先称CI/生产已发布。低位/龙虎榜联合仅编排，原栏目独立。未发现同T既有综合完成决定或运行中原模块，按T唯一id冻结，不重复改两只。

二、从全A入口重新裁决

5574原始/5568有效扫描、120广泛池，独立复核108足够复权历史；28深研全部保留，其中26完整复权历史、2原价辅助/明确前复权缺项，不虚报120全历史。覆盖机器人、半导体、软件、消费、医药、汽车/军工、能源设备等至少五方向；不是从持仓/用户询问名单出发。并非机械抄市场复盘两只：复盘的阿尔特被本任务否决，低位新增和龙虎榜样本也独立比较。

市场支持：3777涨/1668跌、沪深量1.456万亿元，约较前日增186亿元，机器人/边缘AI/软件活跃。反对：深成/创业板收跌、普通非ST主板触板79/封46/未封33约41.8%炸板代理，高位换手和完整梯队缺项。量价支持：全志CLV1、尾盘推进、RVOL20=1.821；反对：前池28收盘均值-0.274%、累计56均值-1.109%，全志尚未收MA20/60，不能单因宽度修复追涨。低位支持：观察从低中位向短期突破的路径；反对：全志未满足原30天新增门槛（当日涨11.27%超过8%），不是强行列入低位样本；三只合格低位样本的尾部/催化不优。龙虎榜不给未上榜全志资金加分；润建近零单日净买、长春/冰山净卖及异动风险反对追高，长盈同向净买也不能解决20%封板次日可买性。

至少三个被替代者：阿尔特300825收11.52、CLV0.737/振幅19.47%/高12.06近压、短期反弹较快及质押风险，弱于全志收盘推进；兆威机电003021虽机器人同步且达30天规则，72.57未站稳MA60约72.587、上影73.70及激励行权/供给因素，保留长期研究不升第二只；金奥博002917虽CLV0.978、尾盘+1.55%，距MA20+17.70%且T19高13.18形成近压，不为凑数追；首航新能301658高换手/行业不同步和担保、戴维医疗300314未收前高及减持窗口继续否决；润建002929明示合同兑现不确定、22日除息，长盈300115封20%板，均不机械跟席位。两只前复权缺项大市值/新股宇树科技688836、摩尔线程688795只风险比较，不靠不完整因子升级。

三、唯一候选事前完整卡

{CARD}

四、上一组和全部原条件样本验证

上一T19综合组空仓，候选0、持仓0、策略盈利不适用，不把市场组广东宏大/宇环数控当综合持仓。最近T16中鼎股份000887在D19开17.12低于原17.40下限、全天高17.18也不到下限，原not_triggered/无成交结论保留；T20收17.30不会使旧D19条件重新激活。

{old}

全部8条原综合条件样本新增日线与已到1/3/5/10/20/30交易日节点、信号后高低观察及同日期上证基准；未到节点不填未来。旧时间/报价缺证、未触发、涨跌停/停牌/无成交样本不删除、不伪造恢复。分钟价格点不是分钟OHLC、不能推断触发/失效/目标先后，更不能以次日最高替代可执行收益。20日新候选尚无任何已实现表现。

五、重复率、版本与下一交易日重点

原已核完整综合日期{verified_dates}，近5/10交易日档案并非每天都有完整当时决定，严格全窗口重复率N/A；可核历史8条原推荐没有全志，本次代码与已有冻结推荐交集0/1，不等于已完成十日无重复统计。允许重选但须同日替代比较，不为低重复率换股。combined_limitup_watch_v5沿用事前条件框架，不由本次56价格观察自动调参；成本/策略胜率仍待成交级样本。

21日重点：①9:25正常状态及竞价/同伴/宽度；②28元平台回踩后量价顺序，缺证即不触发；③29.30/30.15压力下是否量大价不进，买入日T+1锁定风险；④跟踪原量价全池、新低位3条和龙虎榜5条，不只最终一只。APP仅展示归档与统计，没有内置大模型或自动训练权重；此处不是投资收益保证。'''
    return report('combined_pair', '盘后综合双标｜10月20日独立裁决1只条件观察，不凑第二只',
                  '四份同T完整研究齐备，综合盘后组仅全志科技300458条件观察；计划21日严格回踩再转强，最早22日卖出，上一组空仓，无成交收益可报。',
                  body, e, stamp, research_rule_version='combined_limitup_watch_v5', candidate_count=1,
                  selected_codes=['300458'], codes=['300458'] + [x['code'] for x in e['combined_horizon_validation']],
                  recommendation_ids=[RID], prerequisite_report_ids=[MARKET, IDS['volume_price'], IDS['low_position'], IDS['dragon_tiger']],
                  decision_id=IDS['combined_pair'], planned_entry_date=D, earliest_legal_exit_date_if_bought=EXIT,
                  broad_pool_count=120, broad_pool_verified_count=108, deep_pool_count=28)


def limitup_report(e, stamp):
    body = f'''每日打板v2独立事前风险裁决｜最新收盘T={T}，计划D={D}，实际完成/冻结{stamp}。

决定：空仓，无合格候选，不临时替补。D20完整事前空仓报告limitup-single-20261020-review-v2已有真实归档和completed，复用、不补造D20盘中荐股。本次只冻结尚未发生的D21。v2仍首轮20—30实际交易日模拟复核，非自动实盘或稳定规律。

一、最近三日情绪/梯队优先

T16修复：外部聚合61封/49炸（源名单仅59），本地普通非ST主板56封/54未封/14跌停；T19权重护盘但宽度2274涨/3129跌、沪深1.438万亿元，本地40封/36未封/25跌停；T20宽度3777/1668、沪深1.456万亿元、本地46封/33未封/6跌停，深成/创业板仍跌。聚合口径和代理口径分别记录，不合成全市场晋级率。情绪从普遍弱隔夜向修复、分歧仍大，机器人/边缘AI比煤炭贵金属强，单日修复不足以消除断板尾部。

二、市场/主线高度、空间与进阶板

公开可见大业股份603278、长春一东600148处较高层；长春21日原风险公告明确16—20日累计3个收盘涨停，是可核日历事实，不由三日榜硬推板数。市场复盘当时仅列大业可见3板，本次追加公告不改旧报。福莱新材605488、宁波东力002164、浙江荣泰603119为可见2板研究参照，但完整普通主板1/2/3/4/5+梯队与主线高度、T前20交易日连板上限/周期起点仍未完整恢复；原公开逐层源403，不绕过访问限制、不填0。空间板工作定义为试图打开本轮上限者，缺上限不硬定空间龙。1进2/2进3/3进4及更高分母须T-1逐股原名单，原总数/缺失率未知，不能以总体炸板率代替晋级率。20%/ST/30%/转债与普通主板10%分开。

三、至少三只真实T备选，先角色后否决

长春一东600148：T收19.70、10%封板、前3收盘涨停可核，计划3进4参照，RVOL20=14.476、换手22%、榜净卖2684万元；21日风险公告PE243.88 vs同行28.49且基本面无重大变化。高位加速、空间上限/成交证据不清，否决。

宁波东力002164：T收16.16，机器人可见2板/计划2进3，RVOL20=1.831、距MA20+28.70%、换手12.99%；总榜净买不等于机构同向，机构通道净卖约1615万元、21日异动风险需关注。完整主线晋级分母/高标负反馈不明，否决。

润建股份002929：T收51.04封10%，AI词元服务事件/换手核心待确认，当前连续板数不能单看三日榜决定，计划角色不硬填；RVOL20=5.126、单日净买仅18.86万元，机构与股通通道净卖。合同实际结算及兑现不确定、21登记22除息（每10股0.18元），不能使用未除息静态价作次日退出收益，否决。

龙旗科技603341：T收38.26、10%封板、RVOL20=3.361、换手9.60%左右（精确源快照优先），边缘AI跟随/计划层级待完整梯队确认；晚段价格贴板不证明D排队可成交，证券状态/同伴/主线高度不全，否决。全志300458虽为综合条件观察但T未封20%板，非普通主板1进2；长盈300115为20%制度，不混入本实验。新华传媒600825历史高位风险不因今天价格变化追补。

四、成交卡、T+1与固定退出

候选=0，D介入范围/真实涨停价/失效/目标均N/A，上述T收盘只是比较原证据，不是买价。沿用v2未来新候选最低框架：正常非ST普通主板证券、真实D上限、竞价0—5%、09:35—10:30、换手2—12%、首次开板后60秒守真实上限98%及成交均价、事前两同伴≥3%且高标未跌停，必须普通成交证据，缺任何关键项不激活。该段是规则说明，不授权临时换股。当前9:25尚未发生，不能称已通过。

若未来D21出现另有事前完整冻结且真实买入的候选，最早D+1=22日09:30首个可证明成交时点退出，强/平/弱开同一规则。21日炸板不能当日卖，22日跌停无买盘、停牌或委托未成保留风险并顺延首个可成交时点。止损阈值不是保证成交，T+1最高涨幅不代替策略收益。本次空仓，无买入触发/委托/持仓，不虚构封板率/炸板率策略样本。

五、旧样本、统计与下一假设

v1龙溪股份600592原未触发/无持仓不按v2重评；旧完整空仓、历史缺事前交付的blocked/事后补证分开，不把补证当按时空仓。D20真实事前空仓复用，本D21新增完整风险裁决。交易样本N=0，次日净收益/胜率、盈亏比、尾部亏损、可执行MFE/MAE与退出质量N/A，未校准20bp不虚扣成利润。高度/空间/晋级/情绪/长假/版本分组仍有缺项。待验证只有低层晋级、换手承接及高标反馈同时修复，隔夜尾部风险才可能收敛；不借款融资追板、不下单、不自动训练。'''
    # Use observed turnover rather than rounded memory in the final report.
    q = next(s for s in e['volume_price']['deep_samples'] if s['code'] == '603341')
    body = body.replace('换手9.60%左右（精确源快照优先）', '换手' + f(q['turnover_pct']) + '%')
    return {'id': 'limitup-single-20261021-review-v2', 'date': D, 'market_date': T,
            'task_id': 'limitup_single', 'track': 'market_review', 'title': '每日打板v2｜计划10月21日空仓，三日修复与梯队缺项否决',
            'summary': 'T20、D21事前完整空仓裁决；三日市场、空间/晋级缺项与至少4只真实备选逐项否决，无候选无成交。',
            'body': body, 'sources': sources(e), 'published_at': stamp, 'recorded_at': stamp,
            'data_cutoff_at': stamp, 'report_type': 'full_pre_market_risk_decision',
            'eligible_for_integrated_research': False, 'provenance': 'contemporaneous_pre_market_cash_decision',
            'planned_entry_date': D, 'latest_completed_trading_day': T, 'research_rule_version': 'limitup_single_v2',
            'run_id': 'limitup-single-20261021-scheduled-v2', 'candidate_count': 0, 'selected_codes': [],
            'recommendation_ids': [], 'decision': 'cash_no_qualified_candidate', 'ladder_complete': False, 'evidence_file': EFILE}


def recommendation(e, stamp):
    s = next(x for x in e['volume_price']['deep_samples'] if x['code'] == '300458')
    return {'id': RID, 'date': T, 'published_at': stamp, 'task_id': 'combined_pair', 'code': '300458', 'name': '全志科技',
            'group': 'close', 'group_label': '综合盘后组', 'strategy': 'combined_limitup_watch',
            'model': 'combined_limitup_watch_v5', 'reason': '反弹推进与未经审计业绩预告共振；MA20/60未收回，只有次日严格回踩再转强且同伴/宽度一致才观察。',
            'reference_price': 28.64, 'reference_price_time': T + 'T15:00:00+08:00', 'reference_market_date': T,
            'reference_price_source': s['daily_source'], 'crosscheck_source': 'https://hq.sinajs.cn/list=sz300458',
            'trigger': CARD, 'invalid': '27.70为初始失效；入场前破27.85或任一共同条件失败直接放弃，10:30未完成不补单。',
            'exit_plan': '最早22日；弱开/破27.70首个可成交全退，否则50%开盘、25%@30.15、25%@31.20；先破28.64退余仓，10:30退出余仓；无成交保留风险。',
            'sources': [EFILE, s['daily_source'], 'https://static.cninfo.com.cn/finalpage/2026-10-12/1225601760.PDF'],
            'provenance': 'contemporaneous', 'report_ids': [IDS['combined_pair']], 'planned_entry_date': D,
            'earliest_legal_exit_date_if_bought': EXIT, 'entry_price_condition_range': [28.55, 28.85], 'invalid_level': 27.70,
            'rules': {'version': 'combined_limitup_watch_v5', 'frozen_at': stamp, 'entry_sequence_required': True,
                      'entry_window_cn': ['09:45', '10:30'], 'auction_open_range': [27.90, 29.10],
                      'pullback_range': [28.00, 28.30], 'pullback_floor': 27.85, 'reclaim': 28.50,
                      'hold_minute_price_points': 5, 'invalid_level': 27.70, 'no_chase_above': 29.30,
                      'peer_codes': ['002929', '603341'], 'peers_each_min_change_pct': -2,
                      'at_least_one_peer_positive': True, 'same_scope_advance_min': 2800,
                      'ordinary_mainboard_limit_down_max': 14, 'exit_weights_pct': [50, 25, 25],
                      'exit_target_prices': [None, 30.15, 31.20], 'remaining_exit_deadline_cn': '10:30',
                      'cost_assumption': {'round_trip_bps': 20, 'calibrated': False, 'use_for_executable_statistics': False}},
            'frozen_snapshot': s, 'results': []}


def append_observations(e, stamp, recs, volume, low):
    recmap = {r['id']: r for r in recs['items']}
    for row in e['combined_horizon_validation']:
        result = {'id': row['recommendation_id'] + '-daily-validation-20261020', 'recorded_at': stamp,
                  'as_of': T + 'T15:00:00+08:00', 'market_date': T, 'observation_type': 'price_observation',
                  'observed_open': row['ohlc']['open'], 'observed_high': row['ohlc']['high'],
                  'observed_low': row['ohlc']['low'], 'observed_close': row['ohlc']['close'],
                  'close_price_observation_pct': row['price_return_to_T_pct'], 'completed_horizon_observations': row['horizons'],
                  'executed_trade': False, 'executable_net_return_pct': None, 'report_id': IDS['combined_pair'],
                  'sources': [EFILE], 'trigger_status': row['trigger_status'],
                  'note': '旧原条件/未触发与缺成交状态不变；今日价格不重新激活旧D，不推断触发顺序或策略收益。'}
        if row['code'] == '000887':
            result.update(status='not_triggered', entry_fill_status='no_strategy_fill', strategy_sample_activated=False,
                          note='D19开17.12低于原17.40下限、全天高17.18；原未触发结论保留，T20不激活。')
        recmap[row['recommendation_id']].setdefault('results', []).append(result)
    volume['items'].append({'id': 'volume-price-20261019-validation-20261020-v1', 'date': T, 'recorded_at': stamp,
                            'task_id': 'volume_price', 'kind': 'full_forward_price_validation',
                            'origin_cohort_id': 'volume-price-20261019-close-v1-cohort',
                            'origin_report_ids': ['volume-price-20261019-close-v1'], 'report_ids': [IDS['volume_price']],
                            'rule_version': 'volume_price_close_v4', 'full_validation_completed': True,
                            'full_pool_summary': e['volume_price']['previous_statistics'],
                            'full_pool_validations': [dict(r, id='volume-price-20261019-' + r['code'] + '-validation-20261020',
                                                          recorded_at=stamp, report_ids=[IDS['volume_price']],
                                                          origin_cohort_id='volume-price-20261019-close-v1-cohort',
                                                          full_validation_completed=True, eligible_for_model_statistics=True,
                                                          daily_high_price_excursion_pct=r.get('high_observation_pct'),
                                                          daily_low_price_excursion_pct=r.get('low_observation_pct'))
                                                      for r in e['volume_price']['previous_validations']],
                            'frozen_structure_statistics': e['volume_price']['previous_by_frozen_structure'],
                            'cumulative_v4_price_statistics': e['volume_price']['cumulative_v4_next_day_price_statistics'],
                            'executable_sample_count': 0, 'eligible_for_model_statistics': True})
    volume['items'].append({'id': 'volume-price-20261020-close-v1-cohort', 'date': T, 'task_id': 'volume_price',
                            'frozen_at': stamp, 'report_ids': [IDS['volume_price']], 'rule_version': 'volume_price_close_v4',
                            'data_cutoff_at': T + 'T15:00:00+08:00', 'broad_pool_count': 120,
                            'broad_pool_verified_count': 108, 'deep_screen_count': 28,
                            'deep_adjusted_history_verified_count': 26, 'eligible_for_model_statistics': True,
                            'provenance': 'contemporaneous_close_research', 'samples': e['volume_price']['deep_samples']})
    lowmap = {s['id']: s for s in low['items']}
    for obs in e['low_position']['existing_validations']:
        sample = lowmap[obs['origin_cohort_id']]
        sample.setdefault('observations', []).append(dict(obs, recorded_at=stamp))
        bs = e['raw_daily_histories'][sample['code']]; orig = date.fromisoformat(sample['date']); nodes = []
        for n in (1, 3, 5, 10, 15, 20, 30):
            target = orig + timedelta(days=n)
            if target > date.fromisoformat(T):
                continue
            allowed = [b for b in bs if sample['date'] <= b['date'] <= target.isoformat()]
            if allowed:
                nodes.append(('natural_day', n, target.isoformat(), allowed[-1]))
        post = [b for b in bs if sample['date'] < b['date'] <= T]
        for n in (5, 10, 20):
            if len(post) >= n:
                nodes.append(('trading_session', n, post[n - 1]['date'], post[n - 1]))
        for kind, n, target, b in nodes:
            nid = sample['id'] + f'-{kind}-{n}'
            if any(x.get('id') == nid for x in sample['observations']):
                continue
            path = [x for x in post if x['date'] <= b['date']]; ref = sample['day0_close']
            sample['observations'].append({'id': nid, 'date': b['date'], 'recorded_at': stamp, 'target_date': target,
                                           'horizon': n, 'horizon_type': kind, 'close': b['close'],
                                           'close_return_pct': round((b['close'] / ref - 1) * 100, 3),
                                           'path_mfe_pct': round((max(x['high'] for x in path) / ref - 1) * 100, 3) if path else None,
                                           'path_mae_pct': round((min(x['low'] for x in path) / ref - 1) * 100, 3) if path else None,
                                           'observation_type': 'price_observation', 'executable_net_return_pct': None,
                                           'report_ids': [IDS['low_position']], 'source_urls': obs['source_urls'],
                                           'calculation_version': 'low_price_observation_v2_20261019'})
    for s in e['low_position']['new_candidates']:
        low['items'].append({'id': 'low-position-20261020-' + s['code'], 'date': T, 'recorded_at': stamp,
                             'code': s['code'], 'name': s['name'], 'sector': SECTOR[s['code']],
                             'primary_model': '低中位放量推进/平台确认', 'day0_close': s['close'],
                             'invalid_close_below': s['low'], 'initial_invalidation_basis': '收盘跌破信号日低点；不后移',
                             'original_snapshot_provenance': 'contemporaneous_full_market_and_crosschecked_daily',
                             'original_snapshot_verified': True, 'eligible_for_model_statistics': True,
                             'day0_rvol20': s['rvol']['20'], 'day0_turnover_pct': s['turnover_pct'],
                             'day0_amount_yi': s['amount_cny'] / 1e8, 'day0_clv': s['clv'],
                             'day0_range_position_pct': s['range_position_pct'], 'day0_moving_averages': s['ma'],
                             'snapshot': s, 'report_ids': [IDS['low_position']], 'observations': [], 'sources': [EFILE, s['daily_source']]})
    low['updated_at'] = stamp


def catalog_updates(e, stamp, catalog):
    known = {s['code']: s for s in catalog['items']}; updates = {}
    for r in e['low_position']['existing_validations']:
        updates[r['code']] = (r['name'], IDS['low_position'],
                               f"T20收{r['price_observation']['close']:.2f}，相对原参考{r['close_return_pct']:+.3f}%；曾收破原位={r['ever_verified_close_below_original_invalid']}，当前收破={r['observed_close_below_original_invalid']}。原路径保留，30天未成熟。")
    for r in e['combined_horizon_validation']:
        updates[r['code']] = (r['name'], IDS['combined_pair'],
                               f"T20收{r['ohlc']['close']:.2f}、相对原参考{r['price_return_to_T_pct']:+.3f}%；旧触发/未成交状态保留，不因今日价格重新激活旧条件。")
    for s in e['low_position']['new_candidates']:
        updates[s['code']] = (s['name'], IDS['low_position'],
                               f"新增独立30天研究：收{s['close']:.2f}、RVOL20={s['rvol']['20']:.3f}、120日位置{s['range_position_pct']['120']:.1f}%、初始失效{s['low']:.2f}；公告风险见完整报告，不是综合短线指令。")
    updates['300458'] = ('全志科技', IDS['combined_pair'], '综合盘后组唯一条件观察：T20收28.64，D21仅28.55—28.85严格回踩再转强，27.70失效，最早22日卖出；MA20/60未收复与成本/研发风险并存。')
    # New nonselected names are not automatically added to the user's watchlist.
    changed = []
    newcodes = {s['code'] for s in e['low_position']['new_candidates']} | {'300458'}
    for code, (name, rid, reason) in updates.items():
        stock = known.get(code)
        if stock is None and code not in newcodes:
            continue
        if stock is None:
            stock = {'code': code, 'name': name, 'sector': SECTOR.get(code, '边缘AI/半导体'),
                     'role': 'research', 'default_watch': False, 'history': []}
            catalog['items'].append(stock)
        stock['history'].append({'id': f'research-stock-{code}-20261020-validation', 'date': T,
                                 'recorded_at': stamp, 'title': '完整研究后新增核验与风险，不改写原理由',
                                 'reason': reason, 'evidence_status': 'verified_daily_research_with_explicit_execution_gaps',
                                 'fact_note': '真实完成时间录入；价格观察不是成交收益，原模型/失效和失败保留。',
                                 'validation': ['继续原节点及前推；只有事前冻结与真实条件/成交证据齐备才认定触发。'],
                                 'risk': '公告、板块、T+1锁定及涨跌停/停牌约束见关联全文，日线极值不推断时序或净收益。',
                                 'report_ids': [rid], 'sources': [EFILE]})
        changed.append(code)
    return changed


def main():
    research, recs, runs, volume, low, catalog = map(load, ['research.json', 'recommendations.json', 'task_runs.json',
                                                         'volume_price_samples.json', 'low_position_samples.json', 'research_stocks.json'])
    if any(r['id'] == IDS['combined_pair'] for r in research['items']):
        print('Same-T decision already frozen; no duplicate.'); return
    assert any(r['id'] == MARKET and r.get('eligible_for_integrated_research') for r in research['items'])
    assert any(r.get('status') == 'completed' and MARKET in r.get('report_ids', []) for r in runs['items'])
    assert not any(r['date'] == T and r['task_id'] in IDS and r.get('status') == 'running' for r in runs['items'])
    now = datetime.now(timezone.utc); stamp = now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    e = prepare_evidence(load_evidence(ROOT / EFILE), stamp)
    assert len(e['volume_price']['deep_samples']) == len(e['volume_price']['previous_validations']) == 28
    assert len(e['low_position']['existing_validations']) == 32
    assert all(x['seat_reconciliation']['matched'] for x in e['dragon_tiger']['selected_observations'])
    newreports = [volume_report(e, stamp), low_report(e, stamp), dragon_report(e, stamp), combined_report(e, stamp)]
    limit = limitup_report(e, stamp)
    research['items'].extend(newreports + [limit])
    append_observations(e, stamp, recs, volume, low)
    recs['items'].append(recommendation(e, stamp))
    completed = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for r in newreports + [limit]:
        runs['items'].append({'id': r['run_id'] + '-completed', 'run_id': r['run_id'], 'task_id': r['task_id'],
                              'date': r['date'], 'trigger': 'scheduled', 'started_at': e['execution_started_at_utc'],
                              'recorded_at': completed, 'completed_at': completed, 'status': 'completed', 'summary': r['summary'],
                              'report_ids': [r['id']], 'analysis_completed': True, 'recommendation_ids': r.get('recommendation_ids', []),
                              'delivery_status': 'repository_prepared_not_yet_verified', 'sources': [EFILE],
                              'started_at_scope': '真实本轮读取、取证与完整研究开始；各模块分别留档，非按定时时刻虚构。'})
    changed = catalog_updates(e, stamp, catalog)
    save(ROOT / EFILE, e)
    for name, obj in [('research.json', research), ('recommendations.json', recs), ('task_runs.json', runs),
                      ('volume_price_samples.json', volume), ('low_position_samples.json', low), ('research_stocks.json', catalog)]:
        save(DATA / name, obj)
    save(ROOT / 'app/src/main/assets/research_stocks.json', catalog)
    for r in newreports + [limit]:
        (ROOT / 'docs/research' / (r['id'] + '.md')).write_text(r['body'] + '\n')
    manifest = {'market_date': T, 'recorded_at': completed, 'report_ids': [r['id'] for r in newreports + [limit]],
                'reused_report_ids': [MARKET, 'limitup-single-20261020-review-v2'], 'changed_research_stock_codes': changed,
                'candidate_count': 1, 'recommendation_ids': [RID], 'decision_id': IDS['combined_pair'],
                'delivery_status': 'not_yet_CI_or_production_verified'}
    save(ROOT / 'docs/research/combined-pair-20261020-publication-manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
