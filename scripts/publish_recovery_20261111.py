"""Append seven honest same-date reports and forward observations, never fills."""
from collections import Counter
from datetime import datetime, date, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from daily_snapshot import validate_snapshot
from learning_loop import is_session
from strategy_lab import summarize_snapshot
sys.path.insert(0, str(ROOT / 'scripts'))
from research_evidence_io import load_evidence

T, D, EXIT = '2026-11-11', '2026-11-12', '2026-11-13'
PREFIX = 'manual-recovery-20261111'
CN = ZoneInfo('Asia/Shanghai')
URL = 'https://github.com/kevinqdmagic-png/Robin-Stock-Assistant/blob/main/'


def read(p):
    return load_evidence(ROOT / p)


def write(p, value):
    (ROOT / p).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def table(head, rows):
    return '\n'.join(['|'+'|'.join(head)+'|', '|'+'|'.join(['---']*len(head))+'|'] +
                     ['|'+'|'.join(str(v).replace('|','/') for v in row)+'|' for row in rows])


def f(v, n=2):
    return '未知' if v is None else f'{v:.{n}f}'


def module(p, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    stamp = datetime.now(timezone.utc).astimezone(CN).isoformat(timespec='seconds')
    research, runs = read('backend/data/research.json'), read('backend/data/task_runs.json')
    assert not any(r['id'].startswith(PREFIX) for r in research['items'])
    snap = validate_snapshot(read('docs/research/recovery-20261111-sina-close.json'), T, 'sina_close_snapshot')
    em = validate_snapshot(read(f'backend/data/https_daily_full/{T}.json'), T, 'eastmoney_https_unofficial')
    current = {r['code'].split('.')[-1]:r for r in snap['rows']}
    independent = {r['code']:r for r in em['rows']}
    cross = [r['code'] for r in snap['rows'] if r['code'] in independent and
             max(abs(r[k]-independent[r['code']][k]) for k in ['open','high','low','close']) <= .011]
    h = read('docs/research/recovery-20261111-histories.json')
    ctx = read('docs/research/recovery-20261111-evidence.json')
    filings = read('docs/research/recovery-20261111-filings.json')
    learning = read('docs/research/recovery-20261111-learning-evidence.json')['snapshot']
    assert len(h['broad_pool']) == 120 and len(h['deep_pool']) == 28
    assert len(cross) == 5219 and len(ctx['seats']) == 66
    assert all(m['validation']['verified'] for m in h['five_minute'].values())
    assert '34.05%' in filings['300415-q3-full']['text']
    assert '76.30%' in filings['002156-q3-full']['text']
    helper = module('scripts/publish_recovery_20261105.py', 'manual_helper')
    minutes = {c:helper.minutes_summary(m) for c,m in h['five_minute'].items()}
    metrics = {r['code']:r for r in h['broad_pool']}
    breadth = Counter('上涨' if r['close'] > float(r['preclose']) else '下跌' if r['close'] < float(r['preclose']) else '平盘' for r in snap['rows'])
    sectors = ctx['sectors']['data']['data']['diff']
    sectors = list(sectors.values()) if isinstance(sectors,dict) else sectors
    started = min(h['started_at'], ctx['started_at'])
    base_sources = [URL+'docs/research/recovery-20261111-sina-close.json', URL+f'backend/data/https_daily_full/{T}.json',
                    URL+'docs/research/recovery-20261111-histories.json', URL+'docs/research/recovery-20261111-evidence.json']
    common = f'研究交易日：{T}｜发布时间：北京时间 {stamp[:16].replace("T"," ")}（UTC+8）\n\n'
    common += ('本轮为用户要求的真实手动补做，收盘参考统一为11月11日15:00；取数和冻结在实际盘后时间。'
               '沪深范围，排除北交所。并未重建或改写09:50/14:40原时点信号。发布、研究完整完成、正式买点、可成交收益分开。\n\n')
    reports = []
    def add(task, title, summary, body, status='partial', full=False, sources=None, **extra):
        rid = PREFIX+'-'+task+'-v1'
        report = {'id':rid,'task_id':task,'date':T,'published_at':stamp,
                  'track':task if task in ['volume_price','low_position','dragon_tiger'] else 'market_review',
                  'title':title,'summary':summary,'body':common+body,'sources':sources or base_sources,
                  'status':status,'analysis_completed':full,'eligible_for_integrated_research':False,
                  'report_type':'full_daily_research' if full else 'manual_recovery_research',
                  'provenance':'manual_same_day_after_close_not_original_intraday_signal', **extra}
        reports.append(report)
        run_id = PREFIX+'-'+task+'-v1'
        event = {'id':run_id+'-receipt','run_id':run_id,'task_id':task,'date':T,'trigger':'manual',
                 'started_at':started,'recorded_at':stamp,'status':status,'summary':summary,
                 'report_ids':[rid],'analysis_completed':full,'sources':report['sources']}
        if status != 'waiting': event['completed_at'] = stamp
        runs['items'].append(event)
        (ROOT/f'docs/research/{rid}.md').write_text('# '+title+'\n\n'+report['body']+'\n')

    scope = f'新浪与东方财富分别核验5219/5225只（99.8852%），逐股OHLC对照{len(cross)}/5219只差异≤0.011元。缺6只不填充。BaoStock本轮登录10002007失败，未放弃主源，实际使用独立免费备份。'
    market_table = table(['指标','当日值'],[['上证指数','3680.64 / +0.46%'],['深证成指','11389.74 / +1.32%'],['创业板指','2572.07 / +3.11%'],['本次沪深样本上涨/下跌/平盘',f"{breadth['上涨']}/{breadth['下跌']}/{breadth['平盘']}"],['样本成交额（万亿元）',f(sum(r['amount'] for r in snap['rows'])/1e12,4)]])
    sector_table = table(['板块','涨幅%','上涨/下跌家数'],[[r['f14'],r['f3'],str(r['f104'])+'/'+str(r['f105'])] for r in sectors[:12]])
    add('market_review','11月11日复盘补做｜双免费源5219只与成长修复',
        '完成5219只收盘、双源OHLC核对、指数及板块横比；完整涨停生态和逐时板块证据仍待补。',
        scope+'\n\n'+market_table+'\n\n'+sector_table+
        '\n\n指数来自腾讯同日收盘时间戳，行业榜来自东财当日板块快照，榜单仅返回前100/496项，不称全行业完整扫描。'
        '同花顺原研显示元件、通信设备、自动化设备领先，白酒和机场航运偏弱；东财文章报道85只涨停、25只触板未封、77.27%封板率，源口径保持独立，不与本次沪深股票数混算。'
        '本次涨停池接口虽HTTP200但rc=205且data=null，不能当作成功或据此确认连板完整梯队。\n\n'
        '判断：成长方向放量修复，适合验证低位承接与突破回踩；单日大涨不足以认定中期趋势反转。'
        '120只历史广池、28只深池、37只五分钟均留档；ST/高位放量回落对照保留。完整逐时行业/情绪与涨停梯队缺口继续保留。',
        sources=base_sources+['https://news.10jqka.com.cn/20261111/c681700951.shtml','https://finance.eastmoney.com/a/202611113928392529.html'])

    broad_table = table(['代码/名称','收盘/涨幅%','RV5/RV10/RV20','120日位置%','CLV','形态'],[
        [r['code']+' '+r['name'],f(r['close'])+'/'+f(r['pct']),'/'.join(f(r[k]) for k in ['rvol5','rvol10','rvol20']),f(r['position120']*100),f(r['clv']),';'.join(r['tags'])] for r in h['broad_pool']])
    deep_table = table(['代码','分钟校验','尾30分钟%','VWAP偏离%','午后低点'],[
        [r['code'],minutes[r['code']]['count'],f(minutes[r['code']]['last30_return_pct']),f(minutes[r['code']]['close_vs_vwap_pct']),f(minutes[r['code']]['afternoon_low'])] for r in h['deep_pool']])
    add('volume_price','11月11日量价补做｜120只历史与37只完整五分钟',
        '120/120日线核验，深池28只及9只温和结构共37只五分钟全部通过48根及OHLC量额校验。',
        scope+'\n\n从全范围单日量价扫描后冻结120只多结构广池，进一步冻结28只深池；额外9只温和正向结构单列，不能称5219只均查完150日历史。'
        'RV为当日成交量/前5、10、20个已完成日均量，不是盘中量比。120日位置是区间归一化位置，不是距最低点涨幅。\n\n'+broad_table+
        '\n\n深池完整分钟：\n\n'+deep_table+
        '\n\n通富微电RV20=1.25、RV5=0.87，支持温和修复而非新一轮巨量启动；三花RV20=1.77、午后低点36.11，需检验36.47—36.70压力。'
        '伊之密放量越20日高但公告核查发现单季归母下降34.05%，形态不能盖过盈利风险，降为对照；东方新能高量低CLV与华利集团放量下跌保留失败样本。'
        '五分钟能确认日内路径，不能确认逐笔身份、排队成交或60秒封单承接。未完成全部行业时点、证券状态和执行验证，故仍为partial。'
        '待验证H1：温和量价修复的T+1/T+2观察是否优于高量长上影；H2：突破后回踩是否减少追高；H3：公告负反馈是否解释部分假突破。')

    ledger = read('backend/data/low_position_samples.json')
    low_updates = []
    for sample in ledger['items']:
        row = current.get(sample['code'])
        anchor = sample.get('day0_close')
        if not row or not anchor: continue
        start = date.fromisoformat(sample['date'])
        days = [start+timedelta(days=i) for i in range(1,(date.fromisoformat(T)-start).days+1)]
        obs = {'as_of':T,'recorded_at':stamp,'calendar_day':(date.fromisoformat(T)-start).days,
               'trading_day':sum(is_session(d) is True for d in days),
               'open':row['open'],'high':row['high'],'low':row['low'],'close':row['close'],
               'change_from_day0_pct':(row['close']/anchor-1)*100,
               'status':'historical_close_observation_not_complete_intraday_path',
               'source':'docs/research/recovery-20261111-sina-close.json','price_basis':'unadjusted_daily_close',
               'original_snapshot_eligibility_unchanged':True,'executed_trade':False,'executable_net_return':None}
        if not any(x.get('as_of')==T for x in sample.get('observations',[])): sample.setdefault('observations',[]).append(obs)
        low_updates.append({'code':sample['code'],'name':sample['name'],**obs})
    ledger['updated_at'] = stamp
    write('backend/data/low_position_samples.json',ledger)
    low_table = table(['代码/名称','收盘','RV20','120日位置%','判定'],[[r['code']+' '+r['name'],r['close'],f(r['rvol20']),f(r['position120']*100),'破20日高' if r['breakout20'] else '修复/压力待确认'] for r in h['moderate_structures']])
    old_table = table(['原样本','收盘','相对原收盘%','自然日/交易日'],[[r['code']+' '+r['name'],r['close'],f(r['change_from_day0_pct']),str(r['calendar_day'])+'/'+str(r['trading_day'])] for r in low_updates])
    add('low_position','11月11日低位补做｜9只温和结构与旧样本追加',
        f'广池9只温和结构完成历史及分钟对照；给{len(low_updates)}条旧样本追加真实当日观察，不修改原资格。',
        scope+'\n\n新形态限定120只历史广池，当前9只温和结构是研究对象，不等于9只正式买点或全市场低位历史筛选完成。\n\n'+low_table+
        '\n\n原样本继续保留失败与亏损：\n\n'+old_table+
        '\n\n本次只追加T日真实日线观察，不借当天最高最低反推路径次序、实际成交、完整最大回撤或净收益；原未核实冻结仍不纳入有效策略收益。'
        '伊之密形态最好之一，但盈利回落及质押风险使其降级；通富修复中期MA60尚未回收；三花接近20日前高尚未确认突破。低位置不能单独证明建仓完成。')

    all_rows = ctx['lhb']['data']['result']['data']
    rows = [r for r in all_rows if r['SECURITY_CODE'] in current]
    seat_raw = {'seat_queries':{c:{side:{'rows':v.get('data',{}).get('result',{}).get('data',[]) or []} for side,v in parts.items()} for c,parts in ctx['seats'].items()}}
    seat_records = []
    for c in sorted({r['SECURITY_CODE'] for r in rows}):
        choices = [r for r in rows if r['SECURITY_CODE']==c]
        chosen = sorted(choices,key=lambda r:('连续' in r['EXPLANATION'],-r['BILLBOARD_NET_AMT']))[0]
        seat_records.append({'code':c,'name':chosen['SECURITY_NAME_ABBR'],**helper.seat_summary(seat_raw,chosen)})
    seat_table = table(['代码/名称','披露期','买/卖/净(亿)','机构净(亿)','买一占比%'],[[r['code']+' '+r['name'],r['interval'],'/'.join(f(r[k]/1e8) for k in ['listed_buy_yuan','listed_sell_yuan','listed_net_yuan']),f(r['institution_net_yuan']/1e8),f((r['top_buy_share'] or 0)*100)] for r in seat_records])
    add('dragon_tiger','11月11日龙虎榜补做｜66只完整买卖侧查询',
        f'取得沪深{len(rows)}条原因、{len(seat_records)}只股票全部买卖侧查询；交易所原文400/403，不能升级完整前置。',
        '东财公开披露副本实际查询66只×买卖两侧，共132次，日期均为11月11日。每只优先单日披露；连续多日榜单另标，不把多个上榜原因加总为额外资金。\n\n'+seat_table+
        '\n\n东山精密披露净买7.22亿元，但该值只覆盖公开上榜席位，不能称全市场净流入；沪电股份与光迅科技构成硬件强势对照。'
        '通富微电、三花智控未在本次同日榜单出现，不虚构机构席位为其背书。机构专用、股通与营业部标签不确认最终账户，也不证明次日锁仓或做T。'
        '上交所原接口HTTP400、深交所HTTP403，错误保留在原始证据。缺交易所原始完整对照和历史席位画像，因此partial。')

    lab = summarize_snapshot(learning)
    learn_table = table(['周期','证券基准日N','独立基准日','正价格比例%','均值%','中位%'],[[k,r['sample_count'],r['unique_anchor_dates'],r['positive_pct'],r['average_price_change_pct'],r['median_price_change_pct']] for k,r in lab['horizons'].items()])
    add('learning_review','11月11日学习复核｜新快照与收益/上涨比例分开',
        '23代码重新取同日截止历史，31条正式旧记录：22可观察、9回顾性不合格；样本仍不足，未调权。',
        '重新获取23个代码截至11月11日的未复权历史，实际追加forward-learning-2026-11-11；不是把11月10日时间改成今日。31条旧正式记录保留22条observed与9条ineligible_retrospective；低位4条独立保留，不混入正式组。\n\n'+learn_table+
        '\n\n按证券+实际基准日去重17个事件、8个独立基准日，仍低于36个事件/20个独立日的探索下限。T+2正价格比例52.94%但均值-1.633%，说明高上涨比例不等于正期望；T+5和T+10较弱，不把延长持有当解套规则。'
        '同证券与相邻日期相关，未验证成交、交易成本与滑点；真实胜率和净收益继续为空。'
        '明日新观察在实际冻结后前推，不预填11月12日收益；次日未触发和亏损也必须留档。早尾盘使用原生产档案，不事后用收盘赢家重建缺失信号。'
        '本轮学习分析完成，无自动训练、调权、下单或稳定盈利结论。',status='completed',full=True,
        sources=[URL+'docs/research/recovery-20261111-learning-evidence.json', URL+'backend/data/learning.json', URL+'docs/research/recovery-20261111-learning-inputs.json'])

    board = current['002384']
    limit_watch = {'task_id':'limitup_single','code':'002384','name':board['name'],'reference_price':board['close'],
                   'reference_as_of':T+'T15:00:00+08:00','actual_frozen_at':stamp,'planned_observation_date':D,
                   'candidate_status':'research_shadow_limitup_only','formal_buy_signal':False,'buy_order_allowed':False,
                   'hypothesis':'硬件强势和同日披露净买支持次日板后承接观察，不能据此预判可成交。',
                   'trigger_condition':'11月12日09:35—10:30观察首次分歧后回封，须另取得真实竞价、连续至少60秒承接与同期板块反馈。',
                   'abandon_condition':'一字排队、抢跑高开、板块转弱、无连续盘口或无可成交证据即放弃；不按旧收盘价追入。',
                   'risk':'前日已封板，次日高开和T+1退出风险；本轮无明日盘口，正式0只是未确认。',
                   'earliest_legal_exit_if_entered':EXIT}
    add('limitup_single','11月11日独立打板补做｜东山精密为观察对照',
        '独立打板观察东山精密92.06元；正式0只，因次日竞价/60秒承接与可成交证据尚未取得。',
        '## **东山精密（002384）**\n\n资格：打板观察；11月11日15:00收盘92.06元，非入场价。'
        '今日涨停与披露席位净买支持板后承接研究，不构成次日买入许可。\n\n'
        '11月12日观察首次分歧、板块持续性和回封；至少60秒连续承接、一字排队与实际成交条件均需当时采集。'
        '本轮涨停池接口rc=205，完整梯队及晋级率未核，不能据85只新闻口径独立裁决正式打板。正式0只源于未确认，不是市场无机会。'
        '如11月12日发生实际买入，最早11月13日可卖；不得按日内最高点填收益。',research_shadow_candidates=[limit_watch])

    pair=[]
    conditions={
        '002156':('45.20—45.30附近承接带、44.91日线MA20为结构参照；11月12日09:35—10:30或14:00—14:40观察承接后放量站稳46.15。',
                  '未入场前跌破44.90且不能回收、半导体同步走弱或较45.90高开超过3%（约47.28）则放弃追价。',
                  'Q3扣非净利+76.30%支持对照，但归母+199.54%含较多非经常性收益；RV5不足1，中期MA60约55.16仍在上方，不能当趋势反转。'),
        '002050':('36.10—36.20附近观察午后低点/VWAP承接；11月12日09:35—10:30或14:00—14:40放量站稳36.47—36.70压力带再评估。',
                  '未入场前失守36.10且不能回收、板块转弱或较36.35高开超过3%（约37.44）则放弃追价。',
                  '三季度归母同比-9.64%、扣非-5.09%，不是业绩爆发股；回购截至11月5日约2.23亿元不保证股价，20日前高尚未确认突破。')}
    for code in ['002156','002050']:
        r=metrics[code];tr,ab,risk=conditions[code]
        pair.append({'task_id':'combined_pair','code':code,'name':r['name'],'reference_price':r['close'],
                     'reference_as_of':T+'T15:00:00+08:00','actual_frozen_at':stamp,'reviewed_at':stamp,
                     'planned_observation_date':D,'candidate_status':'pending_integrated_review_not_final',
                     'formal_buy_signal':False,'buy_order_allowed':False,'hypothesis':'日线位置修复与完整五分钟承接共同前推验证，尚无统计优势。',
                     'trigger_condition':tr,'abandon_condition':ab,'risk':risk,'earliest_legal_exit_if_entered':EXIT})
    pair_body=''
    for c in pair:
        r=metrics[c['code']];m=minutes[c['code']]
        pair_body+=f"## **{c['name']}（{c['code']}）**\n\n资格：待综合观察；参考价{c['reference_price']:.2f}元，{T}15:00北京时间。涨幅{r['pct']:.2f}%，RV20={r['rvol20']:.2f}，120日位置{r['position120']*100:.2f}%；48根五分钟已核验，尾30分钟{m['last30_return_pct']:.3f}%。\n\n触发观察：{c['trigger_condition']}\n\n放弃：{c['abandon_condition']}\n\n风险：{c['risk']}\n\n"
    add('combined_pair','11月11日综合比较补做｜通富微电与三花智控待综合观察',
        '完成当日横比并冻结通富微电45.90、三花智控36.35两只待综合观察；完整前置未齐，最终研究双标仍待确认。',
        pair_body+'已先整理本轮市场、量价、低位、龙虎榜、学习与独立打板，再作比较；输入报告ID均为同前缀对应任务-v1。'
        '四项完整前置仍partial，不能将本轮两只改称最终研究双标。正式买点0只。\n\n'
        '对照与否决：伊之密虽然放量越20日高，三季报单季归母-34.05%、扣非-35.40%，且有一致行动人质押，故从形态初选降级；'
        '中电电机有计提减值公告未全量核清，信维通信有员工持股锁定期届满提示，均不靠K线升级。盛通更接近短期高区且临近6.19—6.23压力；'
        '梦洁精确代码公告未返回，缺失不作风险解除；如通/大亚缺乏本轮更强行业证据，未取代两只。'
        '通富的经营扣非增长与半导体修复背景较好，但不能忽略非经常性收益和MA60压制；三花相对量能更清楚但盈利回落，均只作条件观察。\n\n'
        '实际冻结为本次真实盘后时间；计划11月12日验证，若实际买入最早11月13日卖出。11月13日09:35—10:30依据真实开盘承接/冲高回落再评估退出，'
        '绝不预填成交、收益或假设当日止损可卖。今天原09:50/14:40如无当时证据则继续标缺，不能用本名单回填。'
        '后续欠项：原始交易所席位对照、完整时点行业和涨停生态、证券状态/公告广度、正式竞价及可成交验证。跨日保留，不能称彻底修复。',
        status='waiting',research_shadow_candidates=pair,
        sources=base_sources+[v['url'] for k,v in filings.items() if 'text'in v])
    research['items'].extend(reports)
    write('backend/data/research.json',research)
    write('backend/data/task_runs.json',runs)
    write('docs/research/recovery-20261111-new-reports.json',{'items':reports})
    write('docs/research/recovery-20261111-derived.json',{'date':T,'published_at':stamp,'crosschecked_ohlc':len(cross),
          'breadth':dict(breadth),'seat_records':seat_records,'minutes_summary':minutes,'old_low_observations':low_updates,
          'learning_summary':lab,'observation_pair':pair,'formal_candidates':[]})
    print(json.dumps({'reports':len(reports),'learning_completed':True,'final_pair_completed':False,'pair':pair,'stamp':stamp},ensure_ascii=False))


if __name__=='__main__':
    main()
