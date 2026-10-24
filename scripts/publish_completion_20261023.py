#!/usr/bin/env python3
"""Publish the 23 October catch-up as an append-only, reviewable research bundle.

Inputs are dated observations collected separately. No orders, fills, probabilities,
or retrospective trade signals are manufactured by this publication helper.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo
import gzip, hashlib, json, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT.parent/'task_audit_20261023'
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'scripts'))
from learning_loop import append_snapshot, nth_session_after
from prepare_completion_20261023 import pct, stats

T='2026-10-23'; D='2026-10-26'; EXIT='2026-10-27'
EV='docs/research/completion-20261023-evidence.json.gz'
IDS={'market_review':'market-review-20261023-close-v1','volume_price':'volume-price-20261023-close-v1',
     'low_position':'low-position-20261023-close-v1','dragon_tiger':'dragon-tiger-20261023-close-v1',
     'limitup_single':'limitup-single-20261023-close-v2','learning_review':'learning-review-20261023-forward-v1',
     'low_dragon':'low-dragon-20261023-completion-v1'}

def load(p):return json.loads((ROOT/p).read_text())
def save(p,v):(ROOT/p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+
                     ['|'+'|'.join('N/A' if v is None else str(v) for v in r)+'|' for r in rows])
def dedup(seq):return list(dict.fromkeys(seq))

SECTORS={
 '603278':'机器人关联/轮胎材料','301413':'机器人/传感器','002009':'机器人/汽车产业链',
 '002724':'军工/照明','002421':'物理AI/智能建筑','003021':'机器人/微型传动',
 '301023':'机器人/传动','002343':'传媒/短剧','300466':'机器人/智能制造','002474':'软件/信创',
 '001283':'消费电子/电池','301666':'半导体/存储','000678':'机器人/轴承','300298':'医疗器械',
 '300503':'机器人/机床','603677':'家电/机械','603341':'消费电子','603728':'机器人/电机',
 '002249':'机器人/电机','300484':'电气设备/机器人','300007':'传感器/机器人','603528':'机器人/智能交通',
 '300184':'电子元件','688500':'软件/数据服务','603448':'智能装备（短历史）','603089':'汽车零部件/机器人',
 '603721':'传媒/短剧','301707':'半导体（短历史）'}

def main():
    research=load('backend/data/research.json');runs=load('backend/data/task_runs.json')
    if any(r['id']==IDS['learning_review'] for r in research['items']):
        raise RuntimeError('Catch-up already published; never rewrite its frozen evidence')
    raw=json.loads((AUDIT/'completion_raw.json').read_text())
    su=json.loads((AUDIT/'completion_supplement.json').read_text())
    de=json.loads((AUDIT/'completion_derived.json').read_text())
    scan=load('docs/research/low-dragon-2026-10-23-market-scan.json')
    ve=load('docs/research/volume-price-20261023-close-evidence.json')
    prior22=load('docs/research/market-review-2026-10-22-evidence.json')
    low=load('backend/data/low_position_samples.json');recs=load('backend/data/recommendations.json')
    learning=load('backend/data/learning.json');catalog=load('backend/data/research_stocks.json')
    now=datetime.now(timezone.utc);stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    started=raw['started_at_utc'];daily=raw['daily'];lookup={r['code']:r for r in de['broad_recomputed']}
    deep=[lookup[r['code']] for r in scan['deep_pool']]
    for r in deep:r['sector_research_label']=SECTORS[r['code']]
    lv=de['low_validations'];selected=de['dragon_selected'];dv=de['dragon_previous_validations']
    assert len(lv)==39 and len(de['broad_recomputed'])==120 and len(deep)==28
    assert len(selected)==8 and all(r['seat_reconciliation']['matched'] for r in selected)
    assert not su['daily_errors'] and not su['seat_errors']
    assert all(not r['missing_sessions'] for r in lv)
    # Preserve all original sample attributes and every previous observation.
    for s in low['items']:
        v=next(r for r in lv if r['origin_cohort_id']==s['id'])
        v['calculated_at']=v['recorded_at'];v['recorded_at']=stamp
        s.setdefault('observations',[]).append(v)
    low['updated_at']=stamp
    learn=de['learning_snapshot'];learn['calculated_at']=learn['recorded_at'];learn['recorded_at']=stamp
    learning,added=append_snapshot(learning,learn)
    if not added:raise RuntimeError('Existing learning snapshot requires separate reconciliation')
    # A fresh result never reactivates an old trading condition.
    for r in recs['items']:
        bars=daily[r['code']]['bars'];by={b['date']:b for b in bars};cur=by[T]
        anchor=r.get('planned_entry_date') or r['date'];base=by.get(anchor)
        horizons=[]
        for h in (1,3,5,10,20,30):
            target=nth_session_after(date.fromisoformat(anchor),h)
            if not target or target.isoformat()>T:
                horizons.append({'h':h,'status':'pending','date':target.isoformat() if target else None});continue
            b=by.get(target.isoformat());path=[x for x in bars if anchor<x['date']<=target.isoformat()]
            horizons.append({'h':h,'date':target.isoformat(),'status':'price_observed' if b and base else 'missing',
                             'close_pct':pct(b['close'],base['close']) if b and base else None,
                             'mfe_pct':pct(max(x['high'] for x in path),base['close']) if path and base else None,
                             'mae_pct':pct(min(x['low'] for x in path),base['close']) if path and base else None})
        result={'id':r['id']+'-price-review-20261023','date':T,'market_date':T,'recorded_at':stamp,
                'report_ids':[IDS['limitup_single'] if r['task_id']=='limitup_single' else IDS['learning_review']],
                'status':'price_observation_only','observed_daily':cur,'anchor_date':anchor,
                'anchor_close':base['close'] if base else None,'horizons':horizons,
                'trigger_status':'original_no_entry_preserved' if r['id']=='limitup-single-20261008-600592-v1' else 'not_reconstructed_from_daily_extremes',
                'executed_trade':False,'executable_net_return_pct':None,'source':daily[r['code']]['source'],
                'note':'补充价格路径，原推荐、触发/失效与既有结果冻结；未验证实际委托或成交。'}
        r.setdefault('results',[]).append(result)
    # Prior whole-market deep pool and volume cohort share the same original 28 symbols.
    previous=ve['previous_pool_validation']
    assert {r['code'] for r in previous}=={r['code'] for r in prior22['deep_pool']}
    minute_checkpoints=[]
    for v in previous:
        m=su['minute_price_points'].get(v['code'],{})
        g=next((x for x in m.get('groups',[]) if str(x['date'])=='20261023'),{})
        p={x['clock']:x for x in g.get('points',[])}
        minute_checkpoints.append({'code':v['code'],'name':v['name'],
            'checkpoints':{k:p.get(k) for k in ('0930','0945','1030','1130','1400','1430','1500')},
            'point_count':len(p),'source':m.get('source'),'full_minute_OHLC':False,'verified_fill':False})
    # Independent THS summaries are compared by code + single-day period, never by row order.
    ths=json.loads((AUDIT/'ths_tables.json').read_text());thsrows=ths[5]['rows'];cross=[]
    for s in selected:
        match=next((r for r in thsrows if str(r.get('1','')).zfill(6)==s['code'] and r.get('0') is None),None)
        cross.append({'code':s['code'],'ths_single_day_row':match,'price_agrees':bool(match and abs(match['3']-s['close'])<0.011),
                      'join_scope':'single_day_code_summary_only; exact TRADE_ID joins use Eastmoney source'})
    assert all(x['price_agrees'] for x in cross)
    groups=defaultdict(list)
    bysample={x['id']:x for x in low['items']}
    for v in lv:groups[bysample[v['origin_cohort_id']]['primary_model']].append(v)
    modelstats=[]
    for model,vs in groups.items():
        mature=[x for x in vs if x['thirty_natural_days_matured'] and x['eligible_for_model_statistics']]
        modelstats.append({'model':model,'all_n':len(vs),'eligible_n':sum(x['eligible_for_model_statistics'] for x in vs),
                           'mature_30d_eligible_n':len(mature),'mature_30d_stats':stats([x['close_return_pct'] for x in mature]),
                           'note':'不同入选日的当前回报不合并为30日策略成绩'})
    learningstats={str(h):stats([o['close_pct'] for r in learn['evaluations'] for o in r['horizons'] if o['h']==h and o['status']=='observed']) for h in (1,2,5,10)}
    common_sources=dedup(scan['sources']+['https://www.cls.cn/detail/2513445',
        'https://api3.cls.cn/share/article/2513493?app=&os=CailianpressWeb&sv=815',
        'https://api3.cls.cn/share/article/2512173?app=&os=android&sv=830',
        'https://api3.cls.cn/share/article/2510941?app=&os=android&sv=873',
        raw['other_sources']['index_quotes']['source'],EV])
    intro=f'研究交易日T={T}；实际补做完成时间{stamp}。行情只使用截至T收盘的资料；本轮在周末补齐漏跑研究，不补造10月23日盘前/盘中推荐。下一实际交易日为{D}；如当日真实买入，最早{EXIT}可卖。候选与成交须分别验证。'
    marketfacts='上证3690.48（+0.89%），深成指11673.83（+2.79%），创业板2684.10（+4.16%），科创50 1345.51（+3.04%）。沪深成交约19562.58亿元；新浪全A不同范围合计19724.44亿元，两种范围不混加。全A有效5573只（原始5576，分页错误0），上涨4525、下跌909、平盘139；前一日为535/4998/38。'
    emotion=table(['交易日','财联社涨停/炸板/封板率（不含ST/退市）','连续板数','跌停口径'],[
        ['10月21日','50 / 19 / 72%','16','旧档打板客5；口径不完全同源'],
        ['10月22日','33 / 23 / 59%','9','新浪普通非ST主板≤-9.5%代理58'],
        ['10月23日','82 / 12 / 87%','12','同代理11，不能当精确跌停池']])
    ladder='截至23日财联社可见连续板：大业股份603278、海洋王002724均6板，上海九百600838为3板；2板共9只，其中华阳智能301502为20%制度另列，普通主板2板8只为正裕工业603089、多伦科技603528、林州重机002535、兆威机电003021、赛福天603028、襄阳轴承000678、南方路机603280、睿能科技603933。4/5板在该连续板表为0；普通主板首板完整数量未独立核清。慈文传媒11天7板不是7连板。图表给出跨板块1进2=9/24、2进3=1/5、5进6=2/2，且整体旧连板晋级3/9；除5进6两只已逐名核对，其余前一日完整逐股分母未冻结，主板专属晋级率记N/A。前20交易日主板最高高度与情绪周期起点仍缺完整样本，不能声称空间突破。'
    # At least five economic groups are visible, with labels explicitly qualitative.
    deep_table=table(['代码/名称','研究行业标签','收盘','RVOL5/10/20','20/60/120日区间位置%','距MA20% / CLV','14时至收盘%'],[
        [f"{r['code']} {r['name']}",SECTORS[r['code']],r['close'],'/'.join(str(r['rvol'][str(k)]) for k in (5,10,20)),
         '/'.join(str(r['range_position_pct'][str(k)]) for k in (20,60,120)),f"{r['distance_ma20_pct']} / {r['clv']}",r['tail_1400_close_pct']] for r in deep])
    prev_table=table(['代码/名称','开盘%','最高观察%','最低观察%','收盘%'],[[f"{r['code']} {r['name']}",r['open_pct'],r['mfe_pct'],r['mae_pct'],r['close_pct']] for r in previous])
    methodology='RVOL为当日成交量/此前5、10或20个已完成交易日均量；本补充MA含T当日收盘，原扫描MA字段的窗口定义保留，差值不当成行情错误。区间位置=(收盘-窗口最低)/(最高-最低)，不是获利盘。CLV=(收盘-当日最低)/(最高-最低)，只衡量收盘位置。120只均用未复权日线重算并与新浪当天OHLC比对，短上市历史不足60/120日记N/A。分钟只为价格点及累计量额，不是完整OHLC、盘口或成交回报。'
    methodology+=' 原量价扫描在T之前的可得K线计算MA/区间，历史不足N天时原字段也可能有值；本补充严格要求满N天，原值不作为完整N日历史证明。已恢复的原报告/样本保持冻结，后续统计应使用本次明确的缺历史标记。'
    prior_stats=ve['previous_pool_statistics']
    market_body=f'''{intro}

一、市场与情绪
{marketfacts}

{emotion}

判断：退潮后的强修复，尚不是已验证的持续启动。支持证据是宽度和涨停数量扩大、封板率修复、机器人及物理AI共同走强；反证是6板高标盘中剧烈分歧、深筛多股高乖离、旧池18/28在盘中相对前收曾低于-5%。银行、电力在全面反弹中偏弱。板块判断来自当日公开复盘和个股联动，不用个股涨幅代替精确行业指数排名。

{ladder}

二、覆盖与28只深筛
复用当日18:33北京时间已留档全市场扫描，广泛池120、深筛28；本轮重新取回相关198只未复权日线。深筛覆盖机器人/机械、军工、软件、电子/半导体、医疗、传媒、家电等研究类别，行业标签用于研究分组。启发式排序只用于组织候选，不作为已验证胜率评分。
{methodology}

{deep_table}

三、上日完整池验证
10月22日复盘深筛28只与量价原28只逐码相同，因此关联原volume-price-20261022-close-v1-cohort，只统计一次。28/28已补齐日线：18只收红，均值+2.410%，中位+3.413%；平均最低观察-5.475%，18只最低观察≤-5%。这些均以22日收盘为基准，不是23日实际买入收益。

{prev_table}

原任务9:50/14:40及盘后组分开保留；本次完整分钟价格点覆盖见证据文件。未留存的竞价和实际触发序列不反推，买入后分时退出窗口收益、手续费滑点后净收益均N/A。原两只条件观察日发精机/长江电力的价格结果已追加，是否满足全部板块、顺序与成交条件仍不由OHLC替代。

四、选股影响与反例
正式新增推荐0只。优先研究观察力源信息300184和昊志机电300503：前者收10.84，RVOL20=3.524，距含T的MA20约+0.217%，120日区间14.151%，但仍低于MA60约11.674；后者收62.30，RVOL20=3.183，120日区间20.552%，仍在MA60约64.855下方。两者是20%制度研究对象，不混入普通主板打板统计，公告/竞价/订单条件未完成前不转成交易推荐。
替代比较：大业股份距MA20约+50.20%且6板剧震，否决低位标签；天博智能603448历史不足60/120日，不能证明长期低位；展芯股份301707仍低于MA20约7.83%，反弹不等于反转；天奇股份002009的20日区间100%，虽120日位置较低，也不能只挑长期位置忽略近期冲高。
新推荐为0，推荐重复率N/A。深筛与可核档案的交集8/28=28.57%，但过去5日仅有1日、10日仅有2日结构化完整codes可比，不能伪装完整5/10日重复率；逐日缺项在repeat_audit保存。

五、下一交易日条件观察（不恢复已删除的指数预测栏目）
上行情景：10月26日上证持续站在23日高点3691.40之上，且上涨家数维持3000以上、机器人核心分歧后能承接，才支持修复延续；跌回该高点下且宽度回落使其失效。震荡情景：指数在3658.03（22日收盘）至3691.40间来回，量能低于23日同时间口径，缩小追涨范围。下行情景：失守3658.03且下跌家数重新占优、高标开板亏损扩散，否决追板；跌破23日低点3574.27为更强反证。均为事前可证伪的观察假设，无校准概率。
只观察三件事：高标次日竞价与开板反馈；机器人首板/二板梯队的真实承接；近MA20放量样本能否缩量守住23日低点并再上行。若26日入场，最早27日退出；止损价不保证有成交。
'''
    lowtable=table(['原样本/代码','自然日/交易日','收盘观察%','路径MFE/MAE%','收盘峰谷回撤%','首次收破原失效'],[
        [f"{x['reference_date']} {x['code']} {x['name']}",f"{x['elapsed_natural_days']}/{x['elapsed_trading_sessions']}",x['close_return_pct'],f"{x['path_mfe_pct']}/{x['path_mae_pct']}",x['max_close_to_close_drawdown_pct'],x['first_verified_close_below_original_invalid']] for x in lv])
    lowbody=f'''{intro}

A. 新增低位启动样本
全A入口5573→广泛120→深筛28；本轮新增正式30天样本0。保留力源信息300184和昊志机电300503两只后续复核对象，完整20/60/120日位置、RVOL5/10/20、换手/成交额与均线见证据。力源信息低于MA60、昊志机电同样未越过MA60，23日大幅修复之后还需观察缩量回踩与板块延续。天博智能603448、展芯股份301707缺60/120日历史，不能用短历史证明长期低位。没有逐股完成公告/减持/解禁核验，周末补做不冒充23日实时冻结的新启动信号。

B. 全部既有样本的重要变化
39个原始样本、38只股票全部复核；吉林化纤两个不同日期的样本分别保留，没有按股票代码合并删除。39条原始参考收盘均能与本轮未复权日线对应，路径交易日缺口0；原快照真实性和模型资格仍逐条保留。固定初始失效位，不因反弹后移；回撤计算本轮明确包含信号日参考收盘，旧计算原文不改写。

{lowtable}

10月22日四只影子样本次日收盘观察：长江电力-1.241%、吉林化纤-1.508%、农业银行-2.838%、日发精机+3.934%；均值-0.413%、中位-1.375%，只有1/4为正。它们同属一个日期且市场风格不同，不把25%叫作模型胜率。说明“市场普涨”不足以保证低位代理样本同步上涨。

C. 30自然日到期复盘
9月23日双环传动002472和宝信软件600845达到30自然日，只有16个交易日，不是30交易日。双环当前相对原参考+9.180%，路径最大有利+9.979%、最大不利-14.023%；宝信当前-3.599%，最大有利+0.872%、最大不利-8.942%。两者均曾在10月8日收破原失效位，因此双环最后反弹不能抹去原路径风险。
两条最早样本的original_snapshot_verified=false，原先已标不进模型统计；本轮保持这一资格，故已到30自然日的原始观察N=2，合格30日模型样本N=0。不能计算或宣称稳定30天胜率、盈亏比或10%/20%达标率。30交易日样本N=0。已归档每只1/3/5/10/15/20/30自然日节点与5/10/20/30交易日节点，非交易日节点取其前一可得收盘并显式记实际日期。

D. 当前模型阶段统计
{table(['模型','原样本数','本轮价格核验合格数','可用30自然日模型数'],[[x['model'],x['all_n'],x['eligible_n'],x['mature_30d_eligible_n']] for x in modelstats])}

不同入选日期的当前收益不混成同一30天收益。没有可靠基准全路径和成交费用，超额收益与可执行净收益N/A。全部失败、未成熟、旧快照缺失样本保留。

下一项可证伪假设：仅在初始60/120日位置较低且放量后回踩不破原低点、板块继续扩散时，观察后续5/10/20日MAE是否改善；在未来日期冻结，当前不修改low_position_30d_v1规则。RVOL、CLV及区间位置只是公开量价描述，不证明某类账户吸筹。
'''
    seat_table=table(['股票/代码','榜单净额万元','机构净额万元','股通净额万元','买1/卖1集中度%','日榜TRADE_ID'],[
        [f"{x['name']} {x['code']}",round(x['net_cny']/1e4,3),x['institution_net_wan'],x['stock_connect_net_wan'],f"{x['buy_concentration_top1_pct']}/{x['sell_concentration_top1_pct']}",x['selected_trade_id']] for x in selected])
    dragonbody=f'''{intro}

一、独立龙虎榜覆盖与口径
东方财富当日原始理由行98、去重股票78，包含不同市场、ST/退市与多日榜，全部原行留档；单独选取8只作深入席位比较，均按同一TRADE_ID核对买五/卖五，不把同一股票多条上榜理由相加。8/8买卖合计核对通过，同花顺单日摘要的8只收盘价交叉一致；两个网站原始行数不同不能直接当缺股。机构总量媒体口径39只沪深股与包含其他市场/统计期间的口径有差异，不据此下全市场净买结论。
深圳部分披露汇总使用买五卖五去重后的并集，上海所选单日行用两侧前五合计；每条明确aggregate_basis。机构多席位与股通双向买卖按原始部门代码及期间去重，“买入额”不冒充净买入。未入前五的席位行为不可见。

{seat_table}

二、席位结构、量价共振与反例
天娱数科8.03，机构净买6738.887万元、股通净买5649.305万元，正向共振；但RVOL20只有1.406，单一买席约34.67%，尚不能证明资金连续流入。埃斯顿29.18，机构+945.274万元、股通+6079.244万元，RVOL20=2.667；买1约47.98%，集中度较高，次日一旦该方向不承接可能放大波动。歌尔股份23.11，机构+2165.898万元、股通+6871.885万元，RVOL20=1.654，为较低乖离对照，仍要验证后续普通成交承接。
慈文传媒涨停同时机构净卖4390.237万元，距MA20约45.73%，是涨价与机构席位方向背离的反例。海洋王6板但当日日榜净额-1554.643万元、机构与股通皆净卖；其3日榜另有净买，不能拿累计净买掩盖当天分歧。大业股份日榜净卖5598.679万元、距MA20约50.20%，高标修复不等于低风险隔夜。
风语筑14.69，日榜净卖12684.122万元、股通净卖4283.451万元，封板不能抵消资金分歧。晶丰明源105.96，20%制度另组；股通买入8361.582万元、卖出8290.443万元，净额只有71.139万元，不能把买入额当净买入；日榜净卖4118.355万元，机构净卖5001.153万元。全部计算可由原席位复算。
营业部事实画像：天娱买一为国泰海通三亚迎宾路，歌尔与埃斯顿的西安西大街席位出现在买侧；海洋王的华泰深圳彩田路同时有较大买卖。这只说明本期披露的双向活动/集中度，不能确认某游资本人、量化账户、锁仓比例或真实持仓。历史风格需要跨日期可复核样本，本轮不编造席位胜率。

三、上一观察组全量验证
10月22日机构29只与股通17只公开比较名单的并集33只，全部补齐23日日线，16/33收红，均值+1.435%、中位-1.736%，最差-10.012%、最好+20.000%；该组包含不同涨跌幅制度，分市场结果见原始逐股证据，汇总只作覆盖描述，不当交易策略比较。22日正式龙虎榜交易候选0，故实际策略成交N=0。上一日机构买入并不保证次日普涨；保留所有负例，不能只追踪当天上涨的席位股票。

{table(['代码/名称','开盘%','收盘%','最大有利/不利观察%'],[[f"{x['code']} {x['name']}",x.get('open_pct'),x.get('close_pct'),f"{x.get('mfe_pct')}/{x.get('mae_pct')}" ] for x in dv])}

四、情绪、高度、空间及下一步
{ladder}
阶段判断为强修复待验证，普通主板、20%与北交所样本分开保存。对天娱/埃斯顿/歌尔的次日承接与慈文/海洋王/风语筑的背离组分别跟踪；交易名单0。假设是“同日机构与股通同向且低乖离，比高位价格强而席位卖出的组有更小T+1不利波动”，只前推登记，不用当日结果调门槛。未来有真实介入仍受A股T+1，不能用买入日止损退出；缺分钟触发、订单、费用就不报净收益。
'''
    limitbody=f'''{intro}

结论：本次补做研究空仓，无合格打板候选。规则limitup_single_v2保持冻结，正式新增候选0，继续模拟验证。周末不发布“今日盘中买入”；10月26日只作复市准备，未达到全部条件不转交易。

一、先看市场与梯队
{marketfacts}

{emotion}

{ladder}
修复支持来自涨停与宽度；否决来自高标日内大幅分歧、部分高位日榜资金卖出和完整前序晋级/20日空间基准缺失。媒体跨制度9/24不能当普通主板首板进二板胜率。

二、全A入口及真实替代比较
沿用5573只全A扫描、120广泛池、28深筛；普通主板10%与创业/科创20%及北交所独立处理。
{table(['对象','T参考收盘','角色/支持','否决或待查'],[
 ['天奇股份002009',17.30,'机器人、23日涨停；RVOL20约5.75','20日区间顶端，首板/回封时序与真实队列未核清'],
 ['天娱数科002354',8.03,'AI传媒；日榜机构/股通同向','主线身份及首次回封质量待确认，RVOL20约1.41'],
 ['埃斯顿002747',29.18,'机器人、较低乖离；机构/股通同向','买1集中约48%，次日公告/竞价与可成交性待核'],
 ['歌尔股份002241',23.11,'消费电子、距MA20约4.86%，机构/股通同向','不能仅因低乖离替代完整首板谱系和盘口'],
 ['海洋王002724',12.33,'军工6板高标观察','高位剧震，日榜机构/股通净卖，否决'],
 ['大业股份603278',15.96,'机器人6板高标观察','高乖离、爆量大振幅、日榜净卖，否决']])}
这些参考价对应10月23日收盘，不是成交价；10月26日涨停价及除权/ST/停牌状态没有完成权威核验，因此所有“经核验D日涨停价”记N/A，不用前收×1.1直接当作实盘上限。已披露日榜只能用于之后的计划，不能用于23日盘中事后挑选。

三、下一轮必须核验与退出边界
观察窗口为26日9:25及9:35—10:30北京时间；参考高标固定海洋王002724、大业股份603278，机器人同伴固定天奇002009、埃斯顿002747，数据基础为23日，次日表现尚未知。逐股公告与交易状态、有效竞价、板块同步、首开后承接/回封顺序、成交量与盘口都须有可靠证据。一字无普通成交、持续撤单/反复开板、爆量无法推进、高标断板亏损扩散或缺实时证据一律放弃。没有本次入选股，故不虚构具体委托价/仓位或已触发条件。
如后续26日另行冻结合格条件并真实买入，最早27日才可卖；强开观察能否持续承接，平开检验原价位，弱开或失效时在首个实际可成交窗口执行原计划，跌停/停牌则记录未能退出。当前无候选，不制定事后可变的假止损价格。20—30交易日仅是第一轮模拟复核点，不能自动转实盘。

四、旧600592样本与统计
龙溪股份600592的10月8日limitup_single_v1条件与10月12日已存结果保持原样：原必要开盘价格条件不满足，未形成策略入场。当前只追加截至23日价格路径，不重新激活过期候选。原信号日收盘锚15.55；T+1收盘观察-1.479%、T+2 -6.624%、T+5 -14.662%、T+10 -3.923%，最大不利路径约-14.920%，均不是持仓亏损或实盘收益；它属于国庆后样本另列。
v1唯一冻结候选N=1、验证入场N=0；v2新增候选N=0、验证成交N=0。首板/二板/回封的策略封板率、炸板率、盈亏比、可执行净收益与尾部损失全部N/A；市场82/12是市场统计而非本策略成功率。手续费与滑点未因无成交而伪造净收益。新假设：在修复初日保留低乖离普通主板组，与6板高标组比较未来次日承接和MAE，之后按事前名单前推，当前不改规则。
'''
    mature2=learn['validation']['total_mature_t2_featured'];dates=learn['validation']['unique_cohort_dates']
    learnbody=f'''{intro}

学习归档已用截至23日的未复权日线重新计算，新增forward-learning-2026-10-23快照；实际执行/录入时间为本次真实时刻，历史评估截止T单独保存，没有把执行时间倒填23日收盘。沿用forward_learning_v1，所有特征只用各原信号锚之前的数据。

一、新快照与成熟度
31条原始推荐记录逐条评估：22条T+2已观察、9条因回溯来源不合格而排除；行情读取缺失0。相较22日21条/6个日期，本次T+2含特征样本22条/7个日期；仍少于预设36条及20个独立日期，不能进行可信训练/留出阈值筛选。model_weights_updated=false，strategy_active_rules_changed=false，没有自行训练或提高胜率的声明。

{table(['信号后交易日','已观察N','平均收盘变化%','中位数%','正变化N','最差%'],[[h,v['n'],v['mean_pct'],v['median_pct'],v['positive_n'],v['min_pct']] for h,v in learningstats.items()])}
上表是相对原计划交易日收盘的价格代理，非按原触发买入；不同期限成熟样本数不同，不用跨行均值断言持有越久越好。9条回溯记录保留但不进入前推成绩；非交易日按交易所日历，不以现存K线行号跳过停牌。真实成交、费用、滑点与T+1退出证据不足，可执行净收益N/A。

二、低位独立影子组
4条10月22日原时点冻结的形态观察已有T+1日线：平均-0.413%、中位-1.375%、1/4收红；T+1盘中MAE中位-5.100%。T+2/5/10/30尚未成熟，所以总状态仍pending，并非忘记更新。该组与正式推荐统计分开，不能把两组相加成更大训练样本。39条长期低位台账另完成路径复核，30自然日到期2但合格模型样本0。

三、归因与可证伪假设
1. 23日宽度修复但22日低位4样本仅1只收红，提示“近均线放量”还需要行业/风格共振；未来先冻结板块强弱、再比较同模型T+1/2，不在本日按结果修改阈值。
2. 旧28只深筛池18只收红，同时18只盘中不利观察≤-5%，说明收盘好看可以伴随深回撤；未来检验“开盘后承接确认”能否降低MAE，必须补齐分钟OHLC和触发顺序才能评估可执行性。
3. 龙虎榜天娱/埃斯顿/歌尔的同向组与慈文/海洋王/风语筑的高位背离组作为新前推对照；席位净买不是资金身份或持仓连续性的证明。不同涨跌幅制度、长假样本与v1/v2隔离。
4. 双环30自然日末转正但中途收破初始失效并有-14.023%不利观察，提示终点收益掩盖路径风险。今后保留“曾失效”标签，不能因为反弹把失败样本改成成功。
以上均为待验证假设，当前有效规则不变。下一次先补26日新成熟T+2，再持续积累独立交易日期；没有达到样本外门槛，不宣传可靠高胜率模型。

四、证据与交付修复
发现最新仓库的research.json、volume_price_samples.json存在不可解码字节，已从上一可读提交恢复111份历史报告和18条量价档案，并按独立原文件恢复23日量价报告及两个记录。所有旧报告/原始推荐/既有回执保持不变，旧17条缺原报告记录仍显式显示report_missing，不假装补齐。修复依据和哈希在本轮evidence的archive_recovery。缺少调度系统内部日志，不能把这次文件损坏直接认定为五个定时任务漏跑的唯一原因。
'''
    jointbody=f'''{intro}
本联合仅为执行编排摘要，不替代研究全文。低位独立报告{IDS['low_position']}：39条全部核验、30自然日到期2、合格30日模型0；龙虎榜独立报告{IDS['dragon_tiger']}：98理由行/78股票，8只精核买卖席位、33只上一观察组验证。两份报告及对应真实回执均在同一原子提交。
量价同日完整报告{IDS['volume_price']}复用原文，未重复出样本；其28只前池验证与复盘关联去重。联合report_type=execution_summary、eligible_for_integrated_research=false；两个成员各自为完整研究。缺盘口/订单成交、20日空间基准和部分公告证据逐项保留，以空仓/待核验处理，不填造字段。
'''
    bodies={'market_review':market_body,'low_position':lowbody,'dragon_tiger':dragonbody,'limitup_single':limitbody,'learning_review':learnbody,'low_dragon':jointbody}
    titles={'market_review':'每日复盘｜10月23日强修复、28只旧池验证与反例','low_position':'低位启动30天｜39条复核与首批30自然日到期','dragon_tiger':'龙虎榜｜8只席位逐项核对与33只旧组验证','limitup_single':'独立打板｜10月23日补研，空仓与复市准备','learning_review':'每日学习复核｜22条成熟T+2、7个日期，规则不变','low_dragon':'低位＋龙虎榜｜10月23日两模块完成摘要'}
    summaries={'market_review':'全A5573→广泛120→深筛28；旧池28/28日线复核，中位+3.413%，18只盘中不利≤-5%；正式新推荐0。',
      'low_position':'39条/38股全路径核验；30自然日到期2条但原快照不合格，模型成熟N=0；不删失败样本。',
      'dragon_tiger':'98理由行/78股票；8只买五卖五同期间核对及同花顺摘要交叉，旧名单33/33验证；候选0。',
      'limitup_single':'v2无合格候选；保留6板高位分歧、制度分组与空间/晋级缺项；旧600592未入场状态不变。',
      'learning_review':'31条逐项评估，22条成熟T+2、9条回溯排除；独立日期7，未达36条/20日门槛，未修改规则。',
      'low_dragon':'低位和龙虎榜两份完整研究与独立回执已归档；联合仅编排摘要。'}
    reports=[]
    for task,body in bodies.items():
        sources=list(common_sources)
        if task=='dragon_tiger':sources += [raw['other_sources']['lhb_details']['source'],'https://data.10jqka.com.cn/market/longhu/date/2026-10-23/']+[x['source'] for x in su['seat_queries']]
        reports.append({'id':IDS[task],'date':T,'market_date':T,'task_id':task,'track':task if task in ('low_position','dragon_tiger') else 'market_review',
                        'run_id':task.replace('_','-')+'-20261023-manual-completion-v1',
                        'title':titles[task],'summary':summaries[task],'body':body.strip(),'sources':dedup(sources),
                        'report_type':'execution_summary' if task=='low_dragon' else 'full_daily_research',
                        'eligible_for_integrated_research':task in ('market_review','low_position','dragon_tiger'),
                        'analysis_completed':True,'status':'completed','published_at':stamp,'recorded_at':stamp,
                        'data_cutoff_at':T+'T15:00:00+08:00','provenance':'retrospective_close_research_with_prospective_hypotheses',
                        'research_rule_version':'limitup_single_v2' if task=='limitup_single' else '20261023_catchup_existing_rules',
                        'candidate_count':0,'recommendation_ids':[],'evidence_file':EV,
                        'codes':[x['code'] for x in selected] if task=='dragon_tiger' else [x['code'] for x in lv] if task=='low_position' else [x['code'] for x in deep] if task=='market_review' else [],
                        'planned_entry_date':D,'earliest_legal_exit_date_if_bought':EXIT})
    research['items'].extend(reports)
    for task in IDS:
        rid=task.replace('_','-')+'-20261023-manual-completion-v1'
        runs['items'].append({'id':rid+'-completed','run_id':rid,'task_id':task,'date':T,'trigger':'manual',
                              'started_at':started,'recorded_at':stamp,'completed_at':stamp,'status':'completed',
                              'summary':summaries.get(task,'恢复并复核同日原量价完整报告、28只前池验证及全部旧历史；不重复候选。'),
                              'report_ids':[IDS[task]],'recommendation_ids':[],'analysis_completed':True,
                              'delivery_status':'repository_prepared_not_yet_verified','sources':[EV]})
    # The catalog retains its original watch choices and all historical reasons.
    lowby=defaultdict(list)
    for x in lv:lowby[x['code']].append(x)
    learnby={x['code']:x for x in learn['evaluations'] if x['status']=='observed'}
    changed_catalog=[]
    for stock in catalog['items']:
        c=stock['code']
        if c not in lowby and c not in learnby:continue
        bs=daily[c]['bars'];close=bs[-1]['close'];links=[IDS['low_position']] if c in lowby else [IDS['learning_review']]
        facts=f'10月23日未复权收盘{close}；'
        if c in lowby:facts += '；'.join(f"{x['reference_date']}原样本参考至今{x['close_return_pct']}%，曾收破初始失效={x['ever_verified_close_below_original_invalid']}" for x in lowby[c])
        else:facts += '已按原信号日与交易日历追加成熟节点，价格代理不证明原触发/成交。'
        linked_report=next(r for r in reports if r['id']==links[0])
        linked_report['body'] += f"\n\n研究自选关联：{stock['name']}（{c}）。{facts}"
        stock.setdefault('history',[]).append({'id':f'research-stock-{c}-20261023-validation','date':T,'recorded_at':stamp,
            'title':'10月23日原样本价格路径复核','reason':'追加已留存原样本的价格事实及失效证据，原研究理由和条件保持冻结。',
            'evidence_status':'unadjusted_daily_price_observation_not_fill','fact_note':facts,
            'validation':['继续原自然日/交易日节点；未成熟不提前评估。','跨任务同一价格样本不重复计策略成绩。'],
            'risk':'日线不能证明逐笔成交、止损次序或席位身份；不得把原样本反弹视为新入场指令。',
            'report_ids':links,'sources':[daily[c]['source'],EV]})
        changed_catalog.append(c)
    catalog['updated_at']=stamp
    lh=raw['other_sources']['lhb_details']['payload']['result']['data']
    evidence={'market_date':T,'actual_started_at_utc':started,'actual_completed_at':stamp,'planned_next_session':D,'earliest_exit_if_bought':EXIT,
      'scope':'manual_catchup_no_backdated_trading_signals','market_scan_source':'docs/research/low-dragon-2026-10-23-market-scan.json',
      'market_scan_retrieved_at':scan['retrieved_at_utc'],'coverage':scan['coverage'],'index_quotes':raw['other_sources']['index_quotes'],
      'daily_histories':daily,'daily_collected_at':raw['retrieved_at_utc'],'supplement_collected_at':su['retrieved_at_utc'],
      'daily_volume_units':'Tencent provider lots; do not mix with Sina shares without conversion',
      'recomputed_broad_pool':de['broad_recomputed'],'deep_pool':deep,'repeat_audit':de['repeat_audit'],
      'previous_whole_pool':previous,'previous_minute_checkpoints':minute_checkpoints,
      'raw_minute_price_points':su['minute_price_points'],'minute_errors':su['minute_errors'],
      'low_validations':lv,'low_summary':de['low_summary'],'low_model_statistics':modelstats,
      'dragon_raw_reason_rows':lh,'dragon_raw_seat_queries':su['seat_queries'],'dragon_selected':selected,
      'dragon_previous_validations':dv,'dragon_ths_summary_rows':thsrows,'dragon_ths_summary_crosschecks':cross,
      'learning_snapshot_id':learn['id'],'learning_proxy_statistics':learningstats,'research_stock_updates':changed_catalog,
      'archive_recovery':{'last_readable_base':'7a0eb47b508b93a7d007459a4bd080eed899aed0',
        'damaged_commit':'c6dbaffcb94b1b1a99172736c5ead983b5099c4b',
        'damaged_blobs':{'research.json':'7347bea7433eca32531dc5213bd67a7d127e843f','volume_price_samples.json':'a6073ab702c352403145055e2a3bfa8cefaf9fd5'},
        'preserved_historical_reports':111,'preserved_historical_volume_records':18,
        'same_day_report_recovered_from':'docs/research/volume-price-20261023-close-v1.json',
        'same_day_volume_records_recovered_from':'docs/research/volume-price-20261023-close-evidence.json',
        'root_cause_of_scheduler_miss':'not_established_by_available_logs'},
      'limitations':['No verified orders/fills, full minute OHLC or Level2',
        'No complete prior20-session board-height baseline or ordinary-mainboard promotion denominators',
        'New trade candidates withheld pending announcement/trading-status checks',
        'Mature historical low-position observations with unverified original snapshots excluded from model statistics',
        'Original 17 historical missing-report markers remain unresolved and visible']}
    (ROOT/EV).write_bytes(gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    for f,v in [('research',research),('task_runs',runs),('recommendations',recs),('learning',learning),('low_position_samples',low),('research_stocks',catalog)]:save('backend/data/'+f+'.json',v)
    save('app/src/main/assets/research_stocks.json',catalog)
    doc='# 2026年10月23日五项任务补齐\n\n实际完成：'+stamp+'。只补研究及可核验观察，不回填盘中推荐。\n\n'
    for r in reports:
        doc += '## '+r['title']+'\n\n'+r['body']+'\n\n来源：\n\n'+'\n'.join('- '+x for x in r['sources'])+'\n\n'
    original=next(r for r in research['items'] if r['id']==IDS['volume_price'])
    doc+='## 复用的同日量价报告\n\n'+original['body']+'\n\n原报告ID：'+original['id']+'；原文保持不变。\n'
    (ROOT/'docs/research/completion-20261023.md').write_text(doc)
    print(json.dumps({'reports_added':len(reports),'completed_receipts_added':len(IDS),'low_observations_added':len(lv),
                      'recommendation_results_added':len(recs['items']),'new_recommendations':0,'research_stock_histories_added':len(changed_catalog),
                      'minute_previous_complete':sum(x['point_count']>0 for x in minute_checkpoints),'recorded_at':stamp},ensure_ascii=False))

if __name__=='__main__':main()
