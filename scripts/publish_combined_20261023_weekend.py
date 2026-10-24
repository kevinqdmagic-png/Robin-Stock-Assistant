"""Append the T23 integrated decision and reopening evidence; preserve every old record."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import copy
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
T = '2026-10-23'
D = '2026-10-26'
STARTED = '2026-10-24T09:49:23+00:00'
REPORT_ID = 'combined-pair-20261023-close-v1'
RUN_ID = 'combined-pair-20261023-scheduled-weekend-v1'
LIMITUP_ID = 'limitup-single-20261023-weekend-evidence-v2'
CONFIG_ID = 'combined-orchestration-20261024-audit-v1'
EVIDENCE = 'docs/research/combined-pair-20261023-decision-evidence.json'
ORIGINAL_LIMITUP = 'limitup-single-20261023-close-v2'
SCHEDULE = 'BEGIN:VEVENT\nDTSTART;TZID=Pacific/Auckland:20261001T223000\nRRULE:FREQ=DAILY;BYHOUR=0,6,22,23;BYMINUTE=30\nEND:VEVENT'


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def save(path, document):
    (ROOT / path).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def cn_now():
    return datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='microseconds')


def public_attempt(document):
    """Public evidence links original PDFs with checksums; do not republish complete filing text."""
    out = copy.deepcopy(document)
    for item in out.get('official_pdf_documents', {}).values():
        text = item.pop('text', None)
        item.pop('local_source_path', None)
        if text is not None:
            item['extracted_text_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
            item['full_text_omitted'] = 'Official source URL and original PDF SHA retained; read-only source PDF kept locally.'
    return out


def receipt(report, run_id, trigger, started_at, summary=None, extra=None):
    stamp = cn_now()
    row = {'id': run_id + '-completed', 'run_id': run_id, 'task_id': report['task_id'],
           'date': report['date'], 'trigger': trigger, 'started_at': started_at,
           'recorded_at': stamp, 'completed_at': stamp, 'status': 'completed',
           'summary': summary or report['summary'], 'report_ids': [report['id']],
           'recommendation_ids': [], 'analysis_completed': True,
           'delivery_status': 'repository_prepared_not_yet_ci_or_production_verified', 'sources': [EVIDENCE]}
    if extra:
        row.update(extra)
    return row


def report_base(report_id, task, title, summary, body, stamp, sources, kind):
    return {'id': report_id, 'date': T, 'market_date': T, 'task_id': task, 'track': 'market_review',
            'title': title, 'summary': summary, 'body': body, 'sources': sources,
            'report_type': kind, 'published_at': stamp, 'recorded_at': stamp,
            'market_data_cutoff_at': T + 'T15:00:00+08:00', 'data_cutoff_at': stamp,
            'information_boundary': 'T23 close prices plus official filings verified at the actual weekend review time',
            'planned_entry_date': D, 'earliest_legal_exit_date_if_bought': '2026-10-27',
            'provenance': 'weekend_reopening_maintenance_with_original_T23_research',
            'evidence_file': EVIDENCE, 'analysis_completed': True, 'status': 'completed'}


def main():
    research = load('backend/data/research.json')
    runs = load('backend/data/task_runs.json')
    tasks = load('backend/data/tasks.json')
    if any(r['id'] == REPORT_ID for r in research['items']):
        raise RuntimeError('T23 decision already exists; do not reselect or overwrite')
    first = load('docs/research/combined-pair-20261023-weekend-evidence.json')
    supplement = load('docs/research/combined-pair-20261023-weekend-supplement.json')
    api = dict(first['api_readback'])
    api.update(supplement['api_readback'])
    assert all(not row.get('error') and row['payload']['ok'] for row in api.values())
    online_reports = {r['id']: r for r in api['reports_t23']['payload']['items']}
    online_receipts = api['receipts']['payload']['items']
    for task, dep in first['dependency_audit'].items():
        r = online_reports[dep['report_id']]
        assert r['task_id'] == task and r['date'] == T and r.get('eligible_for_integrated_research') is True
        assert hashlib.sha256(r['body'].encode()).hexdigest() == dep['body_sha256']
        assert any(e['task_id'] == task and e['date'] == T and e['status'] == 'completed'
                   and dep['report_id'] in e['report_ids'] for e in online_receipts)
    assert ORIGINAL_LIMITUP in online_reports
    assert online_reports[ORIGINAL_LIMITUP]['planned_entry_date'] == D
    assert not any(r['date'] == T and r.get('eligible_for_integrated_research') is True
                   for r in api['combined_reports']['payload']['items'])

    official = {
        '300184-q3': {'source': 'https://static.cninfo.com.cn/finalpage/2026-10-23/1225615680.PDF',
            'disclosure_date': '2026-10-23', 'table_page': 2, 'audited': False,
            'revenue_ytd_cny': 10477300994.01, 'revenue_yoy_pct': 61.68,
            'net_profit_ytd_cny': 480436861.17, 'net_profit_yoy_pct': 208.16,
            'deducted_net_profit_ytd_cny': 485676364.00, 'deducted_profit_yoy_pct': 220.22,
            'operating_cash_flow_ytd_cny': -337664326.60,
            'receivables_end_cny': 3349755423.54, 'receivables_previous_year_end_cny': 2033678283.82,
            'cash_flow_explanation': 'Receivables not yet due, more supplier payments, taxes and payroll; not proof of irreversible deterioration.'},
        '002241-q3': {'source': 'https://static.cninfo.com.cn/finalpage/2026-10-24/1225619737.PDF',
            'disclosure_date': '2026-10-24', 'table_page': 2, 'audited': False,
            'revenue_ytd_cny': 68220433789.91, 'revenue_yoy_pct': .17,
            'net_profit_ytd_cny': 2618804249.11, 'net_profit_yoy_pct': 1.21,
            'q3_revenue_yoy_pct': -7.80, 'q3_profit_yoy_pct': -1.51,
            'q3_deducted_profit_yoy_pct': -3.56, 'operating_cash_flow_ytd_cny': -2637755661.80},
        '300503-project': {'source': 'https://static.cninfo.com.cn/finalpage/2026-10-21/1225612462.PDF',
            'disclosure_date': '2026-10-21', 'second_project_area_mu': 241,
            'finding': 'Second-project spending and progress depend on decisions and actual funds; not a contractual profit commitment or a customer order.'},
        '002724-1225621455': {'source': 'https://static.cninfo.com.cn/finalpage/2026-10-24/1225621455.PDF',
            'disclosure_date': '2026-10-24', 'consecutive_limitups': 6, 'cumulative_rise_pct': 77.41,
            'finding': 'Company warns of irrational speculation, rapid turnover and valuation risk; relevant thematic revenue limited.',
            'next_quarterly_disclosure_planned_date': '2026-10-27'},
        '603278-1225620006': {'source': 'https://static.cninfo.com.cn/finalpage/2026-10-24/1225620006.PDF',
            'disclosure_date': '2026-10-24', 'rise_since_oct16_pct': 77.14,
            'unrestricted_float_turnover_pct': 33.42, 'software_free_float_turnover_pct': 67.28,
            'finding': 'Robot tendon product still R&D/customer-sample stage, no mass production or substantive revenue; recent trailing profit negative.'}}
    for key, facts in official.items():
        pdf = ROOT / 'tmp/pdfs/combined-20261023' / (key + '.pdf')
        text = pdf.with_suffix('.txt')
        assert pdf.exists() and text.exists()
        facts['pdf_sha256'] = hashlib.sha256(pdf.read_bytes()).hexdigest()
        facts['extracted_text_sha256'] = hashlib.sha256(text.read_bytes()).hexdigest()
        facts['verification'] = 'Official original retrieved; financial table pages visually checked where numerical data used.'

    rows = {x['code']: x for x in first['recomputed_broad_pool']}
    rows.update({x['code']: x['price_structure'] for x in first['dragon_selected'] if x.get('price_structure')})
    codes = ['300184', '300503', '002241', '002009', '002747', '002354', '002724', '603278']
    evidence = {'schema_version': 1, 'research_date': T, 'planned_entry_date': D,
        'earliest_legal_exit_if_bought': '2026-10-27', 'actual_started_at': STARTED,
        'collection_attempts': {'first_pass': public_attempt(first), 'supplement': public_attempt(supplement)},
        'official_filing_facts': official, 'comparison_sample_codes': codes,
        'decision': {'id': REPORT_ID, 'group': 'close', 'cohort_label': '综合盘后组',
                     'strategy': 'combined_limitup_watch', 'rule_version': 'combined_limitup_watch_v5',
                     'candidate_count': 0, 'recommendation_ids': [], 'decision': 'cash_no_qualified_candidate'},
        'sample_accounting': {'new_market_scan': False, 'reused_full_scan': 5573,
                             'reused_broad_pool': 120, 'reused_deep_pool': 28,
                             'new_volume_price_samples': 0, 'new_limitup_candidates': 0,
                             'reused_limitup_full_report_id': ORIGINAL_LIMITUP,
                             'reused_previous_pool_validation_count': 28},
        'safe_schedule_snapshot': {'title': '综合双标＋每日打板', 'schedule': SCHEDULE,
            'timezone': 'Pacific/Auckland', 'enabled': True,
            'source': 'connected task private readback; private identifiers and prompt intentionally omitted',
            'source_configuration_updated_at': '2026-10-24T05:35:57.477389+00:00',
            'standalone_limitup_schedule_enabled': False},
        'cost_and_execution': {'executed_trade_count': 0, 'executable_net_return_pct': None,
                              'cost_assumption_bps_placeholder': 20, 'calibrated_costs': False,
                              'trade_execution_inferred_from_OHLC': False},
        'limitations': ['Latest twenty-session main-board ladder and complete tier-transition denominators remain unavailable.',
                       'No weekend live auction, order-book queue or fill evidence; D conditions are prospective.',
                       'Original MA definitions (excluding T versus including T) retained and explicitly separated.',
                       'No short-term rule or model weight changed, no calibrated success probability exists.']}

    cfg_stamp = cn_now()
    cfg_body = f'''配置核对时间{cfg_stamp}，关联研究交易日T={T}。本报告只记录安全配置快照，不代表交易研究或手机安装已完成。用户于10月24日要求将综合双标和打板合并，连接的现有任务已回读为启用，原单独打板外部调度已暂停；本轮只把这一实际状态同步到APP登记，不修改真实调度、不创建新任务。

combined_pair保留market_review、volume_price、low_position、dragon_tiger四个同T完整前置，并编排limitup_single；打板不是第五个综合前置。limitup_single保留独立栏目、原始规则、历史样本和回执，enabled表示研究模块启用，independent_schedule_enabled=false表示没有第二个外部独立打板调度。GitHub盘后局部兜底原有工作流保持原状，不冒充外部完整研究。

tasks.json中的时区、周期和执行归属均来自实际读回的安全快照；私有调度ID、完整提示词未公开。quant_research继续取消。此配置回执trigger=manual；本轮研究的scheduled回执另行追加。APP数据是否同步仍要通过CI、准确SHA发布及公开API核验。'''
    config_report = report_base(CONFIG_ID, 'combined_pair', '合并编排配置审计｜独立栏目保留，打板随综合执行',
        '同步10月24日已合并外部任务的安全配置快照；配置核对不计作完整交易研究。', cfg_body, cfg_stamp,
        [EVIDENCE, 'docs/current-execution.md', 'backend/data/tasks.json'], 'configuration_audit')
    config_report.update(eligible_for_integrated_research=False, configuration_date='2026-10-24')
    config_run = receipt(config_report, 'combined-orchestration-20261024-manual-v1', 'manual', cfg_stamp,
        extra={'execution_scope': 'configuration_audit_only', 'eligible_for_integrated_research': False})

    stamp = cn_now()
    dep_table = '\n'.join(f"|{task}|{x['report_id']}|{x['published_at']}|" for task,x in first['dependency_audit'].items())
    comparison = []
    for code in codes:
        x = rows[code]
        rs = '/'.join(f"{x['rvol'][str(n)]:.2f}" for n in (5, 10, 20))
        tail = x.get('tail_1400_close_pct')
        comparison.append(f"|{code} {x['name']}|{x['close']:.2f}|{rs}|{x['distance_ma20_pct']:+.2f}%|{x['clv']:.3f}|{('N/A' if tail is None else f'{tail:+.2f}%')}|")
    body = f'''一、本次独立综合决定与时间
综合盘后组T={T}，实际完成/冻结{stamp}，计划介入D={D}，如买入最早2026-10-27卖出。本轮在10月24日周末补齐T23缺失的综合裁决，只使用T23及之前价格和当前已公开的公告。最终0只，空仓观察；不新造10月24日交易候选，也不将研究对照名单当作交易指令。决策唯一id={REPORT_ID}，模型combined_limitup_watch_v5沿用，未因本次结果调整规则或权重。没有买入、持仓、浮盈或可执行策略收益。

二、四份同T完整研究及真实回执
|模块|原完整报告ID|原实际完成/公开时间（北京时间）|
|---|---|---|
{dep_table}
四份正文hash与线上API逐一一致，且每份有同T completed回执；自动扫描、configuration_audit、execution_summary和eligible=false材料没有被用作前置。市场复盘、低位和龙虎榜补做研究实际完成于24日，绝没有倒填为23日按时完成；volume_price原完整报告实际完成于23日，本轮复用且没有漏做。quant_research已取消。

市场复盘支持：5573只有效股票、120广泛池、28深筛，覆盖机器人/机械、军工、软件、电子、医疗、传媒、家电等研究类别。23日4525涨/909跌，沪深约1.9563万亿元成交，较22日约1.4346万亿元明显放量，属于退潮后的强修复。反证：两只可见6板高标剧烈分歧，旧28池有18只日内最低相对前收不利≥5%；主板前20交易日完整高度与逐层分母不足，修复能否持续尚未验证。

量价支持：28/28逐股有冻结原始快照；力源信息、昊志机电的相对量与收盘位置较好。反证：普涨中大量样本同步放量，单一形态区分度降低；此前28只收盘中位+3.413%仍伴随深盘中不利。低位研究支持：39条/38股全路径复核，保留失败及失效样本。反证：正式30自然日模型成熟N=0，两个到期原始样本不满足原快照资格，不足以给新股票加胜率分。龙虎榜支持：98理由行/78股票，8只买卖席位勾稽；歌尔、埃斯顿、天娱的机构与股通方向同向。反证：集中度及价格位置不同，高位海洋王/大业的单日净卖不能被三日累计净买覆盖，席位名称不能证明账户身份、锁仓或连续流入。

三、量价研究与验证：完整28只复用，8只重点比较
下表全部价格为10月23日15:00收盘参考，不是介入价。相对量RVOL5/10/20=当日完整成交量/此前已完成交易日均量，与盘中量比不同；CLV=(收盘-最低)/(最高-最低)，仅描述收盘位置，最高=最低则N/A。均线使用本轮完整未复权日线且包含T，满20日才计算；原量价报告采用此前窗口的字段保留原定义，两者差异不当成报价错误。
|对照对象|T收盘|RVOL5/10/20|距MA20（含T）|CLV|14时后价格变化|
|---|---|---|---|---|---|
{chr(10).join(comparison)}
其余20只、全部28只的换手/振幅、20/60/120日位置、六个时点价格点和旧池逐股结果均在原完整报告及本轮引用附件可复核；六个时点不是完整分钟OHLC，不能推断杀跌→承接→突破的完整顺序。低位首次放量、突破/回踩、缩量上涨、高位爆量/长上影与放量下跌继续分组研究，未把未验证结构机械打分。

四、支持与否决的重新裁决（全部为研究对照）
1. 力源信息300184：在本次对照中，120日区间位置约14.15%、RVOL20=3.52、CLV约0.80和尾盘+1.59%较有吸引力。官方三季报前三季度收入104.773亿元（+61.68%）、归母4.804亿元（+208.16%）、扣非4.857亿元（+220.22%）是实质支持，并非缺少业绩催化。反证是经营净现金流-3.377亿元、应收款增加，且T收盘10.84仍在MA20约10.82附近、未越过T高点11.08及MA60约11.67的上方供给；公司将现金流变动解释为未到回款期、采购付款和税费薪酬增长，不直接认定财务恶化。23日放量修复尚未经历后续缩量承接，20%制度隔夜波动更大。本轮维持后续研究优先对象，未升级为本组条件推荐，也不因利润增长捏造涨停概率。
2. 昊志机电300503：RVOL20=3.18、CLV约0.91、14时后+2.47%，120日位置约20.55%，机器人板块同步提供支持。反证为T单日振幅大，62.30至63.23/MA60约64.85仍有供给；最新241亩二期项目合同具体投资额和进度取决于内部决策及实际资金，不是客户订单或业绩承诺。单日V形价格点不能证明持续建仓。与力源相比，独立业绩催化的当次核验弱一些，未胜出。
3. 歌尔股份002241：距MA20约4.86%，日榜机构/股通同向、容量较大，是普通主板对照。新核验的三季报前三季度归母约26.188亿元同比+1.21%，第三季度收入-7.80%、归母-1.51%、扣非-3.56%，年初至今经营现金流-26.378亿元；三季报未经审计。数据不构成破产或现金流必然继续恶化的判断，但未提供强业绩加速支持。RVOL20约1.65、涨停后买点需重建，当前没有充分证据胜过其余替代者。
4. 天奇股份002009：机器人方向、RVOL20约5.75有支持，但T回封顺序只有离散价格点，20日位置顶端且距MA20约+11.90%，本次没有把封板当普通可成交入场。埃斯顿002747：机构与股通同向但买1集中约48%，且尚有MA60约30.40压力。天娱数科002354：日榜机构与股通同向，但RVOL20仅约1.41，封板强度不等于足量换手后的延续；本轮公司公告检索返回0条也不等于不存在风险。三只均未满足本次较严格的隔夜质量判断。
5. 海洋王002724、大业股份603278：可见6板高度支持情绪观察，但不进入低位/首次分歧优选。海洋王10月24日公告称6日累计+77.41%、换手急增、相关题材业务规模有限，并计划27日披露三季报；大业公告称短期上涨过快，机器人腱绳产品仍为研发送样、未量产且没有实质收益。两者日榜分歧及高乖离构成明确否决，不能机械追逐最高板或用媒体题材当订单。

综合结论：修复支持继续研究，现有证据还不足以在本轮周末维护中升级出更高把握、可执行进出条件完整的新交易卡。优先核验力源的增长与回款、两只量价样本的后续承接；普通主板替代组也没有更完整的催化/量价组合。选择现金是本次完整比较后的决定，非四模块等待状态。

五、上一组与统计口径
上一已完成综合组T22为空仓，23日没有该组买入和策略盈亏。更早全志科技300458的21日最低28.56高于冻结回踩区间上界28.30，原结果为未触发/无成交；之后23日收盘30.08只是后续价格观察，不重新激活过期条件、不记成策略利润。原结果与时间不改写。
上一深筛池28/28的23日收盘观察均值+2.410%、中位+3.413%，高点观察均值+5.487%、低点观察均值-5.475%，18只曾低于前收-5%；是共享原样本一次验证，不重复计数。完整策略成交N=0，净收益、胜率、盈亏比及9:50/14:40窗口绩效N/A；20bp只为历史未校准占位，不拿它算假收益。5/10交易日完整深筛池档案覆盖不齐，重复率N/A；可得档案交集8/28约28.57%不是完整5/10日重复率。本次推荐0只，亦不存在为了降低重复率而换股。

六、复市研究重点与执行边界
26日先验证23日全部28只与旧低位样本到期节点，再冻结任何新样本；时间窗口为9:25、9:30、9:45、10:30、午盘、14:00后及收盘。重点看市场宽度修复能否延续、机器人核心是否继续交换后推进、6板高标是否出现亏钱扩散。力源/昊志为已有量价研究对象，不能把此段当成新的双标买入卡；具体竞价、回踩、突破与放弃条件若后续研究需另行事前冻结，不倒填。
继续沿用原量价H6/H7/H8影子假设，未新增交易规则：比较近均线高相对量组与高乖离封板组的后续不利波动，比较量不足反弹是否需要补量确认，以及收盘转正但日内不利深的样本的退出质量。规则只有经过滚动前推/样本外支持才考虑修订，记录日期和版本。
本次0候选，参考介入区间/仓位/个股止损与止盈订单均未激活，不伪造具体委托。若未来26日另有真实入场，最早27日才能卖出；26日失效也只能停止加仓并承担隔夜风险，27日跌停/停牌不能保证退出。APP只展示归档与验证，不内置大模型、自动权重训练或稳定获利能力。

七、独立打板衔接与归档
完整打板v2报告{ORIGINAL_LIMITUP}已在本轮之前归档并线上可读，planned_entry_date={D}、候选0。本轮复用该完整报告及回执，未生成第二份D日新候选；最新公司公告补证另见{LIMITUP_ID}，两组账本独立。配置审计{CONFIG_ID}只为合并快照，不属于四项前置。研究报告、原始池证据、真实回执及配置一起原子追加，发布后需CI/容器、准确SHA的Railway终态SUCCESS和公开API读回才能称APP同步。'''
    sources = [EVIDENCE, 'docs/research/volume-price-20261023-close-evidence.json',
               'docs/research/completion-20261023-evidence.json.gz',
               'https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml']
    sources.extend(x['source'] for x in official.values())
    combined = report_base(REPORT_ID, 'combined_pair', '综合双标｜10月23日四项齐备后空仓与10月26日复市预案',
        '复用5573只全A、120广泛池、28深筛与四项完整研究；新增官方公告补证后综合候选0只。',
        body, stamp, sources, 'full_trading_research')
    combined.update(run_id=RUN_ID, eligible_for_integrated_research=True,
        dependency_report_ids=[d['report_id'] for d in first['dependency_audit'].values()],
        strategy='combined_limitup_watch', research_rule_version='combined_limitup_watch_v5',
        group='close', cohort_label='综合盘后组', candidate_count=0, recommendation_ids=[],
        decision='cash_no_qualified_candidate', broad_pool_count=120, deep_pool_count=28,
        previous_pool_verified_count=28, full_scan_count=5573, new_market_sample_count=0,
        executed_trade_count=0, codes=codes, reused_limitup_report_id=ORIGINAL_LIMITUP)

    limit_body = f'''本轮实际公告复核{stamp}；研究T={T}，计划D={D}。本报告为原完整打板v2研究{ORIGINAL_LIMITUP}的周末公告补证，原完整报告、空仓结论、固定参考股及规则均保留。原报告已覆盖最近三个交易日情绪、6板高标、次高与二板梯队、至少三只替代者、空间/晋级缺项、v1历史验证和T+1退出边界。本轮不重新计样本、不将补证伪装为新的一股。

一、最近三日环境继续沿用已归档口径
21/22/23日财联社不含ST/退市涨停50/33/82，炸板19/23/12，封板率72%/59%/87%；原报告不同来源跌停口径不能混加。23日普通非ST主板代理跌停11、22日同口径58，只是阈值代理不是官方精确跌停数。市场为强修复待持续验证。可见主板最高海洋王002724、大业股份603278为6板，上海九百600838为3板，普通主板二板8只；华阳智能301502为20%另列。此前20交易日完整高度、完整主板首板逐股分母和情绪周期起点仍未知，不能声称空间已确认打开。媒体跨制度9/24等晋级率不当作普通主板首板进二板胜率。

二、官方新证据对原备选的影响
海洋王24日异动公告确认6个交易日涨停、累计+77.41%及激烈换手，提示公司相关概念业务规模有限和非理性交易风险，并列27日三季报计划。大业24日公告提示短期涨幅与分歧，机器人腱绳仍在研发送样、未量产和无实质收益。两者仍仅是情绪参考高标，无法通过高位加速/爆量分歧否决。
歌尔股份002241虽机构/股通同向，最新季度营收、扣非同比下降且现金流净流出，未补成强加速证据；天奇股份002009虽相对量高，完整首开/回封序列与队列成交证据仍不足；埃斯顿002747买方集中度偏高；天娱数科002354相对量较弱。原比较结论维持。力源信息300184、昊志机电300503只是20%制度量价对照，不能塞入普通10%主板打板策略；力源增长、回款及昊志合同落实继续另外研究。

三、D日计划和退出
维持空仓/0候选，不新增D日涨停委托价，不把前收×1.1当经核验的实时涨停价；周末D日证券状态、竞价和盘口均未出现。保留原26日9:25及9:35—10:30观察窗口、海洋王/大业高标及天奇/埃斯顿同伴，不事后换参考。高标亏钱扩散、一字排队、首次开板后承接不明、放量不进或无法核实盘口直接放弃。此次没有入选者，原泛化观察条件不等同可下单卡。
将来若26日另行事前冻结合格条件并能证明买入，最早27日实际交易日卖出；强/平/弱开均按原冻结退出，不选事后最高价。停牌、跌停或卖单未成交保留敞口。当前模拟验证，未转实盘。

四、历史样本和统计
龙溪股份600592的v1唯一原候选必要开盘条件未满足，已归档未入场不重新激活。v1候选N=1、验证入场N=0；v2仍0候选、0验证成交。首板/二板/回封、不同涨跌幅制度、情绪阶段和长假样本继续分组，策略净收益、胜率、盈亏比、封板成功率N/A。真实成本与滑点没有数据，不能用20bp占位计算假净收益。新公告不改变原条件，未来仅追加结果。'''
    limitup = report_base(LIMITUP_ID, 'limitup_single', '打板v2周末补证｜复用10月26日空仓预案与官方风险公告',
        '原完整D26打板报告复用；新核验官方公告支持继续空仓，未新增或重复候选。',
        limit_body, stamp, sources, 'weekend_evidence_addendum')
    limitup.update(run_id='limitup-single-20261023-scheduled-weekend-evidence-v2',
                   eligible_for_integrated_research=False, research_rule_version='limitup_single_v2',
                   candidate_count=0, recommendation_ids=[], decision='cash_no_qualified_candidate',
                   supplements_report_ids=[ORIGINAL_LIMITUP], reused_full_report_id=ORIGINAL_LIMITUP,
                   creates_new_decision=False, creates_new_recommendation=False, supersedes_original=False)

    evidence['actual_completed_at'] = stamp
    save(EVIDENCE, evidence)
    research['items'].extend([config_report, combined, limitup])
    runs['items'].extend([config_run,
        receipt(combined, RUN_ID, 'scheduled', STARTED, extra={'eligible_for_integrated_research': True}),
        receipt(limitup, limitup['run_id'], 'scheduled', STARTED,
                extra={'execution_scope': 'reuse_full_report_and_append_verified_evidence',
                       'reused_report_ids': [ORIGINAL_LIMITUP], 'eligible_for_integrated_research': False})])
    before_tasks = copy.deepcopy(tasks)
    index = {r['id']: r for r in tasks['items']}
    index['combined_pair'].update(title='综合双标＋每日打板',
        summary='同一外部编排分别完成四项前置后的综合决策和独立打板v2；两个栏目、样本与回执分开保留。',
        schedule=SCHEDULE, timezone='Pacific/Auckland',
        schedule_text='外部合并研究与复查；四项前置齐备才作综合裁决，打板v2独立归档；GitHub局部证据只作兜底审计',
        configuration_confirmed_at=cfg_stamp, coordinated_task_ids=['combined_pair', 'limitup_single'],
        also_executes_task_ids=['limitup_single'])
    index['limitup_single'].update(schedule='COMBINED_PAIR_COMPONENT', timezone='Pacific/Auckland',
        timing_mode='dependency_driven', executor_task_id='combined_pair', independent_schedule_enabled=False,
        schedule_text='随综合双标＋每日打板合并编排执行；本栏目与v1/v2样本、报告、回执独立保留',
        summary='独立打板v2研究模块随综合编排执行，最多一只或空仓；原单独外部打板调度已暂停，非第五项综合前置。',
        execution_mode='combined_pair_component_full_research_with_partial_fallback',
        configuration_confirmed_at=cfg_stamp)
    tasks['updated_at'] = cfg_stamp
    save('backend/data/research.json', research)
    save('backend/data/task_runs.json', runs)
    save('backend/data/tasks.json', tasks)
    safe = evidence['safe_schedule_snapshot'] | {'observed_at': cfg_stamp,
            'changed_local_task_ids': ['combined_pair', 'limitup_single'],
            'old_safe_registry_rows': [r for r in before_tasks['items'] if r['id'] in ('combined_pair', 'limitup_single')],
            'configuration_is_research_completion': False}
    save('docs/research/combined-orchestration-20261024-safe-snapshot.json', safe)
    for r in (combined, limitup):
        path = ROOT / 'docs/research' / (r['id'] + '.md')
        path.write_text('# ' + r['title'] + '\n\n' + r['body'] + '\n\n来源：\n\n' +
                        '\n'.join('- ' + x for x in r['sources']) + '\n', encoding='utf-8')
    save('docs/research/combined-pair-20261023-publication-manifest.json', {
        'research_date': T, 'planned_entry_date': D, 'started_at': STARTED, 'completed_at': stamp,
        'report_ids': [config_report['id'], combined['id'], limitup['id']],
        'dependency_report_ids': combined['dependency_report_ids'],
        'reused_limitup_report_id': ORIGINAL_LIMITUP, 'candidate_count': 0, 'limitup_candidate_count': 0,
        'new_recommendation_count': 0, 'new_volume_price_sample_count': 0,
        'configuration_only_receipt_trigger': 'manual', 'production_verified_at_preparation': False})
    print(json.dumps({'completed_at': stamp, 'reports': [CONFIG_ID, REPORT_ID, LIMITUP_ID],
                      'candidate_count': 0, 'limitup_candidates': 0, 'reused_prerequisite_count': 4,
                      'configuration_ids': ['combined_pair', 'limitup_single']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
