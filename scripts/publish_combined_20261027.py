"""Prepare one append-only publication after independent, dated full research.

Not an autonomous stock picker: the explicit research findings below accompany
recomputed evidence. No orders, hypothetical fills or trained weights are made.
"""
from collections import Counter
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from statistics import mean
import copy,gzip,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from learning_loop import is_session,nth_session_after
from prepare_completion_20261023 import pct,stats,snapshot
T='2026-10-27';D='2026-10-28';EXIT='2026-10-29';TAG='20261027'
START='2026-10-27T09:41:46+00:00'
EV='docs/research/combined-pair-20261027-evidence.json.gz'
IDS={'market_review':'market-review-20261027-close-v1','volume_price':'volume-price-20261027-close-v1','low_position':'low-position-20261027-close-v1','dragon_tiger':'dragon-tiger-20261027-close-v1','limitup_single':'limitup-single-20261027-close-v2','combined_pair':'combined-pair-20261027-close-v1'}
SECTORS=dict(zip(['300961','301083','002196','300307','002724','002820','300949','000888','002823','600826','001219','300631','605333','600626','603370','002249','600785','603528','002284','600865','000678','002187','603489','603350','001318','603037','601086','300549'],['环保水务','智能装备','汽车电机','纺织机械/机器人','专业照明','食品','景观/数字创意','旅游','汽车零部件','会展服务','食品','膜材料/环保','汽车线束','汽车材料','电机铁芯','电机/机器人','零售','智能交通','汽车制动','零售','轴承/机器人','零售','电驱动','电机','乳品','汽车零部件','零售','精密模具']))
NEW_LOW={'002823':('汽车零部件',12.25,'120日区间20.526%、60日区间62.238%，收盘越过原20日高点13.10并收复MA60，首次换手板后等待回踩检验。','Q3及累计利润下降，前三季已计提减值3954.49万元；员工持股锁定期届满后可择机出售，不能等同已减持。'), '000888':('旅游',9.14,'120日区间44.343%属低中位，放量突破原20日高点9.56且收复MA60，研究高量首次突破后的承接。','RVOL5约9.12倍存在次日失速风险；可核半年报营收与现金流同比下降，三季报尚未取得，旅游季节性不能当作新催化事实。')}
def load(p):return json.loads((ROOT/p).read_text())
def save(p,x):
 p=ROOT/p;temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temp.replace(p)
def fmt(x,n=3):return 'N/A' if x is None else str(round(x,n)) if isinstance(x,(int,float)) and not isinstance(x,bool) else str(x)
def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(fmt(x) for x in row)+'|' for row in rows])
def main():
 research=load('backend/data/research.json');runs=load('backend/data/task_runs.json');low=load('backend/data/low_position_samples.json');vp=load('backend/data/volume_price_samples.json');recs=load('backend/data/recommendations.json');catalog=load('backend/data/research_stocks.json')
 for task in IDS:
  if task!='market_review' and any(r.get('task_id')==task and r['date']==T and r.get('report_type') in ('full_daily_research','full_trading_research') for r in research['items']):raise RuntimeError('Same-T full module exists: '+task)
 market_report=next(r for r in research['items'] if r['id']==IDS['market_review'])
 assert market_report.get('eligible_for_integrated_research') is True
 assert any(r.get('status')=='completed' and r.get('report_ids')==[IDS['market_review']] for r in runs['items'])
 raw=load('tmp/combined-20261027-raw.json');initial_failures={k:{c:r.get('error') for c,r in raw[k].items() if not r.get('ok')} for k in ('daily_histories','seat_queries','minute_price_points','limit_up_pools')}
 ext=load('tmp/combined-20261027-extension.json')
 for kind in ('daily_histories','seat_queries','minute_price_points','limit_up_pools'):raw[kind].update(ext.get(kind,{}))
 prior_path='docs/research/combined-pair-20261026-evidence.json.gz'
 prior=json.loads(gzip.decompress((ROOT/prior_path).read_bytes()))
 for day in ('2026-10-23','2026-10-26'):
  raw['limit_up_pools'][day]={**copy.deepcopy(prior['limit_up_pools'][day]),'reused_from':prior_path}
 de=load('tmp/combined-20261027-derived.json');cum=load('tmp/combined-20261027-statistics.json');sup=load('tmp/combined-20261027-supplement.json');files=load('tmp/combined-20261027-official-files.json');official=load('tmp/combined-20261027-announcements.json');extra=load('tmp/combined-20261027-extra-announcements.json');ths=load('tmp/combined-20261027-ths.json');profiles=load('tmp/combined-20261027-seat-profiles.json');upper=load('tmp/combined-20261027-quote-upper-check.json');market=load('docs/research/market-review-2026-10-27-evidence.json')
 assert de['crosscheck']['recomputed_broad']==120 and de['crosscheck']['deep']==28 and not de['crosscheck']['ohlc_mismatches']
 assert len(de['low_validations'])==42 and de['low_summary']['all_paths_complete']
 assert all(s['seat_reconciliation']['matched'] and s['ths_close_match'] for s in de['dragon_selected'])
 assert de['progression_main_10pct']['1_to_2']['advanced']==8
 now=datetime.now(timezone.utc);stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
 daily={c:r['bars'] for c,r in raw['daily_histories'].items() if r.get('ok')};lookup={s['code']:s for s in de['broad_recomputed']}
 for s in de['deep_recomputed']:
  s.update(sector_research_label=SECTORS[s['code']],signal_frozen_at=stamp,rule_version='volume_price_close_v4',is_recommendation=False)
 def features(rows):
  return table(['代码/名称','板块','收盘/涨跌%','RVOL5/10/20','换手%/较T26变化pp','20/60/120日位置%','MA5/10/20/60','CLV/14时后%'],[[s['code']+' '+s['name'],SECTORS.get(s['code'],'其他研究分组'),fmt(s['close'])+'/'+fmt(s['daily_change_pct']),'/'.join(fmt(s['rvol'][str(n)]) for n in (5,10,20)),fmt(s['turnover_pct'])+'/'+fmt(s['turnover_change_pct_points']),'/'.join(fmt(s['range_position_pct'][str(n)]) for n in (20,60,120)),'/'.join(fmt(s['ma'][str(n)]) for n in (5,10,20,60)),fmt(s['clv'])+'/'+fmt(s['tail_1400_close_pct'])] for s in rows])
 def pool_validation(rows):return table(['代码/名称','开盘观察%','最高观察%','最低观察%','收盘观察%'],[[r['code']+' '+r['name'],r.get('open_pct'),r.get('mfe_pct'),r.get('mae_pct'),r.get('close_pct')] for r in rows])
 common=f'研究交易日T={T}，收盘行情截止北京时间15:00；实际分析完成{stamp}。计划交易/观察日D={D}；若D真实买入，最早{EXIT}可卖。所有新增条件在后续结果未知时冻结；参考收盘不是成交价。'
 definitions='RVOL5/10/20为T完整成交量除以前5/10/20个已完成交易日均量，分母不含T；不是盘中同一时点量比。MA与20/60/120日区间含T，足额历史才计算；与复盘原扫描前T均线字段分开，不重写原样本。CLV=(收盘-最低)/(最高-最低)，高低相同记N/A。换手变化使用T26已公开冻结新浪全A快照与T27同口径字段相减；缺完整历史换手曲线。分钟资料只是有日期的价格点与累计量额，不能证明分钟OHLC、9:25竞价、撤单、逐笔、排队成交或同一分钟内先后。相对前收的最高/最低观察与持仓MFE/MAE分开。'
 previous=de['previous_whole_pool_summary']
 previous_text=f"先验证10月26日冻结的完整28只，28/28取得原始日线并核对锚价；{previous['positive_n']}只收红，收盘观察均值{previous['mean_pct']}%、中位{previous['median_pct']}%，平均最高观察+{previous['mean_mfe_pct']}%、平均最低观察{previous['mean_mae_pct']}%，{previous['mae_le_minus5_n']}只最低相对前收≤-5%。市场复盘与量价关联同一原cohort volume-price-20261026-close-v1-cohort，不能跨任务重复计数。两只涨停例子不能替代整个池的验证。原综合组和D27打板均为现金，候选/成交为0，不把研究池涨跌记为账户盈亏。"
 previous_table=pool_validation(de['previous_whole_pool'])
 version_rows=[]
 for rule,v in cum['vp_by_rule_version'].items():
  a=v['horizons']['1'];b=v['horizons']['2'];version_rows.append([rule,v['frozen_sample_count'],v['independent_dates'],a['n'],fmt(a['mean_pct'])+'/'+fmt(a['median_pct']),a['mean_mae_pct'],b['n'],fmt(b['mean_pct'])+'/'+fmt(b['median_pct'])])
 stats_text='10个有明确id的冻结cohort共257条日期-股票样本，256个原收盘锚可与未复权日线一致；10月8日1条原价缺失仍保留排除，不补造。无id的9月29/30假期回溯摘要另存，不混普通隔夜。v4只有6个独立信号日期，168条不是168个独立交易日。所有1/2/3/5/10/20/30交易日节点、失败与未成熟pending保存到证据；按原冻结标签、位置和制度分层的描述统计同时保存，旧标签缺失保持unknown，不按后续结果补标签。价格基准为信号日收盘及同日期上证指数，尚无可验证成交，费用、最低佣金、数量和滑点未校准，20bp仅旧占位，不算可执行净收益。策略胜率、净收益均值/中位、盈亏比、退出质量均N/A；9:50/14:40/盘后组及v1/v2分别跟踪，不合并成胜率。'
 stats_table=table(['冻结版本','样本数','独立日期','T+1可观察N','T+1均值/中位%','T+1平均最低%','T+2 N','T+2均值/中位%'],version_rows)
 # A consistent three-day ordinary-main proxy; do not mix it with media/all-board counts.
 market_days=[]
 for day,path in [('2026-10-23','docs/research/low-dragon-2026-10-23-market-scan.json'),('2026-10-26','docs/research/market-review-2026-10-26-evidence.json'),(T,'docs/research/market-review-2026-10-27-evidence.json')]:
  m=load(path)['market'];market_days.append([day,m['standard_non_st_limit_up_sealed'],m['standard_non_st_failed_boards'],m['standard_non_st_limit_down'],round(m['standard_non_st_limit_up_sealed']/m['standard_non_st_limit_up_touched']*100,3),round(m['amount_yuan_full_scan']/1e8,2),m['advance'],m['decline']])
 emotion=table(['交易日','主板阈值封板','触板未封代理','跌停代理','代理封板率%','全A成交亿元','上涨','下跌'],market_days)
 emotion+='\n\n该表只比较新浪正常普通主板约10%阈值代理，非全制度精确涨跌停，也不含完整历史证券状态；创业/科创20%、北交所30%、风险警示和无上限分开。T27财联社11:48午盘46涨停/13连板/13未遂/封板率78%仅作午盘对照，绝不冒充收盘；收盘全制度精确炸板数N/A。全A成交口径含扫描覆盖股票，不能与只含沪深的媒体成交额混称。T23强修复→T26分歧→T27退潮加速，是综合推断：4921只下跌、成长指数显著走弱、首板后晋级与断板反馈恶化；正面是零售/食品局部高标仍强，不能仅凭指数跌或最高板上升定性。'
 ladder=de['board_ladder'][T]['layers']
 ladder_text=table(['普通主板层级','家数','代码与名称'],[[k,len(v),'、'.join(r['code']+r['name'] for r in v)] for k,v in ladder.items()])
 ladder_text+='\n\n东财原始池41条保持；兰生600826、百大600865未列，复查仍缺。两只由腾讯当日涨停上限字段47、带T27日期的报价、未复权日线和新浪收盘共同核验后补入独立修正表，合计43条（普通主板38、20%制度5），不是改写原池。兰生前日已首板，今为二板；百大为首板，3天2板不当2连板。修正后的普通主板可见最高为上海九百600838五板，次高襄阳000678/赛福天603028/多伦603528四板，三板断层。赛福天全天高低价相同为一字，CLV记N/A；青岛有开板记录，不能把涨停开盘等同全天一字或普通成交。封单/撤单与队列未接入，主线机器人可见4板、消费可见5板，均非已验证优势。'
 progression=table(['层级','T26原分母','晋级','断板','停牌/缺失','晋级%'],[[k,v['prior_full_denominator'],v['advanced'],v['broken'],v['missing'],v['verified_advancement_pct']] for k,v in de['progression_main_10pct'].items()])
 denominator_rows=[]
 for k,v in de['progression_main_10pct'].items():
  denominator_rows += [[k,r['code']+' '+r['name'],r['status'],r['T_close']] for r in v['rows']]
 denominator_table=table(['原层级','T26冻结股票','T27验证','T27收盘'],denominator_rows)
 progression+='\n\n分母逐股取自T26已经真实发布的完整池，价格逐股复核，不从T27成功名单倒推。遗漏兰生补证后1进2为8/33而非7/33；2进3为0/8、3进4为3/5、4进5为1/1，无分母的更高层N/A。媒体整体晋级率不替代分层分母。'
 space=cum['twenty_prior_sessions_space_reference']
 space_text=f"辅助空间窗口为T之前20个实际交易日（{space['requested_sessions'][0]}至{space['requested_sessions'][-1]}），本轮取得14池，再复用T26真实冻结的9月29日池，合计15/20；仍缺{','.join(space['missing_session_pools'])}。可见局部高点11板，新华传媒600825在10月16日15.16元与原始日线核验；完整20日最高与情绪周期起点/周期最高均N/A。不把五板高度上升称空间已经打开，也不把反包或N天M板当连续M板。"
 fact_notes=[
 {'code':'600826','keys':['600826-q3'],'fact':'未经审计Q3营收6.3696亿元(+35.14%)、归母1.4030亿元(+12.97%)、扣非8689.82万元(+55.59%)；前三季营收11.7316亿元(+14.49%)、归母1.5768亿元(-12.94%)、扣非1.1456亿元(-2.30%)、经营现金流1.5046亿元(-52.86%)。单季改善和累计现金流走弱并存，不归因当日上涨。'},
 {'code':'002823','keys':['002823-q3','002823-impairment','002823-employee-unlock'],'fact':'未经审计前三季营收24.4179亿元(+12.25%)、归母1.5744亿元(-12.08%)、扣非1.4150亿元(-23.05%)、经营现金流3.2916亿元(-6.47%)；Q3归母5274.98万元(-20.00%)。前三季减值3954.49万元已在利润中反映，不能再从净利润重复扣除。员工持股125.22万股的锁定期10月20日届满，计划可择机出售，不等同已卖出。'},
 {'code':'000888','keys':['000888-h1-summary'],'fact':'可核2026半年报营收4.4281亿元(-3.12%)、归母1.2258亿元(+1.07%)、扣非1.2242亿元(+2.60%)、经营现金流1.0984亿元(-29.54%)。半年报未审计，三季报未取得，不用旧半年报伪称三季业绩或新旅游催化。'},
 {'code':'300961','keys':['300961-q3'],'fact':'未经审计前三季营收2.3253亿元(-12.10%)、归母-8387.16万元、扣非-5017.74万元、经营现金流1337.22万元(-62.03%)；Q3归母-2724.82万元。收涨11.43%不能证明盈利已反转。'},
 {'code':'301083','keys':['301083-q3'],'fact':'未经审计前三季营收2.6919亿元(+5.86%)、归母31.89万元(-98.99%)、扣非-419.67万元、经营现金流1433.40万元(-50.17%)；Q3归母-509.46万元。尾盘价格推进与经营反证并存。'},
 {'code':'001318','keys':['001318-q3'],'fact':'实际于T27本轮取得、PDF路径日期为10月28日的未经审计三季报：前三季营收3.2715亿元(-8.13%)、归母6492.41万元(-25.71%)、经营现金流6778.99万元(-30.04%)；Q3归母1855.00万元(-32.74%)。只用于本次盘后D28预案，不回填T27盘中可得，也不假定精确首次披露时刻。'},
 {'code':'603028','keys':['603028-risk'],'fact':'风险公告提示短期涨幅和非理性炒作风险；披露半年归母亏损3243.77万元，因最近12个月亏损，负市盈率不具备与行业正市盈率直接比较的意义。'},
 {'code':'603528','keys':['603528-risk'],'fact':'风险公告披露10月22日至26日累计涨幅33.40%；半年归母亏损3626.03万元。不涉及人形机器人核心本体研发生产，机器人业务收入/利润占比极小，预计2026年不构成重大业绩影响；不把题材标签视为主营事实。'}]
 official_text=table(['准确代码','公告原文核验与边界'],[[r['code'],r['fact']] for r in fact_notes])
 official_text+='\n\n上述财务数字经PDF原始表格视觉核对；公告检索按准确代码过滤并保留原始查询。22个本月查询加3个扩展查询均无下一页，不等同全证券风险、减持、解禁或停复牌清单。峨眉山本月简称查询为空后，以“峨眉山A”扩展8月以来范围取得原半年报，不能把空搜索当无风险。公开可得时间以本次真实HTTP取证时刻为上界，PDF日期不是精确首次公布时刻。'
 new_low=[]
 for c,(sector,invalid,reason,risk) in NEW_LOW.items():
  s=lookup[c];keys=['002823-q3','002823-impairment','002823-employee-unlock'] if c=='002823' else ['000888-h1-summary']
  urls=[s['source'],EV]+[files[k]['source'] for k in keys]
  new_low.append({'id':f'low-position-{TAG}-{c}','date':T,'recorded_at':stamp,'code':c,'name':s['name'],'sector':sector,'primary_model':'低中位箱体突破','research_rule_version':'low_position_30d_v1','feature_calculation_version':'unadjusted_MA_including_T_v3','day0_close':s['close'],'day0_change_pct':s['daily_change_pct'],'day0_amount_yi':s['amount_yi'],'day0_turnover_pct':s['turnover_pct'],'day0_rvol20':s['rvol']['20'],'day0_clv':s['clv'],'day0_range_position_pct':s['range_position_pct'],'day0_moving_averages':s['ma'],'invalid_close_below':invalid,'initial_invalidation_basis':'未来收盘跌破T信号日低点；原位冻结，不冒充当天可卖或保证止损成交','snapshot':copy.deepcopy(s),'reason':reason,'risk':risk,'original_snapshot_provenance':'contemporaneous_after_close_research_sample_not_recommendation','original_snapshot_verified':True,'eligible_for_model_statistics':True,'statistical_scope':'future_price_observation_only_not_executable_trade_return','is_recommendation':False,'default_watch':False,'capital_identity':'unknown','lhb_today':any(r['SECURITY_CODE']==c for r in raw['lhb_lists'][T]['payload']['result']['data']),'announcement_scope':'bounded official exact-code queries; security-master, all insider sales/unlocks and actual first release timestamps incomplete','sources':urls,'report_ids':[IDS['low_position']],'observations':[]})
 new_low_table=features([lookup[c] for c in NEW_LOW])
 new_low_text='本轮新增2条30天研究样本，不为3—8只目标硬凑；它们不进入综合两只或打板一只，也不自动加入本机自选。两只均普通主板首次换手板，长期区间较低但已经达到20日高位，不能称绝对底部或开盘即买。\n\n'+new_low_table
 for s in new_low:new_low_text+=f"\n\n{s['name']}{s['code']}：模型{s['primary_model']}。{s['reason']} 冻结收盘参考{s['day0_close']}，初始收盘失效{s['invalid_close_below']}，依据为T低点；T27是否上榜={s['lhb_today']}，未获得可确认的账户资金身份。{s['risk']} 观察D28缩量回踩前20日突破位/MA60的承接，只有后来实际价格证据才追加触发/失效，不因短期涨跌删除或移动原位。"
 low_rows=[]
 for v in de['low_validations']:
  low_rows.append([v['code']+' '+v['name'],v['reference_date'],v['reference_close'],v['price_observation']['close'],v['close_return_pct'],v['path_mfe_pct'],v['path_mae_pct'],v['original_invalid_close_below'],v['ever_verified_close_below_original_invalid'],v['elapsed_natural_days'],v['elapsed_trading_sessions']])
 low_table=table(['代码/名称','原入选日','原收盘','T收盘','当前观察%','路径最高%','路径最低%','原失效','曾收破','自然日','交易日'],low_rows)
 low_model_table=table(['原模型','保留N','原快照可验证N','成熟30自然日N','成熟均值/中位%','曾破失效N'],[[r['model'],r['all_n'],r['eligible_n'],r['mature_30d_eligible_n'],fmt(r['frozen_30d_close_statistics']['mean_pct'])+'/'+fmt(r['frozen_30d_close_statistics']['median_pct']),r['ever_original_invalidation_broken_n']] for r in de['low_model_statistics']])
 low_prev='42条旧样本、41个代码全路径验证，按原id保留吉林化纤等不同入选日。第1/3/5/10/15/20/30自然日节点，使用不晚于该目标日的最近交易日，另列5/10/20/30交易日节点；原价、失效和历史观察均不重写。9月23日双环传动002472、宝信软件600845已满30自然日，但原快照未验证，30日节点仍用10月23日，合格成熟30自然日模型N=0；成熟30交易日N=0。所有模型30日胜率、平均/中位净收益、盈亏比、10%/20%占比目前N/A，不能把不同年龄当前收益混为30天成功率。'
 low_prev+='\n\n10月26日新3条的首个次日验证：顺景科技603007收4.65、较原4.59为+1.307%，CLV仅0.4386且未收复MA60；甘源食品002991收38.66、较39.21为-1.403%，CLV0.0316、收近低位，分时接口501未取得完整时点；青岛食品001219收14.98、较13.62为+9.985%，涨停开盘后有低于开盘的价格，日线不证明排队成交或先后。三条均未收破原4.15/38.00/13.08失效位，仍是价格观察，不写成1/3成功或赚到涨停。'
 selected={s['code']:s for s in de['dragon_selected']}
 dragon_table=table(['代码/名称','披露期','收盘','买/卖/净万元','机构净万元','股通净万元','买1/卖1集中%','MA20乖离%','CLV'],[[s['code']+' '+s['name'],s['period'],s['close'],'/'.join(fmt(s[k]/1e4) for k in ('buy_cny','sell_cny','net_cny')),s['institution_net_wan'],s['stock_connect_net_wan'],fmt(s['buy_concentration_top1_pct'])+'/'+fmt(s['sell_concentration_top1_pct']),s['price_structure']['distance_ma20_pct'],s['price_structure']['clv']] for s in de['dragon_selected']])
 dragon_conditions={
 '000678':('当前4板/计划5板，机器人高标待确认','D28 9:25后、9:45/10:30核验；只有缩量回踩不失14.68并重新推进、同伴多伦科技603528与赛福天603028不现系统性跌停才继续观察。高开后爆量不推进、一字无普通成交或失14.68放弃，机构/股通买入不豁免高位风险。'),
 '600826':('当前2板/计划3板，会展/消费跟随待确认','D28观察9.04是否能重新获得承接，低点8.56为放弃边界；同伴新华百货600785、百大集团600865需同步。三日机构净卖不等于T27当日卖，无法验证回踩或普通成交则只记观察。'),
 '002249':('首板/计划2板，电机链反包跟随待确认','D28回踩不失6.84、重新放量推进7.70，并核验方正电机002196、凯中精密002823同步；板块掉队、连续开板或高开后不能推进直接放弃，股通净买不等于已验证锁仓。'),
 '002724':('六板断后反包/当前首板，非低位首板','D28需守11.89并在13.09上方获得可核验回踩，同伴襄阳轴承000678、大洋电机002249同步；高乖离、反复开板、经营扣非亏损反证未消除时不升级交易。'),
 '603089':('3进4失败反例，不抄跌停','D28先看是否脱离11.77弱势区，再看13.16原高压制，襄阳轴承000678与多伦科技603528只作情绪参照；低开无承接或持续跌停直接否决。日线高低不能证明能在跌停卖出。')}
 dragon_obs=[{'id':f'dragon-tiger-{TAG}-watch-{c}','date':T,'frozen_at':stamp,'planned_observation_date':D,'code':c,'name':selected[c]['name'],'reference_price':selected[c]['close'],'reference_price_at':T+'T15:00:00+08:00','board_regime':selected[c]['board_regime'],'selected_trade_id':selected[c]['selected_trade_id'],'disclosure_period':selected[c]['period'],'role':role,'condition':cond,'is_recommendation':False,'executed_trade':False,'research_rule_version':'dragon_tiger_original_contract','report_ids':[IDS['dragon_tiger']],'results':[]} for c,(role,cond) in dragon_conditions.items()]
 dragon_obs_table=table(['研究观察，不是交易推荐','角色','D28确认/放弃条件'],[[s['code']+' '+s['name'],s['role'],s['condition']] for s in dragon_obs])
 dragon_prev=table(['制度分组','T26披露池N','T27收盘均值%','中位%','收红N'],[[b,v['n'],v['mean_pct'],v['median_pct'],v['positive_n']] for b,v in de['dragon_previous_by_board'].items()])
 dragon_focus=pool_validation(de['dragon_previous_focused_eight'])
 # Formal decisions compare real alternatives independently of watchlists.
 comparisons=table(['真实备选/T27参考收盘','当前→计划板数/角色','支持','否决或未闭环'],[
 ['凯中精密002823 / 13.49','1→2 汽车零部件跟随待确认','低中位突破、收复MA60、换手成交','利润下降、员工计划可择机出售；次日承接未验，仅30天样本'],
 ['峨眉山Ａ000888 / 10.10','1→2 旅游独立性待确认','长期位置44%、20日突破、经营盈利','9倍相对量、现金流下降；独立旅游主线持续性未证'],
 ['兰生股份600826 / 9.04','2→3 会展消费跟随待确认','量价与尾盘推进，Q3单季改善','同周期三日机构净卖、累计净利/现金流下降，二进三梯队0/8'],
 ['广百股份002187 / 5.92','1→2 零售跟随待确认','消费局部强势、封板','市场宽度极弱、次日高开/队列流动性未知'],
 ['青岛食品001219 / 14.98','2→3 食品跟随待确认','上一低位样本突破后续强','当前20/60日顶部、涨停开盘有开板，已不是新低位；不追研究池涨幅'],
 ['襄阳轴承000678 / 16.01','4→5 机器人高标待确认','机构与股通同向净买','约39%MA20乖离，总榜净卖，接力不符合低位首/二板假设'],
 ['上海九百600838 / 13.31','5→6 消费高度参考','可见最高仍封板','高位相对缩量和官方风险提示，不能只因最高板入选']])
 risk_boundary=f'D28空仓，无新买入区间、失效位或止盈卡。若未来另有在结果未知时冻结的条件并于D28真实买入，最早D29（{EXIT}）09:30后可卖；强开/平开/弱开均按事前冻结的首个可证明可成交报价执行，不能事后选最高价。跌停、停牌或队列未成交保留敞口，不能保证止损成交。买入当日炸板不能当日止损，涨停浮盈不等于可退出利润。本次仍为模拟验证，不自动转实盘，不融资、不借款、不重仓追板。'
 repeat=de['repeat_audit']
 repeat_text=f"严格过去5/10个实际交易日都只核得3个原完整报告的代码池（10月22/23/26日），可得池交集8/28=28.571%，不是完整5/10日重复率；严格值N/A，未覆盖日期不填0。新正式推荐0，推荐重复率N/A。重复的襄阳、青岛等因本轮量价和风险证据重新比较，不因用户持仓、自选或降低重复率而自动进出。"
 # Keep newly frozen zero-outcome samples out of mature price statistics.
 model_inventory=copy.deepcopy(de['low_model_statistics'])
 box=next(r for r in model_inventory if r['model']=='低中位箱体突破');box['all_n']+=2;box['eligible_n']+=2
 low_model_table=table(['原模型','含新样本总N','原快照可验证N','成熟30自然日N','成熟均值/中位%','曾破失效N'],[[r['model'],r['all_n'],r['eligible_n'],r['mature_30d_eligible_n'],fmt(r['frozen_30d_close_statistics']['mean_pct'])+'/'+fmt(r['frozen_30d_close_statistics']['median_pct']),r['ever_original_invalidation_broken_n']] for r in model_inventory])
 profile_table=table(['公共营业部观察，不是账户身份','覆盖日期N','股票/披露期行N','能否确认持有周期/做T'],[[p['branch_name'],p['distinct_disclosure_dates'],p['observed_stock_period_rows'],'否，缺逐笔及真实持仓'] for p in sorted(profiles['profiles'],key=lambda p:(-p['distinct_disclosure_dates'],-p['observed_stock_period_rows']))[:10]])
 vp_findings='本轮典型5例：①凯中精密002823低中位突破且收复MA60，但利润/减值/员工计划反证使其只能入30天研究；②峨眉山Ａ000888高量突破后需检验回踩，9倍RVOL不是安全买点；③兰生股份600826收盘/尾盘推进，但3日机构净卖及累计现金流下降否定单因子追涨；④深水海纳300961尾盘推进，却有亏损扩大的财务反证、20%制度不得混主板；⑤奥雅股份300949收涨9.725%而14时后回落2.692%、CLV约0.610，属于上影和冲高回撤风险，不能以涨幅判真转强。'
 vp_findings+='\n\n六类结构逐项反馈：低位首次放量的凯中/峨眉山尚无次日承接；突破后缩量回踩需要D28以后才有前推证据；顺景603007放量试盘后冲高回落、甘源002991缩量回落收近低位，均尚未确认分歧转一致；林州002535/正裕603089跌停和CLV0为高位风险对照，不解释为确定出货账户；相对均量缩量上涨的上海九百RVOL5约0.919处五板，仍可能流动性脆弱，不能视为锁仓；放量下跌及缩量上涨的完整对照，按原冻结标签/位置保留失败，现无稳定净收益结论。'
 vp_findings+='\n\n下一项可证伪假设：H1低中位突破只有回踩缩量、不收破原失效且板块同步时，后续价格质量才可能优于单看RVOL；H2二进三断层下，新首板的隔夜退出质量可能比指数状态更差；H3机构/股通同向加高乖离并不保证次日承接。全部只是新观察假设，不改v4阈值、不机械打分、不回看调参；待跨日期滚动前推与样本外复核。'
 provider_note=f"首次请求中的48份日线、22组席位、54组分钟与3个涨停池出现403，原始失败保留。缩小并发后的48份日线、22组席位、54组分钟已成功补齐；两份旧涨停池复用已发布原证据，新T27池重新取得。额外38个旧低位代码分钟接口均501，保留原失败，不补造。最终{len(daily)}只未复权日线、54份带T27日期的价格点可用；缺9:25竞价、历史逐笔/完整分钟OHLC、队列成交、证券点时状态及完整历史换手曲线。失败不是停任务理由，当前接口可用不等于长期SLA。"
 common_boundary='APP只展示归档和前推统计，不内置大模型、自动权重训练或自动下单。本轮不修改活动策略、任务启停/时间、原推荐或失败样本；量化研究继续取消。独立学习复核启动快照仍截至T26，T27新增结果供后续复核引用，不将读回接口当成新学习已完成。'
 volume_body='\n\n'.join([common,'结论：完成独立volume_price全池研究与验证，正式交易候选0；保留28条新冻结量价研究样本。', '一、全A入口与量价定义\n重新取得5576条原始、5573只有效行情，复用同T完整市场复盘120只广泛池并独立重算，120/120 OHLC跨源一致；深筛28只，覆盖至少十个研究板块，不以扫描启发式分数冒充已验证因子。\n'+definitions,'二、先验证上一整个28只\n'+previous_text,previous_table,'三、本次28只完整冻结快照\n'+features(de['deep_recomputed']),'四、3—5个典型样本、反例与下一假设\n'+vp_findings,'五、累计版本与前推边界\n'+stats_table,stats_text,'六、六个研究时间窗口\n9:30—9:45、9:45—10:30、10:30—11:30、13:00—14:00、14:00—14:30、14:30—15:00分别留研究窗口；全部28只新样本与上一28只保存可得9:30/9:45/9:50/10:30/午盘/14:00/14:30/14:40/收盘价格点。无当时真实冻结买点/分钟OHLC/成交凭据，窗口策略N、净收益和较优卖出时段均N/A，不从高低反推9:50或14:40入场、先止损或先止盈。T27盘后冻结若D28入场最早D29可卖。','七、公告反证\n'+official_text,'八、来源失败和缺项\n'+provider_note,common_boundary])
 low_body='\n\n'.join([common,'结论：独立low_position完整研究；新增2条30天观察，42条旧样本不删除，总数44条。正式短线交易候选0。','一、全市场入口与筛选反例\n5573有效行情→120广泛独立重算→28深筛，另复核42条全部旧样本。ST/退市风险不进新样本；宏明301682虽长期位置低但20%涨幅、未收MA60与前20日高点，亚太002284/大明603376未有效突破旧20日高，华新603370单日量比推进不及入选两只且历史限售流通风险需另核；达瑞300976、苏奥300507上影和弱CLV、安乃达603350尾盘回落，不能为数量硬凑。不是把有限自选当全A。\n'+definitions,'二、新增样本与固定失效\n'+new_low_text,'三、既有样本全量跟踪及到期复盘\n'+low_prev,low_table,'四、原模型阶段统计\n'+low_model_table+'\n新增2条只进入样本库存，不把入选当日0涨幅纳入前推成熟收益。', '五、量价研究与验证\n'+previous_text+'\n'+vp_findings+'\n所有原样本自然日和交易日里程碑、MFE/MAE、收盘路径最大回撤、首次收破原失效日期及T27可得时点单独保存在证据；旧低位38个分钟查询501，缺项标注而不推断触发。','六、公告与风险\n'+official_text,'七、下一验证\n对凯中冻结13.49/失效12.25、峨眉山冻结10.10/失效9.14，观察缩量回踩原20日突破位13.10/9.56是否重新推进；有收破、假突破和不可成交照样留下，原位不后移。30自然日与30交易日分别标成熟，均价/胜率样本不足仍N/A。'+risk_boundary,provider_note,common_boundary])
 dragon_body='\n\n'.join([common,'结论：完成独立dragon_tiger，5条条件研究观察、正式交易候选0。87条上榜原因行/77个代码（含多期与不同制度）；同花顺摘要85个股票-披露期行，原口径分别保留，不硬凑一致。','一、情绪、主线、高度与空间\n'+emotion,ladder_text,progression,space_text,'二、11只重点上榜股资金结构\n'+dragon_table,'按准确TRADE_ID、股票代码、日/连续三日原因匹配；买/卖前五与合并去重席位总额逐个复核，11/11与东财汇总、同花顺同周期收盘一致。青岛、兰生、九百、赛福天只有本次选中的多日口径，不写成T27单日机构买卖。买方/卖方集中度基于对应披露总额，不等于实际流通筹码控制。','襄阳000678机构+3015.446万元与股通+2875.055万元同向，但总榜净卖13046.24万元，39%乖离仍高；兰生600826三日机构-5491.685万元/股通+574.562万元和价格推进背离；正裕603089机构净卖2006.409万元、跌停/CLV0；林州002535机构净卖581.436万元、跌停；海洋王002724总榜净买13313.54万元却股通净卖2117.379万元，反包不自动代表低位接力；凡拓301313的高位冲高回落继续提供反例。无席位证据不认定游资/量化账户，不把榜上同名机构视为同一机构。','三、公共营业部画像更新\n'+profile_table+f"\nT26/T27共{len(profiles['profiles'])}个准确营业部代码/名称画像，{sum(p['observed_stock_period_rows'] for p in profiles['profiles'])}条股票-披露期观察，{sum(p['distinct_disclosure_dates']>1 for p in profiles['profiles'])}个跨两个披露日。另40条机构/股通通用标签不合并为账户。逐项保存首板/接力所处股票、同日披露期和已可得次日价格；首板/反包/趋势偏好、常见持有周期、次日兑现、做T/锁仓仍样本不足，不凭席位标签编出风格。多日披露与单日披露不得简单加总。",'四、先回测T26全部披露池71只\n'+dragon_prev+'\n表内各制度均为价格观察，不混成策略胜率。北交所部分只提供T27一根日线时，采用T26已归档CLOSE_PRICE作为明确锚价，标历史路径不可得；不猜盘中顺序或执行收益。',dragon_focus+'\n以上9只T26重点全部保留；5条原条件观察和其余4条重点不重算成新推荐。','五、5条D28研究观察卡\n'+dragon_obs_table+'\n参考收盘均为T27 15:00已观察价，非买入价；竞价、板块、承接与实时盘口全要二次核验，当前无Level-2/连续盯盘。D28一旦实际买入最早D29可卖，观察卡不证明成交。','六、分层统计与公告反证\n'+stats_table+'\n量价引用原VP cohort，仅交叉支持/反对，不重复计样本。席位组合×位置×板块×情绪×封板质量的可执行净收益、胜率、盈亏比、MAE与退出质量N/A；现有71只次日价格和新5条条件留档，失败/停牌/无法成交不剔除。',official_text,provider_note,common_boundary])
 limitup_body='\n\n'.join([common,'结论：10月28日空仓，无合格打板候选。独立limitup_single_v2完整裁决，最多一只允许0，不作为综合第五项前置。当前仍为模拟前推复核；20—30个交易日只是复核节点，不自动转实盘。','一、先查三日情绪与高标负反馈\n'+emotion,'二、高度、主线、空间与逐层晋级\n'+ladder_text,progression,space_text,'三、独立全A入口与至少三只真实备选\n从5573只可核行情、涨停/炸板和低位结构独立扫描，120只广泛重算、28只深筛；默认研究普通主板低位换手首板/二板/分歧回封，ST/退市、无上限新股、一字排队、高位连续缩量加速及爆量滞涨先否决。20%与30%不混10%制度。用户持仓、自选和曾询问名单不自动入选。',comparisons,'已核T27涨停上限参考：凯中13.49、峨眉山10.10、兰生9.04、百大12.62、青岛14.98、九百13.31，来自T27腾讯报价上限字段并有数据日期及其他价格来源；不是前收乘1.1假装权威。D28实时涨停价、除权/证券状态与盘口尚未可得，全部N/A；不能把T27封单或价格当D28触发。','四、否决与D28条件边界\n二进三0/8、3进4失败的林州/正裕跌停，叠加4921只下跌和原池10只最低≤-5%，退潮与晋级断层共振先否决。高标上海九百五板不能覆盖食品/零售跟随的退出风险，机器人四板也不能把所有电机股自动定为核心。若未来出现板块转弱、失承接、连续开板/撤单、爆量不推进或实时盘口无法核验，同样放弃；一笔大封单不单独成立。没有合格对象，不下调规则凑一只。','五、最早合法退出与持仓限制\n'+risk_boundary,'六、上一唯一候选与统计\nD27原v2决定为0只，不存在可记录的当日打板成交或收益；v2原始正式条件候选累计0，所有被比较对象不能事后变为候选。v1仅保留10月8日龙溪股份600592一条，原参考16.20与原条件保持，原未入场结论保留。新增结果分别列信号日收盘锚和原参考价观察，不能将二者混为入场价。首板/二板/回封、情绪/高度/空间/长假与规则版本统计仍分开，真实可验证成交N=0；封板率、炸板率、固定退出净收益均值/中位、盈亏比和尾部亏损N/A，不把触板或理论次日溢价当成交盈利。',previous_text,previous_table,'七、原文核验与可证伪假设\n'+official_text+'\n下一验证为低位换手首板在退潮后二进三断层环境能否保有承接，及“机构/股通同向+高乖离”是否仍劣于低中位回踩；规则limitup_single_v2冻结不改，不用本轮结果调参。','八、逐股原分母\n'+denominator_table,provider_note,common_boundary])
 combined_body='\n\n'.join([common,'结论：综合盘后组0只，空仓观察；与D28打板v2独立裁决0只分别归档，联合只表示编排。','一、四项同T完整前置及正反证据\n'+table(['任务','完整报告','对裁决的支持/否定'],[['market_review',IDS['market_review'],'同T5573→120→28；4921只下跌/成长指数弱，局部消费和连板强度不足以豁免风险'],['volume_price',IDS['volume_price'],'支持凯中/峨眉山突破；旧28中位-2.015%、冲高回撤否定单看RVOL'],['low_position',IDS['low_position'],'新2条30天研究不冒充短线买点；42条老样本/成熟模型N=0保持反证'],['dragon_tiger',IDS['dragon_tiger'],'襄阳机构股通同向也有高乖离和总榜卖；兰生多日机构净卖、正裕跌停构成对照']])+'\n市场复盘完整报告与真实completed回执复用；另三项完整独立补做，task_id/track/report_id、原始样本和真实回执各自保留。未用automated_observation、配置审计或eligible=false替代前置，量化不恢复。','二、独立扫描与重新比较\n5576原始、5573有效→120广泛→28深筛，全部120 OHLC交叉一致；原扫描启发式分数不直接决定入选，覆盖至少十组研究板块。'+repeat_text,definitions,features(de['deep_recomputed']),comparisons,'三、三日情绪、晋级与空间\n'+emotion,ladder_text,progression,space_text,'四、量价发现、上一组真实跟踪与累计验证\n'+previous_text,previous_table,vp_findings,stats_table,stats_text,'五、低位30天独立结论\n'+new_low_text+'\n'+low_prev,'六、公告和数据反证\n'+official_text,'七、买点、放弃及T+1退出\n'+risk_boundary+'\n下一实际交易日重点看：上海九百600838五板与襄阳000678/赛福天603028/多伦603528四板负反馈；林州002535/正裕603089断板风险是否扩散；凯中002823、峨眉山000888缩量回踩是否守原位。若没有持续价格推进和可核流动性，现金观察，不因错过上涨追高。','八、独立打板与归档检查\n完整'+IDS['limitup_single']+'按D28与v2独立完成0只，非第五前置；已有同T裁决不再换名单，重大事实另追加带实际时间修订。',provider_note,common_boundary])
 # Publish full reports and their real receipts together with all raw samples.
 base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 sources=list(dict.fromkeys([EV,'docs/research/market-review-2026-10-27-evidence.json',
  'https://www.sse.com.cn/disclosure/dealinstruc/closed/',
  'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData',
  'https://data.eastmoney.com/stock/tradedetail.html','https://data.10jqka.com.cn/market/longhu/',
  'https://api3.cls.cn/share/article/2516200',
  'https://qt.gtimg.cn/q=sz002823,sz000888,sh600826,sh600865']+[f['source'] for f in files.values()]))
 bodies={'volume_price':volume_body,'low_position':low_body,'dragon_tiger':dragon_body,'limitup_single':limitup_body,'combined_pair':combined_body}
 titles={'volume_price':'量价完整研究｜10月27日全池验证与28条冻结样本','low_position':'低位启动30天｜10月27日新增2条研究样本、42条历史验证','dragon_tiger':'龙虎榜完整研究｜10月27日席位核对、全池追踪与独立观察','limitup_single':'打板v2｜10月28日空仓，二进三断层与空间缺项先否决','combined_pair':'综合双标｜10月27日四项完整齐备，10月28日空仓观察'}
 summaries={'volume_price':'5573→120→28；旧28只中位-2.015%，v4为168条/6个日期，价格观察不当策略收益。','low_position':'新增凯中精密、峨眉山Ａ2条非交易研究样本；42条历史全路径核验，合格成熟30自然日模型N=0。','dragon_tiger':'87理由行/77股、11只席位及同周期价格核验、5只独立条件观察；旧71只全池分制度验证。','limitup_single':'D28无合格打板候选；普通主板首进二8/33、二进三0/8，20日空间仍缺5池。','combined_pair':'四项同T完整研究真实齐备；综合组0只、D28打板另组0只。原条件和现金结论不回写。'}
 rules={'volume_price':'volume_price_close_v4','low_position':'low_position_30d_v1','dragon_tiger':'dragon_tiger_original_contract','limitup_single':'limitup_single_v2','combined_pair':'combined_limitup_watch_v5'}
 new_reports=[];new_receipts=[]
 for task,body in bodies.items():
  rid=IDS[task];run_id=f"{task.replace('_','-')}-{TAG}-scheduled-close-{'v2' if task=='limitup_single' else 'v1'}"
  r={'id':rid,'date':T,'market_date':T,'task_id':task,'track':task if task in ('volume_price','low_position','dragon_tiger') else 'market_review',
   'run_id':run_id,'title':titles[task],'summary':summaries[task],'body':body.strip(),'sources':sources,
   'report_type':'full_trading_research' if task=='combined_pair' else 'full_daily_research','eligible_for_integrated_research':task!='limitup_single',
   'analysis_completed':True,'status':'completed','published_at':stamp,'recorded_at':stamp,'market_data_cutoff_at':T+'T15:00:00+08:00',
   'data_cutoff_at':stamp,'planned_entry_date':D,'earliest_legal_exit_date_if_bought':EXIT,'research_rule_version':rules[task],
   'provenance':'contemporaneous_after_close_research','candidate_count':0,'recommendation_ids':[],'evidence_file':EV,
   'full_scan_count':5573,'broad_pool_count':120,'deep_pool_count':28,'codes':[s['code'] for s in de['deep_recomputed']]}
  if task=='low_position':r.update(new_sample_count=2,new_sample_ids=[s['id'] for s in new_low],previous_samples_verified=42,codes=sorted({s['code'] for s in low['items']+new_low}))
  if task=='dragon_tiger':r.update(observation_count=5,signal_observations=dragon_obs,codes=[s['code'] for s in de['dragon_selected']])
  if task=='combined_pair':r.update(dependency_report_ids=[IDS[t] for t in ('market_review','volume_price','low_position','dragon_tiger')],strategy='combined_limitup_watch',group='close',cohort_label='综合盘后组',decision='cash_no_qualified_candidate')
  if task=='limitup_single':r.update(strategy='limitup_single_v2',decision='cash_no_qualified_candidate',group='close',full_20_session_space_reference_available=False)
  new_reports.append(r)
  new_receipts.append({'id':run_id+'-completed','run_id':run_id,'task_id':task,'date':T,'trigger':'scheduled','started_at':START,'completed_at':stamp,'recorded_at':stamp,
   'status':'completed','summary':summaries[task],'report_ids':[rid],'recommendation_ids':[],'analysis_completed':True,
   'eligible_for_integrated_research':task!='limitup_single','delivery_status':'repository_prepared_not_yet_ci_or_production_verified','sources':[EV]})
 research['items'].extend(new_reports);runs['items'].extend(new_receipts)
 for s in low['items']:
  obs=next(r for r in de['low_validations'] if r['origin_cohort_id']==s['id'])
  s.setdefault('observations',[]).append({**obs,'recorded_at':stamp,'calculated_at':de['calculated_at']})
 low['items'].extend(new_low);low['updated_at']=stamp
 vp['items'].extend([
  {'id':'volume-price-20261026-validation-20261027-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
   'origin_cohort_id':'volume-price-20261026-close-v1-cohort','rule_version':'volume_price_close_v4','full_validation_completed':True,
   'full_pool_summary':de['previous_whole_pool_summary'],'full_pool_validations':de['previous_whole_pool'],'executed_trade_count':0,
   'eligible_for_model_statistics':False,'statistical_scope':'price_observation_not_executable_strategy'},
  {'id':'volume-price-historical-validation-20261027-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
   'cohort_ids':[r['origin_cohort_id'] for r in cum['vp_all_cohort_validations']],'frozen_sample_count':257,'matched_original_close_count':256,
   'rule_version_groups':cum['vp_by_rule_version'],'evidence_file':EV,'executed_trade_count':0,'eligible_for_model_statistics':False,
   'note':'Frozen cohorts and versions remain distinct; descriptive price observations, no hypothetical fills or net returns.'},
  {'id':'volume-price-20261027-close-v1-cohort','date':T,'task_id':'volume_price','frozen_at':stamp,'report_ids':[IDS['volume_price']],
   'rule_version':'volume_price_close_v4','feature_calculation_version':'unadjusted_MA_including_T_v3','data_cutoff_at':T+'T15:00:00+08:00',
   'broad_pool_count':120,'broad_pool_verified_count':120,'deep_screen_count':28,'eligible_for_model_statistics':True,
   'statistical_scope':'future_price_observation_not_trade_profitability','provenance':'contemporaneous_full_market_research','samples':de['deep_recomputed']}])
 # Preserve the older validation anchor (planned-entry-date close) while also
 # explicitly showing signal-day and original reference baselines. None is a fill.
 bench={b['date']:b for b in sup['benchmarks']['sh000001']['bars']}
 for r in recs['items']:
  by={b['date']:b for b in daily[r['code']]};anchor=r.get('planned_entry_date') or r['date'];a=by.get(anchor);signal=by.get(r['date'])
  hs=[]
  for h in (1,3,5,10,20,30):
   ds=nth_session_after(date.fromisoformat(anchor),h).isoformat();cur=by.get(ds);mature=ds<=T
   expected=[];day=date.fromisoformat(anchor)+timedelta(days=1)
   while day<=min(date.fromisoformat(ds),date.fromisoformat(T)):
    if is_session(day):expected.append(day.isoformat())
    day+=timedelta(days=1)
   missing=[day for day in expected if day not in by];path=[by[day] for day in expected if day in by]
   ok=bool(mature and a and cur and not missing)
   bp=pct(bench[ds]['close'],bench[anchor]['close']) if ok and ds in bench and anchor in bench else None
   ret=pct(cur['close'],a['close']) if ok else None
   hs.append({'h':h,'date':ds,'status':'price_observed' if ok else 'missing' if mature else 'pending',
    'close_pct':ret,'high_observation_pct':pct(max(p['high'] for p in path),a['close']) if ok else None,
    'low_observation_pct':pct(min(p['low'] for p in path),a['close']) if ok else None,'benchmark_pct':bp,
    'excess_price_observation_pct':round(ret-bp,3) if ret is not None and bp is not None else None,'missing_sessions':missing if mature else []})
  ref=r.get('reference_price')
  r.setdefault('results',[]).append({'id':r['id']+'-price-review-20261027','date':T,'market_date':T,'recorded_at':stamp,
   'report_ids':[IDS['limitup_single'] if r.get('task_id')=='limitup_single' else IDS['combined_pair']],
   'status':'price_observation_only','observed_daily':by[T],'anchor_date':anchor,'anchor_close':a['close'] if a else None,
   'anchor_definition':'planned-entry-date daily close, retained for consistency with prior price-only reviews; not a transaction price',
   'signal_date':r['date'],'signal_daily_close':signal['close'] if signal else None,'original_frozen_reference_price':ref,
   'T_close_vs_signal_daily_close_pct':pct(by[T]['close'],signal['close']) if signal else None,
   'T_close_vs_original_reference_pct':pct(by[T]['close'],ref) if isinstance(ref,(int,float)) and ref>0 else None,
   'horizons':hs,'trigger_status':'original_no_entry_preserved' if r['id']=='limitup-single-20261008-600592-v1' else 'not_reconstructed_from_daily_extremes',
   'executed_trade':False,'executable_net_return_pct':None,'fee_and_slippage_status':'unverified quantity, commission/minimum fee, slippage and order fills; no net P/L',
   'source':raw['daily_histories'][r['code']]['source'],'note':'Original reference, group, strategy, trigger/invalidation and previous outcomes remain frozen; no hindsight entry.'})
 stock_updates=[]
 for stock in catalog['items']:
  rows=[r for r in de['low_validations'] if r['code']==stock['code']]
  if not rows:continue
  r=rows[-1];ep={'id':f"research-stock-{stock['code']}-{TAG}-low-followup-v1",'date':T,'recorded_at':stamp,
   'title':'30天研究价格跟踪与原失效核验','reason':f"{stock['name']}原低位样本继续跟踪；本次相对原收盘价格观察{r['close_return_pct']}%，不改原快照、模型资格及失败结论。",
   'evidence_status':'verified_daily_price_observation_not_trade_return','fact_note':f"原日期{r['reference_date']}，T27收盘{r['price_observation']['close']}，原失效位{r['original_invalid_close_below']}；曾收破={r['ever_verified_close_below_original_invalid']}。",
   'validation':['原自然日和交易日节点独立，未成熟不补结果','以原失效位核查收盘路径，未以价格回升抹去失败'],
   'risk':'价格观察不证明实际成交、固定退出净收益、资金身份或30天稳定胜率。','report_ids':[IDS['low_position']],
   'sources':[raw['daily_histories'][stock['code']]['source'],EV]}
  stock['history'].append(ep);stock_updates.append({'code':stock['code'],'history_id':ep['id']})
 for s in new_low:
  assert not any(r['code']==s['code'] for r in catalog['items'])
  ep={'id':f"research-stock-{s['code']}-{TAG}-origin-v1",'date':T,'recorded_at':stamp,'title':'新增30天研究样本，非短线交易推荐',
   'reason':s['reason'],'evidence_status':'verified_closed_daily_snapshot_with_official_filing_risk_notes',
   'fact_note':f"{s['name']}T27收盘{s['day0_close']}，原失效收盘位{s['invalid_close_below']}；未来节点尚未知。",
   'validation':['按1/3/5/10/15/20/30自然日与5/10/20交易日滚动前推','验证放量后的承接与板块同步，不将形态认定账户身份'],
   'risk':s['risk'],'report_ids':[IDS['low_position']],'sources':s['sources']}
  catalog['items'].append({'code':s['code'],'name':s['name'],'sector':s['sector'],'role':'research','default_watch':False,'history':[ep]})
  stock_updates.append({'code':s['code'],'history_id':ep['id']})
 catalog['updated_at']=stamp
 evidence={'market_date':T,'planned_entry_date':D,'earliest_legal_exit_if_bought':EXIT,'actual_started_at_utc':START,'actual_completed_at':stamp,'base_main':base,
  'reused_market_report_id':IDS['market_review'],'reused_market_report_sha256':hashlib.sha256(json.dumps(market_report,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
  'initial_failure_results':initial_failures,'sina_pages':raw['sina_pages'],'daily_histories':raw['daily_histories'],'minute_price_points':raw['minute_price_points'],
  'retry_checks':load('tmp/combined-20261027-retry-checks.json'),'lhb_lists':raw['lhb_lists'],'seat_queries':raw['seat_queries'],'limit_up_pools':raw['limit_up_pools'],
  'prior_pool_reuse':[prior_path],'prior_pool_reuse_sha256':hashlib.sha256((ROOT/prior_path).read_bytes()).hexdigest(),
  'derived':de,'cumulative':cum,'supplement':sup,'official_queries':official,'extra_official_queries':extra,
  'official_files':{k:{a:b for a,b in r.items() if a not in ('pdf_path','text_path','local_pdf','local_text')} for k,r in files.items()},
  'official_verified_fact_notes':fact_notes,'ths_summary_rows':ths['tables'][5],'ths_source':ths['source'],'seat_profiles':profiles,
  'raw_quoted_upper_prices':upper,'fresh_vendor_pool_completeness_check':load('tmp/combined-20261027-pool-completeness-recheck.json'),
  'new_low_samples':new_low,'new_dragon_observations':dragon_obs,'stock_history_updates':stock_updates,
  'limitations':['15/20 prior session pools, full historical highest and cycle start unknown','38 extra old low-code minute queries failed with HTTP 501',
   'No 9:25 auction, full historical minute OHLC/ticks, queue/order fills, exhaustive point-in-time security status or calibrated transaction costs',
   'Old missing anchors/retrospective and unverified samples retained outside eligible statistics','No executable win rate, hypothetical fill, automatic strategy weights or quant research']}
 encoded=gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)
 manifest={'base_main':base,'market_date':T,'planned_entry_date':D,'actual_started_at_utc':START,'analysis_completed_at':stamp,
  'new_report_ids':[r['id'] for r in new_reports],'reused_report_ids':[IDS['market_review']],'new_recommendations':0,
  'new_low_samples':len(new_low),'old_low_observations_appended':42,'new_volume_samples':28,'old_frozen_recommendation_results_appended':len(recs['items']),
  'stock_history_updates':stock_updates,'evidence_file':EV,'evidence_sha256':hashlib.sha256(encoded).hexdigest(),
  'task_registry_changed':False,'schedules_changed':False,'quant_research_restored':False}
 assert datetime.fromisoformat(START)<=datetime.fromisoformat(stamp)<=datetime.now(timezone.utc)
 # All serializations and assertions finish before the archive files are replaced.
 documents={'backend/data/research.json':research,'backend/data/task_runs.json':runs,'backend/data/volume_price_samples.json':vp,
  'backend/data/low_position_samples.json':low,'backend/data/recommendations.json':recs,'backend/data/research_stocks.json':catalog,
  'app/src/main/assets/research_stocks.json':catalog,'docs/research/combined-pair-20261027-publication-manifest.json':manifest}
 serialized={p:json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n' for p,d in documents.items()}
 for p,content in serialized.items():
  target=ROOT/p;temp=target.with_suffix(target.suffix+'.tmp');temp.write_text(content);temp.replace(target)
 (ROOT/EV).write_bytes(encoded)
 for task,body in bodies.items():
  (ROOT/f'docs/research/{IDS[task]}.md').write_text('# '+titles[task]+'\n\n'+body.strip()+'\n\n来源：\n\n'+'\n'.join('- '+s for s in sources)+'\n')
 print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
