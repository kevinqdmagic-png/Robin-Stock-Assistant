#!/usr/bin/env python3
"""Append full Oct19 studies, frozen decisions and real receipts together.

This prepares repository files only. CI and production delivery are verified
separately; no quote, condition or price excursion is a simulated execution.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from collect_20261019_combined import stats, T, PREV
from publish_market_review_20261019 import SECTOR
from research_evidence_io import load_evidence

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'backend/data'
EFILE='docs/research/combined-pair-2026-10-19-evidence.json'
START='2026-10-19T09:17:20+00:00'
IDS={k:k.replace('_','-')+'-20261019-close-v1' for k in ('volume_price','low_position','dragon_tiger','combined_pair')}
MARKET='market-review-20261019-close-v1'
SECTOR.update({'300432':'汽车零部件/锂电材料','000032':'数字基础设施/工程服务',
               '688084':'军工电子/特种装备','300556':'数字视觉'})


def load(name):return json.loads((DATA/name).read_text())
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def f(x,d=2):return 'N/A' if x is None else f'{x:.{d}f}'
def sg(x,d=2):return 'N/A' if x is None else f'{x:+.{d}f}'
def tab(head,rows):
    return '\n'.join(['|'+'|'.join(head)+'|','|'+'|'.join('---' for _ in head)+'|']+
                     ['|'+'|'.join(str(v).replace('|','/') for v in r)+'|' for r in rows])
def source_list(e):
    return list(dict.fromkeys([EFILE]+e['sources']+[r['source'] for r in e.get('issuer_primary_pdf_checks',[]) if 'error' not in r]))
def base_report(task,title,summary,body,e,stamp,**extra):
    return {'id':IDS[task],'date':T,'market_date':T,'task_id':task,
            'track':'market_review' if task=='combined_pair' else task,
            'title':title,'summary':summary,'body':body,'sources':source_list(e),
            'report_type':'full_daily_research','eligible_for_integrated_research':True,
            'published_at':stamp,'recorded_at':stamp,'data_cutoff_at':stamp,
            'market_data_cutoff_at':'2026-10-19T16:15:00+08:00',
            'run_id':task.replace('_','-')+'-20261019-scheduled-close-v1',
            'evidence_file':EFILE,'provenance':'contemporaneous_close_research',**extra}


def volume_report(e,stamp):
    v=e['volume_price']; ss=v['deep_samples']; ps=v['previous_statistics']
    rows=[[s['code']+' '+s['name'],SECTOR.get(s['code'],'独立行业待细分'),s['board_limit_regime'],
           f(s['close'])+'/'+sg(s['daily_change_pct'])+'%',f(s['turnover_pct']),
           '/'.join(f(s['rvol'][str(n)]) for n in (5,10,20)),
           '/'.join(f(s['range_position_pct'][str(n)],1) for n in (20,60,120)),f(s['clv'],3),
           sg(s['distance_ma20_pct']),sg(s['tail_return_1400_to_1500_pct']),f(s['tail_volume_share_pct']),s['structure']] for s in ss]
    snapshot=tab(['代码/名称','板块','制度','收盘/涨跌','换手%','RVOL5/10/20','20/60/120日位置%','CLV','距MA20%','14点后%','尾盘量占%','结构'],rows)
    val=tab(['代码','开盘%','最高观察%','最低观察%','收盘%','分钟检查点'],
            [[r['code'],sg(r.get('open_return_pct')),sg(r.get('high_observation_pct')),sg(r.get('low_observation_pct')),sg(r.get('close_return_pct')),len(r.get('minute_checkpoints',{}))] for r in v['previous_validations']])
    groups=tab(['T-1冻结结构','样本','收涨数','均值/中位收盘%','日低均值%'],
               [[k,s['verified'],s['positive_close_count'],sg(s['mean_close_return_pct'])+'/'+sg(s['median_close_return_pct']),sg(s['mean_low_observation_pct'])] for k,s in v['previous_by_frozen_structure'].items()])
    recovered=e.get('qfq_retry_audit',{}).get('recovered',[])
    body=f'''一、完整范围、先验证后冻结

T=2026-10-19，实际完成/冻结{stamp}。复用同T完整市场复盘{MARKET}的5568只有效全A入口、120只广泛池；本轮独立重取原价/前复权日线、五日分钟价格点、重算相对量、MA和位置，实际广泛池可复算{v['broad_verified']}/120，完整28/28深筛。原始网络失败、随后重试恢复{len(recovered)}只及仍缺历史者全部留档，不把不足120只称全覆盖。候选覆盖传媒、物流、军工、汽车、机器人、医药、PCB、光伏、化工等至少11方向；不是从用户持仓出发。先完成10月16日全部28只前推，再追加本日28只冻结快照；共享原样本通过cohort关联，不重复计成两个任务的独立有效交易。

版本volume_price_close_v4沿用10月16日冻结定义。RVOL5/10/20为T成交量/此前5、10、20个已完成交易日均量，分母不含T；当日量除前一日量另列，不能冒充量比。盘中同一时点量比和T-1逐股换手率部分缺失，分别留空；换手变化仅对与前池重合的6只计算。MA5/10/20/60含T收盘；位置用前复权区间，参考和观察收益用原价，绝不拼接复权价格计算收益。市场复盘部分MA距离按前一完成日窗口，本模块统一含T，因此广东宏大为+8.744%而不是复盘约+9%，并非回改旧报。

CLV=(收盘-最低)/(最高-最低)，高低相同为N/A。全部28只原价OHLC与Sina冻结快照差为0；换手因流通股本口径可能不同（广东宏大Sina5.30%、腾讯约5.10%），不强行称完全一致。10%/20%制度分别标签，20%股票涨约10%不是涨停；按昨收舍入的上限仅是计算参考，D日仍须官方证券状态/除权及真实涨停价。

二、全部28只量价研究与验证快照

{snapshot}

每只保留开高低收、昨收、成交量额、换手、三档RVOL、MA5/10/20/60、20/60/120位置、前5/20高点、振幅、信号冻结时间和来源。分钟检查点覆盖9:30、9:45、10:30、午盘、14:00、14:40、15:00；9:25未取得。五日接口还带15:30等盘后点，分析严格取不晚于15:00的正常交易点；价格点+累计量额不是分钟OHLC/逐笔，不能把点间变化认作真实成交或推断高低先后。

三、五个展示样本，及六类结构的反证

1. 广东宏大002683：收30.11，+7.92%，RVOL5/10/20=3.081/4.110/4.938，120日位置31.8%，CLV0.940，已越前20日高29.70，属于低中位放量推进。14点后价格从29.85至30.11，约+0.87%；不是始终封板。支持跟踪突破后的承接，但30.25近压力、MA5仍低于MA20/60、次日追价后的风险收益不佳，反对直接升级综合买入。

2. 宇环数控002903：收24.96，+8.85%，RVOL20=2.312、120日位置14.1%、CLV0.914；14点后24.45→24.96，约+2.09%。然而仍低于含T的MA20约8.66%，换手19.13%、振幅13.17%；是低位反转待确认，不是已经完成趋势反转。无同日上榜记录不能推断无机构，但也没有席位证据加分。

3. 天津普林002134：RVOL20=2.501、CLV0.947但振幅19.99%、换手22.02%，14点后回落；榜机构专用通道净买与价格尾盘走弱并存。量大且靠近高收不代表分时真正“分歧转一致”，需要顺序/缩量回踩和再推进，不能只看净买。

4. 冰山冷热000530：RVOL20=7.55、120日位置85.4%、距MA20+39.0%、换手44.65%，高8.37收7.80、CLV0.581；高位爆量上影/涨不动风险。慈文传媒002343距MA20+57.6%、换手46.52%；新华传媒600825距MA20+88.6%、RVOL20=20.17，公告风险仍在。即使收红或有多路买方也不能抹掉兑现风险。

5. 负向/缩量对照来自上一冻结全池，不择优删除：莎普爱思603168当日-6.73%、量为前一日1.85倍、RVOL20=5.79；尖峰集团600668跌8.30%、量1.05倍、RVOL20约8.00，提示成交放大后价格未推进。吉大正元003029涨10.01%而量仅前日0.195倍、RVOL20=0.715；京城股份600860涨9.99%而量仅前日0.337倍。缩量封板不证明次日可买或低风险，作为原cohort诊断，不另算新增推荐。

低位首次放量、放量突破、放量分歧承接有当天研究样本；严格的“突破后缩量回踩再突破”尚无同时满足事前条件和可验证成交的新激活样本，不能把普通K线标签当确认。放量下跌、高位长上影、缩量上涨均保留反例。研究核心是交换后价格是否推进与后续承接，而非给资金身份贴标签。

四、上一完整28/28前推

{val}

9/28收涨；开盘均值{sg(ps['mean_open_return_pct'])}%/中位{sg(ps['median_open_return_pct'])}%；收盘均值{sg(ps['mean_close_return_pct'])}%/中位{sg(ps['median_close_return_pct'])}%；日高均值{sg(ps['mean_high_observation_pct'])}%、日低均值{sg(ps['mean_low_observation_pct'])}%。这是T-1收盘基准的价格观察，非入场后MFE/MAE、真实回撤或策略胜率。同期上证+0.39%，同基期均值相对差约-2.33个百分点，也不是净超额收益。

{groups}

分组按T-1冻结结构，不能用结果反过来改标签。v4首批有效下一交易日价格验证28只，区间10月16→19日；新28只尚未到验证日，不计成熟分母。v1/v2/v3、长假与本组分别留档。策略激活/可验证两侧成交N=0，净胜率、平均/中位净收益、盈亏比、可执行MFE/MAE与退出质量N/A；20bp往返成本只是未校准占位，不从观察收益机械扣成策略净收益。9:50/14:40没有同口径两侧成交与分钟条件原证据，本轮不能比较哪个组更赚钱。

五、对买点、退出与下一假设的具体影响

今天宽度2274涨/3129跌、成长指数弱，前池负收益及尾部风险未被修复。只凭低位、放量或龙虎榜净买不应升级；综合组选择空仓，不新发两只。未来T+1=10月20日若有另一次事前冻结并真实买入，最早T+2=21日才可卖；买入当天跌破失效不能当天止损，跌停/停牌也不保证21日退出。

沿用H3影子假设：低中位、CLV高且尾盘回收的突破，只有次日普通缩量回踩后重新推进并伴市场宽度改善，才可能优于高乖离爆量组。当前只是待证伪，不调整权重。下一步①比较广东宏大和宇环后续承接是否真正持续；②比较天津普林机构通道净买却尾盘偏弱与广东宏大未上榜的结果；③保留高位风险和缩量封板对照，滚动前推，不回看优化今天入池规则。无稳定规律或涨停概率承诺。'''
    return base_report('volume_price','量价完整研究｜10月19日全池验证、分歧承接与风险反例',
                       f"独立复算广泛池{v['broad_verified']}/120、深筛28/28，上一28/28收盘均值-1.943%、中位-1.743%；v4策略成交N=0，不以净买或放量机械选股。",body,e,stamp,
                       research_rule_version='volume_price_close_v4',broad_pool_count=120,broad_pool_verified_count=v['broad_verified'],
                       deep_pool_count=28,previous_pool_verified_count=28,frozen_sample_codes=[s['code'] for s in ss],
                       sample_cohort_id='volume-price-20261019-close-v1-cohort',codes=[s['code'] for s in ss],
                       executable_sample_count=0,facts_hypotheses_separated=True)


def low_report(e,stamp):
    l=e['low_position']; vals=l['existing_validations']; new=l['new_candidates']
    rows=[[r['code']+' '+r['name'],f(r['reference_close']),sg(r['close_return_pct']),sg(r['path_mfe_pct']),sg(r['path_mae_pct']),
           str(r['elapsed_natural_days'])+'/'+str(r['elapsed_trading_sessions']),
           '是' if r['observed_close_below_original_invalid'] else '否',r.get('first_verified_close_below_original_invalid') or '未见'] for r in vals]
    vr=tab(['代码/名称','原收盘参考','当前观察%','信号后MFE%','信号后MAE%','自然日/交易日','当前收破原位','首次核验收破'],rows)
    added=[]
    for s in new:
        added.append(f"{s['code']} {s['name']}（{SECTOR.get(s['code'],'行业待细分')}）：收{s['close']:.2f}、涨{s['daily_change_pct']:+.2f}%，成交{s['amount_cny']/1e8:.2f}亿元、换手{s['turnover_pct']:.2f}%；RVOL5/10/20="+
                     '/'.join(f(s['rvol'][str(n)],3) for n in (5,10,20))+'，20/60/120日位置='+
                     '/'.join(f(s['range_position_pct'][str(n)],1) for n in (20,60,120))+'%，MA5/10/20/60='+
                     '/'.join(f(s['ma'][str(n)],3) for n in (5,10,20,60))+f"，CLV{s['clv']:.3f}，尾盘{sg(s['tail_return_1400_to_1500_pct'])}%。初始失效位{s['low']:.2f}（未来收盘跌破信号日低点，原位不后移）。")
    broken=sum(r['observed_close_below_original_invalid'] for r in vals)
    olddoc=load('low_position_samples.json')
    counts=Counter(s.get('primary_model',s.get('model','未标主模型')) for s in olddoc['items'])
    body=f'''A. 新增低位启动研究样本，非短线买入指令

T=2026-10-19，实际完成{stamp}。复用全A5568入口及120广泛池，独立可复算{e['volume_price']['broad_verified']}只历史、28只完整深筛；本模块从广泛池按原low_position_30d_v1继续筛，不把综合组或用户自选直接放入。原门槛保持：非旧代码、120日位置≤55%、RVOL20在2—6、CLV≥0.72、涨1.5%—8%、距含T的MA20为0—15%；排除已连续高位加速、纯情绪接力。不凑数量，实际新增{len(new)}只，均为待验证的低中位放量/平台确认，不断言主力建仓。

'''+ '\n\n'.join(added)+f'''

这{len(new)}只的相对低位口径是120日区间，并不等于20日低位。广东宏大/海安20日位置均超过96%，更接近短周期突破；富临精工、深桑达、晶品特装还未完成全部中期均线多头排列。300/688制度最大涨跌幅和波动风险另列，不把+6%—7%当涨停。新增代码均只作30天研究；综合组本轮没有入选标的。

公告事实与风险分别留档：广东宏大10月9日回购进展不等于新增订单；富临精工9月29日子公司增资引入员工平台为关联交易；深桑达9月股东会/关联交易制度不能当新算力订单；晶品特装董秘/换届公告不是业务催化；海安10月15日同时披露回购结果和实控人股份质押，不能只谈回购；丝路视觉10月16日子公司担保及此前诉讼/可转债线索，不能省略风险。检索精确代码，全文摘要和哈希在证据中；无当日新增强催化不说“没有风险”。

B. 全部既有26只继续跟踪，成功/失败均保留

{vr}

26/26原价日线验证，参考收盘与当前提供者逐项对照；当前收盘破原失效位{broken}只。蓝色光标300058曾在此前研究触及/收破原失效，今天暂回原位之上不删除失败过程、不自动恢复为成功；吉林化纤000420仍是原有样本，不是新推荐。佛塑科技000973今天进一步低于原30天失效位，恩捷股份002812沿用原长期位45.05，不能与短线失效46.35混用。丰倍生物603334相对入选收盘约+0.81%、龙建股份600853约-1.39%，短期正负都不替代30天结论。

C. 节点、路径与到期口径

当前最早样本仅26自然日，30自然日到期0只。按1/3/5/10/15/20/30自然日节点，休市用不晚于目标日最近交易日，并单列5/10/20交易日；真实迟到录入时间与观察日分开。所有已到节点及完整日线路径追加，不删停牌、未触发、无法成交或快照不完整记录。

本轮追加low_price_observation_v2_20261019计算说明：价格路径MFE/MAE从冻结收盘之后的交易日开始，排除信号日收盘前的高低价；旧版本曾包含信号当日日内范围的记录原样保留，并在本次证据另存legacy对照，不反写历史。初始规则和失效位不变，纠正时间边界不被宣传为收益改善。即便这样，价格极值也不是入场后可执行收益或完整路径最大回撤，后者缺真实进出数量/时序仍N/A。

D. 模型统计与下一假设

原26、新增{len(new)}，原主模型计数：{dict(counts)}。新样本统一“低中位放量推进/平台确认”，进一步记录板块、位置和制度标签。30天有效完成数0，30天均值/中位、胜率、盈亏比、10%/20%达标率与可执行最大回撤N/A；不将26次日线观察当26笔交易。无已证实中长期机构身份或资金持续性，公开换手/榜单不是持有人证明。

待验证：长期相对低位但20日已高的突破，是否较长期低位且MA60尚未收回者更能保持第二次放量后的价格推进。广东宏大与海安作前一类，富临精工/深桑达/晶品特装作后一类，丝路视觉观察高换手/担保风险。分别记录后续失效、二次放量、行业变化、自然日/交易日节点，不后改今天标准。T盘后若以后有T+1真实买入最早T+2可卖；本台账仅价格研究，不假设今天或明日成交，不保证收益。'''
    return base_report('low_position','低位启动30天｜10月19日26只全跟踪与新增低中位样本',
                       f'完整验证26/26，当前{broken}只收破原失效；新增{len(new)}只独立30天研究样本，30自然日成熟0，价格路径剔除信号日收盘前极值。',body,e,stamp,
                       research_rule_version='low_position_30d_v1',existing_sample_count=26,new_sample_count=len(new),
                       mature_30d_count=0,codes=[r['code'] for r in vals+new],observation_calculation_version='low_price_observation_v2_20261019')


def dragon_report(e,stamp):
    d=e['dragon_tiger']; ss=d['selected_observations']; ps=d['previous_statistics']
    money=tab(['代码/名称','精确区间/原因','买/卖/净亿元','买一/买前五%','卖一/卖前五%','金额基准'],
              [[s['code']+' '+s['name'],s['selected_period_reason'],
                '/'.join(sg(s[k]/1e8) for k in ('buy_cny','sell_cny','net_cny')),
                f(s['buy_concentration_top1_pct']),f(s['sell_concentration_top1_pct']),s['seat_reconciliation']['aggregate_basis']] for s in ss])
    detail=[]
    for s in ss:
        buys='；'.join(r['OPERATEDEPT_NAME']+'买'+f(float(r.get('BUY') or 0)/1e4)+'万元' for r in s['buy_seats_em'])
        sells='；'.join(r['OPERATEDEPT_NAME']+'卖'+f(float(r.get('SELL') or 0)/1e4)+'万元' for r in s['sell_seats_em'])
        detail.append(s['code']+' '+s['name']+'：\n买前五：'+buys+'。\n卖前五：'+sells+'。')
    validation=tab(['代码','开盘观察%','日高观察%','日低观察%','收盘观察%'],
                   [[r['code'],sg(r.get('open_return_pct')),sg(r.get('high_observation_pct')),sg(r.get('low_observation_pct')),sg(r.get('close_return_pct'))] for r in d['previous_validations']])
    body=f'''一、范围、时间与环境

T=2026-10-19，实际完整分析完成{stamp}。东方财富同日80条上榜原因、67个去重代码，包含可转债/北交所等不同制度；沪深00/30/60/68开头A股59个，非同一分母不混算。同花顺同日摘要72行交叉核对，因区间/重复原因/制度不同，不把差额当漏掉的必涨股。全80原始行、日期、TRADE_ID、原因、金额与逐股原价日线留存；没有把榜单汇总净买当全市场资金净流入。

主要覆盖首板/封板（万丰奥威、慈文传媒）、大振幅未封（天津普林）、高位换手分歧（冰山冷热）、历史空间高位与重组风险（新华传媒）。全市场宽度2274涨/3129跌，沪深缩量、创业板/科创50弱；本地非ST普通主板40封/76触/36未封/25跌停。外部聚合46封、21炸、最高3板为暂定且口径不同；原逐层完整名单接口403，不能把暂定最高或总体晋级率写成全市场确定高度/全层1进2。新华此前11板为已发生历史参照，不等于今天仍是可交易连续11板。主线、空间突破与分层分母缺项保留，对接力形成反对而非虚构数字。

二、5只独立龙虎榜观察/风险样本

{money}

每只以股票+交易日+TRADE_ID+单日/三日区间精确绑定买卖席位，本轮5/5金额勾稽成功。深市按买卖前五披露行并集去重，沪市按每侧前五；同名“机构专用”可能是不同账户，不能按名字简单合并。慈文同日3个单日上榜原因不计3只，也有单独三日累计榜，本表取单日，不与三日相加。买一集中度分母为该侧前五，不拿并集作同一分母。明细如下：

'''+ '\n\n'.join(detail)+f'''

天津普林：收23.87、涨8.95%、换手22.02%、振幅19.99%，120日位置37.6%、RVOL20=2.50。多个机构专用买方通道与净买约1.045亿元共存，但尾盘回落；只研究20日正常开盘后不破23.00、缩量承接23.30—23.60再重站24.10、PCB至少两只非一字同向的顺序，不能用日高当回封成交。高开24.60以上、破22.80、开板后无承接或盘口缺失放弃。本轮只是观察，不进综合推荐。

冰山冷热：收7.80、日高8.37、换手44.65%、CLV0.581、距MA20+39.0%，高位爆量滞涨。机构专用既买又卖，净买0.403亿元不能证明锁仓。保留高位风险对照；20日若不能守7.62并在普通成交下重站8.05，或高开追涨、破7.32、反复开板/冷链同伴走弱均不观察；不跟标签买板。

慈文传媒：收10.26涨停、换手46.52%、120日高位、距MA20+57.6%，多路通道净买约2.158亿元且有机构专用两侧披露。仅在20日非一字、9.60—9.85缩量守住后再站10.15、传媒非一字同伴同步且高标不跌停时研究；高开10.60以上、破9.33、撤单/爆量价不进或缺盘口放弃。其高换手和异常波动/担保公告使其保留风险样本，不入综合。

新华传媒：收15.58、换手25.61%、RVOL20=20.17、120日位置98.3%，榜净卖约4525万元。10月19日新披露资产购买进展及交易风险提示，不能把重组等同已完成或确定增厚；仅风险对照。证券状态/公告不清直接放弃；即使15.00暂获承接、再站15.78，也不能自动升级，需重新事前研究，严禁追历史高度。

万丰奥威：首板/低空情绪参照，收10.90、换手4.82%、120日位置34.5%、RVOL20=3.72；封板且14点后成交量占比很低，不能证明明日可买。只有20日普通连续成交、10.45—10.65回踩守住后再站10.85，且中信海直000099/其他低空核心不弱、真实上限和除权核验才研究；一字排队、开盘高于11.20、破10.20或量大不进放弃。09:25/盘口/成交缺任一不认定买入。

以上全部是独立龙虎榜研究条件，不是实际委托或最终两只。若20日真实买入最早21日可卖；买入日炸板无法当日止损，21日跌停/停牌仍可能无法成交，价格阈值不是保证退出价。

三、上一完整5/5验证，不择优保留

{validation}

上一组5只只有冰山收涨；开盘均值{sg(ps['mean_open_return_pct'])}%/中位{sg(ps['median_open_return_pct'])}%；收盘均值{sg(ps['mean_close_return_pct'])}%/中位{sg(ps['median_close_return_pct'])}%；日高均值{sg(ps['mean_high_observation_pct'])}%、日低均值{sg(ps['mean_low_observation_pct'])}%。中鼎000887开17.12已低于冻结17.40下界；金健米业600127收跌9.99%，不能因前日机构/股通通道买入忽略；尖峰600668跌8.30%，三日榜净买不保证单日溢价；天马603668复权/公司行动前提仍需核验。前池全部保留价格检查点，缺竞价和真实两侧成交，策略N=0，不能报20%“交易胜率”。

四、席位画像、分组与可证伪假设

当前按单日/三日、位置、板块、情绪、封板/炸板、买一集中度和机构通道同向/背离分层；累计主要是10月15→16五只、16→19五只，共10个带次日价格观察的股票-信号日，不把10只当已验证成交。每层样本太少，平均/中位净收益、盈亏比、策略最大不利波动/退出质量全部N/A。国泰海通上海分公司、国信浙江互联网等通道在多只不同方向出现，仅记录披露买卖金额和场景；缺账户历史与完整分钟时不能杜撰常见持有天数、真实游资本人、做T/对倒/锁仓或量化身份。

DT3继续前推，不改旧条件：低中位、适度相对量、价格推进且尾盘承接应与席位通道信息共同验证；新增天津普林“多机构通道净买但尾盘回吐”、冰山“净买但高位滞涨”为反例，万丰“位置适中但普通买不到”为成交性反例。综合组对未上榜广东宏大/宇环保持中性，不赋虚构席位加分；本日完整研究对追接力总体形成反对，不保证任何次日收益。'''
    return base_report('dragon_tiger','龙虎榜完整研究｜10月19日80条原榜、席位勾稽及5只独立观察',
                       '80条原因/67代码（沪深A股59），5只席位精确区间金额勾稽；上一5/5收盘均值-4.290%，1只收涨，交易胜率仍N/A。',body,e,stamp,
                       research_rule_version='dragon_tiger_close_v2',raw_reason_count=80,unique_security_count=67,
                       mainland_a_share_count=59,previous_pool_verified_count=5,
                       observation_samples=ss,codes=[s['code'] for s in ss],executable_sample_count=0)


def combined_report(e,stamp):
    rows=[]
    for s in e['combined_horizon_validation']:
        rows.append([s['code']+' '+s['name'],s['reference_date'],f(s['reference_price']),f(s['ohlc']['close']),sg(s['price_return_to_T_pct']),
                     '、'.join(str(n['trading_horizon'])+'日:'+sg(n['close_return_pct'])+'%' for n in s['horizons']),
                     '未触发：开盘不合格' if s['code']=='000887' else '沿用旧触发结论/只追加价格'])
    follow=tab(['代码/名称','原T','原参考','19日收','截至19日观察%','已到交易日节点观察','触发/成交边界'],rows)
    body=f'''本次决定：综合盘后组空仓观察，最终入选0只。不发布第二只、不临时用低位台账或龙虎榜观察名单填位。决定id={IDS['combined_pair']}，T=2026-10-19，冻结/完成{stamp}，T+1计划日10月20日、T+2最早合法退出日21日；没有本次买入，也没有将条件扫描记成成交。规则combined_limitup_watch_v5沿用，未因今天结果优化阈值、权重或杜撰涨停概率。

一、四份同T完整研究和真实回执

市场复盘{MARKET}已于10月19日16:50完成，本轮实际线上读回并复用；其余三模块本轮实际补做，完整报告为{IDS['volume_price']}、{IDS['low_position']}、{IDS['dragon_tiger']}，各有独立task_id/track、run_id及真实完成回执，与本报告一起原子追加。不是自动扫描、配置审计、eligible=false或旧日报填充。quant_research已取消，不再研究或追踪。低位和龙虎榜分别留档，联合只是编排。

|模块|支持什么|反对/限制|对最终裁决|
|---|---|---|---|
|市场复盘|军工/机器人/通信局部强，广东宏大与宇环具日内推进|2274涨/3129跌；上证+0.39%但创业板-0.94%、科创50-2.17%，本地普通主板跌停25；高度/晋级聚合暂定|不将权重护盘当全面修复，隔夜风险优先|
|量价|广东宏大RVOL20=4.94、CLV0.940、120日位置31.8%、尾盘回收；宇环低位回收|前28只收盘均值-1.943%，日低均值-5.373%；宇环高换手且未收MA20；高乖离风险组多|只放量或日高贴近不能过关|
|低位30天|实际新增独立低中位研究样本，包含广东宏大；长期相对位置可比|30自然日成熟0；短周期位置已高，新增不是短线买入；既有失效样本持续保留|低位身份不是次日涨停证据|
|龙虎榜|天津普林等通道买方金额可核验，万丰低空首板可作情绪参照|前5只只有1只收涨，收盘均值-4.290%；高位净买/放量滞涨共存；广东宏大/宇环未上榜中性|不机械跟榜净买，不给未上榜股虚构资金身份|

二、独立全A重裁决和替代比较

复用可追溯5568全A扫描入口、120只广泛池，本轮重算其中{e['volume_price']['broad_verified']}只历史、完整28只深筛，并由广泛池独立扩出低位比较，不机械复制市场组两只。来源至少11板块；网络失败与尚不足历史标明，没有补造报价。以下为研究比较，不是新的可执行推荐：

广东宏大002683（最接近但仍否决）：30.11、成交10.39亿元、换手5.30%、120日位置31.8%，已越前20高29.70、尾盘+0.87%、价格高于MA60，优于若干尚未收回MA60的低位反弹。反证是MA5/20/60仍未全多头，T日高30.25即近压；若追到市场组的30.15附近，距首压不足0.4%，到28.70短线失效风险约4.8%。更远的31元或涨停路径尚需市场/板块推进，当前不能用远目标覆盖近压和不可当日止损。10月9日回购原公告不是新军工订单。故本组不选，保留原市场组独立条件不改写。

宇环数控002903：24.96、低位14.1%及尾盘回收有利，但仍低于MA20约8.66%，当日19.13%换手、13.17%振幅；市场原条件25.05确认后很快遇25.22压力，假突破/高开兑现与T+1锁仓风险更高。不能因为机器人题材或“相对低”自动成为第二只。

富临精工300432：广泛池独立比较，收13.48、+7.07%、CLV0.990、RVOL20=2.05、120日位置9.9%，成交约9.33亿元，确有低位推进。反面是20%制度、尚低于MA60约14.61、前20日高13.93未突破；关联交易/融资事项不当作无条件催化。深桑达000032虽然收回MA20、成交11.06亿元，但仍低于MA60且板块强度未达军工局部表现。晶品特装688084的成交约1.94亿元、20%波动和中期反转未确认。均只进入独立30天观察，不替补。

海安集团001233：120日位置36.9%但20/60日位置超过96%，换手17.60%、距MA20+14.76%，同时有实控人质押公告；短周期追高不因长窗口相对低而变安全。天津普林002134虽榜净买1.045亿元，近20%振幅与尾盘回吐否决。万丰002085、亨通600487、文灿603348、晶科601778等封板股无法证明次日普通成交条件，不默认排队可以买；慈文/新华/冰山高位拥挤明确降级。

至少3个替代者已实际比较，0只不是降低重复率硬换股。最近5交易日可见综合决策仅10月12、15、16共3个冻结日、4只代码，10月13/14完整综合决策缺失；最近10日也不完整，所以严格5/10日重复率N/A。本轮0只，无重复新增；旧原价/条件与失败不回改。

三、上一综合组和全部到期观察

10月16日唯一中鼎股份000887：10月19日开17.12，低于事前17.40—18.10范围；全日高17.18也达不到17.78收复。结论是未触发、无策略成交/无该组持仓，不是买入后亏损。日低16.45、收17.00，相对原17.72收盘观察-4.063%，只是价格反例；不能把低点后反弹当可实现利润。原冻结的17.20失效位和条件不后移，新增结果及研究自选理由与原报告关联。

{follow}

已到1/3/5等交易日节点只追加日线观察，未到10/20/30日不填。MFE/MAE从原冻结收盘之后的价格路径计算，不从高低推断分钟先后/9:50或14:40成交。旧未触发/数据不足/涨停无法买到样本保留。当前综合组可验证两侧成交仍0，净胜率、均值/中位净收益、盈亏比和退出质量待验证；20bp占位没有校准，不宣称跑赢基准。

四、量价研究与验证对本轮的作用

完整量价28只和前28只在独立volume_price台账，不只展示本节3—5例。成交放大后价格推进与尾盘承接是支持证据；高位爆量、尾盘回吐、仍未收回中期阻力以及前池负反馈是反证。此前“低位+榜净买就能隔夜安全”的解释被中鼎/金健等价格样本反驳；不能据小样本推导新的稳定概率或自动权重。

本轮没有入选股票，因此本组股票代码、参考介入区间、买点/失效/止盈卡均N/A，不给空仓结论附隐性买入指令。T+1=20日只观察：①同口径红盘能否恢复到至少2800、普通主板跌停能否降至14及以下；②军工/机器人换手核心回踩后能否再推进而非单股冲板；③暂定高度/晋级缺项能否取得完整可复算名单。它们只是研究检查点，不是允许盘中临时替换最终结论。

若未来有另一次事前研究并20日买入，最早21日卖；20日失效也不能当天止损，跌停/停牌/无买盘会延长敞口。T+1涨停只是浮盈，无法成交就不算持仓；T+2涨停也不保证卖出或随后溢价。本轮不承诺涨停概率与收益，不自动下单。APP仅展示归档及验证，不内置大模型、自行训练或越用胜率自然提高。发布状态需CI、精确SHA、Railway SUCCESS及线上读回另行证明，本文归档不预称手机已同步。'''
    return base_report('combined_pair','盘后综合双标｜10月19日四研究齐备，综合盘后组空仓观察',
                       '全A5568入口、120广泛池与完整28深筛重裁决：0只，不机械复制市场组；中鼎19日开17.12低于冻结下界，未触发，价格观察-4.063%不是策略亏损。',body,e,stamp,
                       research_rule_version='combined_limitup_watch_v5',group_label='综合盘后组',selected_codes=[],
                       candidate_count=0,decision='cash_observation_no_qualified_candidate',
                       dependency_report_ids=[MARKET,IDS['volume_price'],IDS['low_position'],IDS['dragon_tiger']],
                       planned_entry_date='2026-10-20',earliest_legal_exit_date_if_bought='2026-10-21',
                       broad_pool_count=120,broad_pool_verified_count=e['volume_price']['broad_verified'],deep_pool_count=28,
                       codes=['000887','002683','002903','300432','000032','688084','001233'])


def limitup_reports(e,stamp):
    common='''缺完整普通主板1/2/3/4/5+逐股梯队、T之前20个实际交易日完整最高高度与分层冻结分母。逐日名单接口403原错误留存，未绕过访问限制；外部暂定总晋级率不能套成逐层晋级。历史新华传媒停牌/复牌11板只列已知发生日期，不把N天M板当连续M板，也不把历史高板当当天流动性。没有Level-2、持续盯盘或排队成交，任何未来开板60秒、撤单/承接与真实上限都要当时核验。'''
    retro=f'''实际完成{stamp}，计划D=2026-10-19，D盘前最新T=10月16日。D事前完整报告、冻结候选和真实执行回执缺失，今天已收盘，本报告仅作v2完整补证审计，原交付blocked；不把缺报算一次“按时空仓”，不倒填盘前价格或候选。

按v2先环境再个股：D前最近三日10月14日约36封/30炸/13跌停、15日约36/7/26、16日聚合61/49/最高新华复牌11板；16日聚合61与名单59来源自有差异，本地普通主板56封/54未封/14跌停，两种口径不合并。15日普跌，16日修复而高炸板仍在。{common}

真实T=16备选比较：中鼎000887收17.72、120日位置22.4%、RVOL20=2.96，但MA20未收复/机构通道净卖/高开风险；冰山000530收7.62、换手33.24%、高位分歧；龙建600853收3.59、RVOL20=5.42但尾盘回落且非强板核心；安达维尔300719为20%制度、尾盘回落且中报亏损，不能混进普通主板10%实验。以上只是以原冻结T记录做风险比较，不根据今天谁涨谁跌回选D候选。

9:25证券状态、D真实涨停价、09:35—10:30第一次开板后60秒/均价承接/两只同伴、排队成交与事前条件没有可恢复证据。中鼎今天开17.12低于综合组范围、金健大跌等只属D结果，不能用于伪造D盘前空仓理由。v1龙溪600592沿用原未触发，不改v1规则/结果；此前v2四轮完整空仓与事后partial审计分开，缺失19日不增加空仓样本。D已无事前补做可能，实际完成此审计和未来D=20研究，未擅改调度或任务启停。'''
    a={'id':'limitup-single-20261019-retro-v2','date':T,'task_id':'limitup_single','track':'market_review',
       'title':'打板v2补证｜10月19日事前报告缺失，保留失败不倒填',
       'summary':'完成D=19事后v2风险补证；无法补成当时事前冻结，原交付blocked，不补造荐股或算作按时空仓。',
       'body':retro,'sources':source_list(e)+['docs/research/combined-pair-2026-10-16-evidence.json'],
       'published_at':stamp,'recorded_at':stamp,'data_cutoff_at':stamp,'report_type':'retrospective_review',
       'eligible_for_integrated_research':False,'provenance':'retrospective_evidence_audit',
       'planned_entry_date':T,'latest_completed_trading_day':PREV,'research_rule_version':'limitup_single_v2',
       'candidate_count':0,'recommendation_ids':[],'not_a_contemporaneous_cash_decision':True,'evidence_file':EFILE}
    forward=f'''D=2026-10-20；最新已完成T=2026-10-19。实际完成/冻结{stamp}，仅使用此时已披露行情与公告。本轮事前决定：空仓，无合格打板候选，不临时替补；v2仍是20—30个实际交易日首轮模拟复核，不证明稳定盈利或自动转实盘。本报告不是19日盘前补写，日期D与T明确分开。

一、先核三日情绪/市场及主线梯队

15日普跌，约36封/7炸/26跌停；16日修复，聚合61封/49炸（来源提示名单仅59），本地普通主板56封/54未封/14跌停；19日权重护盘但2274涨/3129跌、沪深成交1.438万亿元且缩量，本地普通主板40封/36未封/25跌停，外部暂定46/21/最高3板不与本地混算。市场前28池平均收盘-1.94%、龙虎榜前5池-4.29%，一日修复未带来普遍隔夜保护。主线只见军工/机器人/通信/低空局部，广度与高位反馈形成反对。

二、高度、空间与分层晋级

{common}本轮的“可见范围/暂定高度”不能写成完整20日最高，情绪周期起点未知。T=19新华收15.58、高换手、榜净卖，并新发资产购买进展/风险提示；历史11板空间参照没有证明今天新空间突破。普通主板与ST、20%/30%、可转债均分离。关键梯队/空间和D盘口无法查清，按v2否决优先空仓，而不是制造一只或声称所有数据齐全。

三、至少三只真实T备选，先比较角色后否决

万丰奥威002085：T收10.90普通10%封板，120日位置34.5%、RVOL20=3.72、换手4.82%，角色为低空首板/次日1进2待确认；主线完整高度未知，尾盘量小且D普通可买性未知，不能将T封单当D队列；否决。

甘化科工000576：T收9.65封板、RVOL20=5.28、120日位置95.2%，军工启动跟随/计划1进2待确认；已到长期高位，D高开、主线梯队和回封承接未确认，不能用局部军工强度覆盖25只普通跌停环境；否决。

慈文传媒002343：T收10.26、换手46.52%、长期高位、RVOL20=6.43；连续/空间角色不能由暂定聚合硬定，买方通道净买2.16亿元不证明锁仓；异常波动及高位爆量风险，否决。

广东宏大002683与宇环002903虽有量价回收，但T未封板，属于突破/低位反转比较，非已确认1进2；前者近压后风险收益不足、后者19%换手且未收回MA20。本轮不将市场组或低位组名字机械变成打板候选。新华历史高位风险对照，不参与追空间。

四、成交卡/固定退出与旧样本

唯一候选=无，D参考介入价、经核涨停价、支撑/失效价、强平弱开退出价均N/A；上述T价格只用于比较。本次无触发、委托、封板率/炸板率策略样本或持仓。未来新候选须另有事前冻结：正常非ST证券及真实D上限、竞价0—5%、09:35—10:30、换手2—12%、首开后60秒守真实上限98%与成交均价、两只预定同伴≥3%且高标未跌停；缺任何盘口/时序/成交证据不认定买入。这里是原规则说明，不是盘中授权临时替补。

若未来D=20真实买入最早D+1=21日09:30首个能证明可成交的时点退出，强/平/弱开同一规则；买入日炸板不可当天卖，跌停无买盘/停牌/卖单未成保留敞口。止损阈值不保证成交，不用最高涨幅替代收益。v1龙溪原未触发/无持仓结果冻结，v2此前4轮完整空仓、19/16缺事前交付审计分列；本D20成为新的完整事前安全裁决，新增候选0，可验证两侧成交0。

五、统计、发现与下一假设

v2本轮没有股票交易样本，策略封板/炸板率、次日平均/中位净收益、盈亏比、尾部亏损、可执行MFE/MAE与退出质量N/A；未校准20bp不用于收益。市场分层因缺名单不报虚假晋级率，首板/二板/回封、情绪/主线高度/空间、长假和版本分组保留缺项，不重复计数。最重要的反证是局部净买和高度曾修复并未使前池普遍获利；待验证只有低层晋级、换手核心承接和高标负反馈同时改善后，隔夜尾部风险才可能收敛。此前失败保留，不自动训练权重、不承诺收益、融资或借款追板。'''
    b={'id':'limitup-single-20261020-review-v2','date':'2026-10-20','market_date':T,'task_id':'limitup_single','track':'market_review',
       'title':'每日打板v2｜计划10月20日空仓，三日环境与真实备选否决',
       'summary':'T=19、D=20事前冻结空仓；实际核三日环境及5只比较，宽度/尾部与梯队证据缺项触发否决，无候选、无成交。',
       'body':forward,'sources':source_list(e),'published_at':stamp,'recorded_at':stamp,'data_cutoff_at':stamp,
       'report_type':'full_pre_market_risk_decision','eligible_for_integrated_research':False,
       'provenance':'contemporaneous_pre_market_cash_decision','planned_entry_date':'2026-10-20',
       'latest_completed_trading_day':T,'research_rule_version':'limitup_single_v2','candidate_count':0,
       'selected_codes':[],'recommendation_ids':[],'decision':'cash_no_qualified_candidate',
       'ladder_complete':False,'evidence_file':EFILE}
    return [a,b]


def append_observations(e,stamp,recs,volume,low):
    # All original recommendations are immutable; only results are appended.
    recmap={r['id']:r for r in recs['items']}
    for row in e['combined_horizon_validation']:
        rec=recmap[row['recommendation_id']]
        result={'id':rec['id']+'-daily-validation-20261019','recorded_at':stamp,'as_of':'2026-10-19T15:00:00+08:00',
                'market_date':T,'observation_type':'price_observation','observed_open':row['ohlc']['open'],
                'observed_high':row['ohlc']['high'],'observed_low':row['ohlc']['low'],'observed_close':row['ohlc']['close'],
                'close_price_observation_pct':row['price_return_to_T_pct'],'completed_horizon_observations':row['horizons'],
                'executed_trade':False,'executable_net_return_pct':None,'report_id':IDS['combined_pair'],
                'sources':[EFILE],'note':'旧未触发/缺成交结论保留；新日线价格不重建成交、触发顺序或策略净收益。'}
        if row['code']=='000887':result.update(status='not_triggered',trigger_status=row['trigger_status'],entry_fill_status='no_strategy_fill',strategy_sample_activated=False,note=row['reason'])
        if not any(x.get('id')==result['id'] for x in rec.setdefault('results',[])):rec['results'].append(result)
    pv=e['volume_price']['previous_validations']
    volume['items'].append({'id':'volume-price-20261016-validation-20261019-v1','date':T,'recorded_at':stamp,
                           'task_id':'volume_price','kind':'full_forward_price_validation',
                           'origin_cohort_id':'volume-price-20261016-close-v1-cohort','origin_report_ids':['volume-price-20261016-close-v1'],
                           'report_ids':[IDS['volume_price']],'rule_version':'volume_price_close_v4',
                           'full_validation_completed':True,'full_pool_summary':e['volume_price']['previous_statistics'],
                           'full_pool_validations':[dict(r,id='volume-price-20261016-'+r['code']+'-validation-20261019',date=T,recorded_at=stamp,
                                                         report_ids=[IDS['volume_price']],origin_cohort_id='volume-price-20261016-close-v1-cohort',
                                                         full_validation_completed=True,eligible_for_model_statistics=True,
                                                         reference_verified_against_current_provider=True,
                                                         daily_high_price_excursion_pct=r.get('high_observation_pct'),daily_low_price_excursion_pct=r.get('low_observation_pct')) for r in pv],
                           'executable_sample_count':0,'eligible_for_model_statistics':True,
                           'frozen_structure_statistics':e['volume_price']['previous_by_frozen_structure']})
    volume['items'].append({'id':'volume-price-20261019-close-v1-cohort','date':T,'task_id':'volume_price','frozen_at':stamp,
                           'report_ids':[IDS['volume_price']],'rule_version':'volume_price_close_v4',
                           'data_cutoff_at':'2026-10-19T16:15:00+08:00','broad_pool_count':120,
                           'broad_pool_verified_count':e['volume_price']['broad_verified'],'deep_screen_count':28,
                           'eligible_for_model_statistics':True,'provenance':'contemporaneous_close_research',
                           'samples':e['volume_price']['deep_samples']})
    lowmap={s['id']:s for s in low['items']}
    for observation in e['low_position']['existing_validations']:
        sample=lowmap[observation['origin_cohort_id']]
        sample.setdefault('observations',[]).append(dict(observation,recorded_at=stamp))
        bs=e['raw_daily_histories'][sample['code']]; orig=date.fromisoformat(sample['date'])
        nodes=[]
        for n in (1,3,5,10,15,20,30):
            target=orig+timedelta(days=n)
            if target>date.fromisoformat(T):continue
            allowed=[b for b in bs if sample['date']<=b['date']<=target.isoformat()]
            if allowed:nodes.append(('natural_day',n,target.isoformat(),allowed[-1]))
        post=[b for b in bs if sample['date']<b['date']<=T]
        for n in (5,10,20):
            if len(post)>=n:nodes.append(('trading_session',n,post[n-1]['date'],post[n-1]))
        for kind,n,target,b in nodes:
            nid=sample['id']+f'-{kind}-{n}'
            if any(x.get('id')==nid for x in sample['observations']):continue
            path=[x for x in post if x['date']<=b['date']];ref=sample['day0_close']
            sample['observations'].append({'id':nid,'date':b['date'],'recorded_at':stamp,'target_date':target,
                                           'horizon':n,'horizon_type':kind,'close':b['close'],
                                           'close_return_pct':round((b['close']/ref-1)*100,3),
                                           'path_mfe_pct':round((max(x['high'] for x in path)/ref-1)*100,3) if path else None,
                                           'path_mae_pct':round((min(x['low'] for x in path)/ref-1)*100,3) if path else None,
                                           'observation_type':'price_observation','executable_net_return_pct':None,
                                           'report_ids':[IDS['low_position']],'source_urls':observation['source_urls'],
                                           'calculation_version':'low_price_observation_v2_20261019',
                                           'note':'信号收盘后路径；自然日遇休市取不晚于目标日最近交易日；真实迟到录入。'})
    for s in e['low_position']['new_candidates']:
        low['items'].append({'id':'low-position-20261019-'+s['code'],'date':T,'recorded_at':stamp,
                             'code':s['code'],'name':s['name'],'sector':SECTOR.get(s['code'],'行业待细分'),
                             'primary_model':'低中位放量推进/平台确认','day0_close':s['close'],'invalid_close_below':s['low'],
                             'initial_invalidation_basis':'收盘跌破信号日低点；不后移',
                             'original_snapshot_provenance':'contemporaneous_full_market_and_crosschecked_daily',
                             'original_snapshot_verified':s['daily_crosscheck']['max_ohlc_difference']==0,
                             'eligible_for_model_statistics':s['daily_crosscheck']['max_ohlc_difference']==0,
                             'day0_rvol20':s['rvol']['20'],'day0_turnover_pct':s['turnover_pct'],'day0_amount_yi':s['amount_cny']/1e8,
                             'day0_clv':s['clv'],'day0_range_position_pct':s['range_position_pct'],'day0_moving_averages':s['ma'],
                             'snapshot':s,'report_ids':[IDS['low_position']],'observations':[],'sources':[EFILE,s['daily_source']]})
    low['updated_at']=stamp


def catalog_updates(e,stamp,catalog):
    changed=[]
    existing={s['code']:s for s in catalog['items']}
    for code in ('300058','000420'):
        stock=existing[code];obs=next(r for r in e['low_position']['existing_validations'] if r['code']==code)
        stock['history'].append({'id':f'research-stock-{code}-20261019-low-validation','date':T,'recorded_at':stamp,
                                 'title':'30天台账全路径日线验证（非新推荐）',
                                 'reason':f"{stock['name']}相对原收盘参考截至19日{obs['close_return_pct']:+.2f}%；价格路径和原失效保留，不是成交收益。",
                                 'evidence_status':'verified_daily_price_observation','fact_note':'新计算严格排除信号日收盘前极值，旧记录不改。',
                                 'validation':['继续1/3/5/10/15/20/30自然日及5/10/20交易日节点；30天未成熟。'],
                                 'risk':'日线极值不能推断成交、时序、资金身份或策略净收益。','report_ids':[IDS['low_position']],'sources':[EFILE]})
        changed.append(code)
    for code in ('000887','300450'):
        stock=existing[code];row=next(r for r in e['combined_horizon_validation'] if r['code']==code)
        stock['history'].append({'id':f'research-stock-{code}-20261019-combined-validation','date':T,'recorded_at':stamp,
                                 'title':'综合组原样本后续验证，不反写原结论',
                                 'reason':row.get('reason',f"{stock['name']}新到期价格节点已追加，旧触发/未成交状态不变。"),
                                 'evidence_status':'verified_daily_and_frozen_condition_failure' if code=='000887' else 'verified_daily_price_observation',
                                 'fact_note':f"19日收{row['ohlc']['close']:.2f}、相对原参考{row['price_return_to_T_pct']:+.3f}%，不是可执行收益。",
                                 'validation':['原触发条件不后移；只追加到期1/3/5/10/20/30交易日与触发证据。'],
                                 'risk':'未触发或缺两侧成交不能统计策略胜率；止损阈值不保证成交。',
                                 'report_ids':[IDS['combined_pair']],'sources':[EFILE]})
        changed.append(code)
    for s in e['low_position']['new_candidates']:
        stock=existing.get(s['code'])
        if stock is None:
            stock={'code':s['code'],'name':s['name'],'sector':SECTOR.get(s['code'],'行业待细分'),'role':'research','default_watch':False,'history':[]}
            catalog['items'].append(stock)
        stock['history'].append({'id':f"research-stock-{s['code']}-20261019-low-sample",'date':T,'recorded_at':stamp,
                                 'title':'独立30天低中位放量样本，不是综合短线指令',
                                 'reason':f"{s['name']}收{s['close']:.2f}、RVOL20={s['rvol']['20']:.3f}、120日位置{s['range_position_pct']['120']:.1f}%、CLV{s['clv']:.3f}，达到原30天入池门槛；本次综合组空仓。",
                                 'evidence_status':'verified_same_day_daily_and_issuer_notice_review',
                                 'fact_note':'实际冻结于本次报告完成；未回填盘中推荐、买入或未实现收益。',
                                 'validation':[f"后续收盘跌破原位{s['low']:.2f}记失效；跟踪自然日及交易日节点，不删除失败。"],
                                 'risk':'相对低位不等于绝对底部；公告、波动与中期均线风险见完整报告；不能认定资金身份。',
                                 'report_ids':[IDS['low_position']],'sources':[EFILE]})
        changed.append(s['code'])
    return changed


def main():
    e=load_evidence(ROOT/EFILE)
    assert len(e['volume_price']['deep_samples'])==28
    assert len(e['volume_price']['previous_validations'])==28
    assert len(e['low_position']['existing_validations'])==26
    assert all(s['seat_reconciliation']['matched'] for s in e['dragon_tiger']['selected_observations'])
    assert all(s['daily_crosscheck']['max_ohlc_difference']==0 for s in e['volume_price']['deep_samples'])
    research,recs,runs,volume,low,catalog=map(load,['research.json','recommendations.json','task_runs.json','volume_price_samples.json','low_position_samples.json','research_stocks.json'])
    if any(r['id']==IDS['combined_pair'] for r in research['items']):
        print('Same-T combined decision already present: no duplicate report/candidate.');return
    assert any(r['id']==MARKET and r.get('eligible_for_integrated_research') for r in research['items'])
    assert any(r.get('status')=='completed' and MARKET in r.get('report_ids',[]) for r in runs['items'])
    now=datetime.now(timezone.utc);stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds');utc=now.isoformat(timespec='seconds')
    reports=[volume_report(e,stamp),low_report(e,stamp),dragon_report(e,stamp),combined_report(e,stamp)]
    limits=limitup_reports(e,stamp)
    research['items'].extend(reports+limits)
    append_observations(e,stamp,recs,volume,low)
    for r in reports:
        runs['items'].append({'id':r['run_id']+'-completed','run_id':r['run_id'],'task_id':r['task_id'],'date':T,'trigger':'scheduled',
                              'started_at':START,'recorded_at':utc,'completed_at':utc,'status':'completed','summary':r['summary'],
                              'report_ids':[r['id']],'analysis_completed':True,'recommendation_ids':[],
                              'delivery_status':'repository_prepared_not_yet_verified','sources':[EFILE],
                              'started_at_scope':'本次真实综合执行开始，包含读取、取证、分析；模块独立报告和回执。'})
    for r in limits:
        blocked=r['date']==T
        run='limitup-single-'+r['date'].replace('-','')+('-retro-audit-v2' if blocked else '-scheduled-v2')
        runs['items'].append({'id':run+('-blocked' if blocked else '-completed'),'run_id':run,'task_id':'limitup_single','date':r['date'],
                              'trigger':'scheduled','started_at':START,'recorded_at':utc,'completed_at':utc,
                              'status':'blocked' if blocked else 'completed','summary':r['summary'],'report_ids':[r['id']],
                              'analysis_completed':not blocked,'recommendation_ids':[],'sources':[EFILE]})
    changed=catalog_updates(e,stamp,catalog)
    for name,obj in [('research.json',research),('recommendations.json',recs),('task_runs.json',runs),
                     ('volume_price_samples.json',volume),('low_position_samples.json',low),('research_stocks.json',catalog)]:save(DATA/name,obj)
    save(ROOT/'app/src/main/assets/research_stocks.json',catalog)
    for r in reports+limits:savepath=ROOT/'docs/research'/(r['id']+'.md');savepath.write_text(r['body']+'\n')
    manifest={'market_date':T,'recorded_at':stamp,'report_ids':[r['id'] for r in reports+limits],
              'changed_research_stock_codes':changed,'candidate_count':0,'decision_id':IDS['combined_pair'],
              'delivery_status':'not_yet_CI_or_production_verified'}
    save(ROOT/'docs/research/combined-pair-20261019-publication-manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
