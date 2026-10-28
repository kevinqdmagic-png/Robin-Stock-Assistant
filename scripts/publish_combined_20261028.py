"""Append contemporaneous full research and isolated forward shadow experiments.

Explicit analyst decisions are documented below. This is an archive assembler,
not a stock-picking service, a fill simulator, or an automatic parameter trainer.
"""
from collections import Counter
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import copy, gzip, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from learning_loop import is_session,nth_session_after
from prepare_completion_20261023 import pct
T='2026-10-28';D='2026-10-29';EXIT='2026-10-30';TAG='20261028'
START='2026-10-28T09:44:14+00:00'
EV='docs/research/combined-pair-20261028-evidence.json.gz'
EXP='docs/research/shadow-experiments-20261029-v1.json'
IDS={t:f'{t.replace("_","-")}-{TAG}-close-'+('v2' if t=='limitup_single' else 'v1') for t in ('market_review','volume_price','low_position','dragon_tiger','combined_pair','limitup_single')}
SECTORS=dict(zip(['000554','300539','300980','605488','600828','002696','300549','603337','603109','603037','001400','301225','688836','300718','600078','603131','002889','001296','002172','003028','603081','688286','603926','300986','603699','603633','300421','300473'],['成品油零售','精密传动/机器人研究标签','高分子材料','功能薄膜','零售','水产/饲料','精密模具','缝制装备','通用动力','汽车零部件','汽车铝型材','汽车进气系统','机器人','传动/机器人','磷化工','焊接设备','供应链','铸造材料','化纤','智能控制','文体装备','传感器','汽车传动','建筑铝模','工业阀门','连接器','精密轴承','汽车零部件']))
NEW_LOW={
 '000554':('成品油零售',6.03,'低中位箱体突破','120日区间39.13%、60日60.305%；收6.63越过原20日高6.50并收复MA60，研究首轮放量突破后的承接。','前三季营收下降10.60%，不是增长无风险；10月21日每股0.06元现金除息使未复权历史位置受影响。','000554-q3'),
 '603109':('通用动力',16.31,'低中位放量修复','120日区间31.673%、收复MA60；原20日高17.99尚未越过，不叫箱体突破，检验放量修复能否持续。','前三季归母下降50.49%、Q3归母下降64.00%，量能放大不能证明经营反转。','603109-q3'),
 '603926':('汽车传动',15.45,'低中位放量修复','120日区间30.168%、收复MA60；RVOL20为3.391，原20日高17.96未破，研究首次放量修复与回踩。','前三季现金流改善，但Q3收入下降13.13%、归母下降10.98%；次日开板和承接仍未知。','603926-q3')}
FACTS=[
 ('000554',['000554-q3','000554-dividend'],'未经审计前三季营收21.4126亿元(-10.60%)、归母1.4253亿元(+25.92%)、扣非1.3939亿元(+19.29%)、经营现金流1.9900亿元(+23.89%)；Q3归母3526.77万元(+62.33%)。每股派0.06元，登记10月20日、除息10月21日，不能给D29买入补算该分红。'),
 ('603699',['603699-h1','603699-pledge','603699-dividend'],'取得的是未经审计半年报而非三季报：营收38.9692亿元(+14.47%)、归母7.3338亿元(+15.20%)、扣非7.2052亿元(+17.11%)、经营现金流5.3996亿元(-40.84%)。10月22日陆斌质押120万股，占其持股1.58%、总股本0.15%，不能凭此断言危机。每股0.42元除息日10月20日；未复权历史高点与原复盘前复权指标不可混用。Q3未取得。'),
 ('603926',['603926-q3'],'未经审计前三季营收17.0866亿元(-3.29%)、归母9349.46万元(+22.39%)、扣非7854.98万元(+23.39%)、经营现金流2.6500亿元(+195.40%)；Q3营收5.0502亿元(-13.13%)、归母2455.97万元(-10.98%)。累计现金改善不掩盖单季收入利润下降。'),
 ('603109',['603109-q3'],'未经审计前三季营收25.1036亿元(+9.74%)、归母8347.51万元(-50.49%)、扣非7098.40万元(-54.44%)、经营现金流7985.73万元(-14.77%)；Q3归母1834.54万元(-64.00%)、扣非470.22万元(-86.77%)。'),
 ('603633',['603633-q3','603633-guarantee'],'未经审计前三季营收13.3717亿元(+16.83%)、归母-8496.39万元、扣非-8820.32万元；Q3归母-2388.74万元。集团担保总额24.75亿元为审计净资产139.22%，其中母保子6.95亿元39.09%、子保母17.80亿元100.13%，不重复加总；新增对子公司4500万元担保，受保子公司负债率超过70%，公告称无逾期。'),
 ('600078',['600078-q3','600078-impairment'],'未经审计前三季营收35.8968亿元(+35.15%)、归母2.6472亿元(+848.20%)、扣非2.5951亿元(+1037.25%)、经营现金流3.0787亿元(-16.91%)。终止宣威项目减值2914.91万元，归母影响约-2186.18万元预计反映Q4，不能说已包含在Q3或再次从Q3重复扣除。'),
 ('300549',['300549-q3'],'未经审计前三季营收2.5770亿元(+5.38%)、归母881.08万元(+3.26%)、经营现金流793.55万元(-66.81%)；价格推进不能认定机构建仓。'),
 ('300539',['300539-q3'],'未经审计前三季营收6.7809亿元(-3.68%)、归母3237.41万元(-13.67%)、扣非2753.55万元(-17.18%)、经营现金流4981.40万元(-9.20%)；Q3归母+16.61%而扣非-4.29%，不能只取增长一项。'),
 ('300980',['300980-q3'],'未经审计前三季归母6979.22万元(+71.68%)、扣非2896.34万元(-12.29%)；Q3归母556.87万元(-72.85%)、扣非293.88万元(-82.11%)。非经常损益与单季反证须保留。'),
 ('001296',['001296-q3'],'未经审计前三季归母7464.37万元(-34.35%)、经营现金流6305.21万元(-65.98%)；Q3归母1988.58万元(-50.68%)，不能把放量首板直接认定价值重估完成。'),
 ('605488',['605488-q3'],'未经审计前三季营收26.3574亿元(+25.71%)、归母5608.95万元(-13.17%)、扣非4335.95万元(-18.82%)、经营现金流6951.73万元(-39.19%)；Q3归母411.62万元(-69.88%)、扣非162.43万元(-79.65%)。'),
 ('603337',['603337-risk'],'原风险公告披露10月23—28日累计涨幅36.82%、换手21.76%；机器人相关产品在缝纫应用处于商业化初期，营收利润占比极低且研发投入带来压力，不当成已确认机器人利润增长。'),
 ('000678',['000678-q3'],'未经审计前三季归母-2617.40万元、Q3归母-556.17万元，均为亏损收窄而非扭亏；前三季经营现金流4008.78万元(-77.47%)。'),
 ('002708',['002708-risk'],'风险公告披露半年归母5720.19万元(+8.04%)、扣非250.49万元(-94.83%)；机器人业务半年收入999.41万元且未盈利。三季报计划10月30日披露，不用半年报冒充三季报。'),
 ('301139',['301139-delisting'],'原公告明确最后交易日10月27日、10月28日摘牌。上一龙虎榜全池仍保留该样本，T28无交易日线不是收益0，也不从样本分母删除；摘牌后的转让安排不证明当前可交易。')]
def load(p):return json.loads((ROOT/p).read_text())
def fmt(x,n=3):return 'N/A' if x is None else str(round(x,n)) if isinstance(x,(int,float)) and not isinstance(x,bool) else str(x)
def table(headers,rows):return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(fmt(x).replace('|','/') for x in row)+'|' for row in rows])
def main():
 research=load('backend/data/research.json');runs=load('backend/data/task_runs.json');low=load('backend/data/low_position_samples.json');vp=load('backend/data/volume_price_samples.json');recs=load('backend/data/recommendations.json');catalog=load('backend/data/research_stocks.json')
 for task in IDS:
  if task!='market_review' and any(r.get('task_id')==task and r['date']==T and r.get('report_type') in ('full_daily_research','full_trading_research') for r in research['items']):raise RuntimeError('Reuse existing same-T full module instead: '+task)
 market_report=next(r for r in research['items'] if r['id']==IDS['market_review'])
 assert market_report.get('eligible_for_integrated_research') is True and any(r.get('status')=='completed' and r.get('report_ids')==[IDS['market_review']] for r in runs['items'])
 raw=load('tmp/combined-20261028-raw.json');initial_failures={k:{c:r.get('error') for c,r in raw[k].items() if not r.get('ok')} for k in ('daily_histories','seat_queries','minute_price_points','limit_up_pools')}
 ext=load('tmp/combined-20261028-extension.json');initial_failed_records={k:{c:r for c,r in raw[k].items() if not r.get('ok')} for k in ('daily_histories','seat_queries','minute_price_points','limit_up_pools')}
 for k in ('daily_histories','seat_queries','minute_price_points','limit_up_pools'):raw[k].update(ext.get(k,{}))
 de=load('tmp/combined-20261028-derived.json');cum=load('tmp/combined-20261028-statistics.json');sup=load('tmp/combined-20261028-supplement.json');files=load('tmp/combined-20261028-official-files.json');official=load('tmp/combined-20261028-announcements.json');extra=load('tmp/combined-20261028-extra-announcements.json');ths=load('tmp/combined-20261028-ths.json');profiles=load('tmp/combined-20261028-seat-profiles.json');upper=load('tmp/combined-20261028-quote-upper-check.json');exact=load('tmp/combined-20261028-exact-main-limit-check.json');market=load('docs/research/market-review-2026-10-28-evidence.json')
 assert de['crosscheck']['recomputed_broad']==120 and len(de['deep_recomputed'])==28 and not de['crosscheck']['ohlc_mismatches']
 assert len(de['low_validations'])==44 and de['low_summary']['all_paths_complete']
 assert all(s['seat_reconciliation']['matched'] and s['ths_close_match'] for s in de['dragon_selected'])
 daily={c:r['bars'] for c,r in raw['daily_histories'].items() if r.get('ok')};lookup={s['code']:s for s in de['broad_recomputed']}
 missing=next(x for x in de['dragon_previous_whole_disclosed_pool'] if x['code']=='301139')
 missing.update(status='delisted_no_exchange_trading_bar',price_observation_return_pct=None,executed_trade=False,source=files['301139-delisting']['source'],explanation='10月27日最后交易，10月28日摘牌；保留缺失/不可交易，不填零收益。')
 now=datetime.now(timezone.utc);stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
 assert now < datetime.fromisoformat(D+'T09:30:00+08:00')
 for s in de['deep_recomputed']:s.update(sector_research_label=SECTORS[s['code']],signal_frozen_at=stamp,rule_version='volume_price_close_v4',is_recommendation=False)
 fact_notes=[{'code':c,'keys':ks,'fact':f} for c,ks,f in FACTS]
 official_text=table(['准确代码','原公告核验与反证'],[[r['code'],r['fact']] for r in fact_notes])
 official_text+='\n\n20份原始PDF均保留URL、哈希和真实HTTP取证时间；核心财务表与摘牌公告已渲染核对。部分PDF路径标10月29日，但本轮10月28日已实际可取，只用于本次盘后D29预案，不回填T28盘中原因或假定精确首次披露时刻。纽威8月以来检索两页后仍有下一页，完整证券状态、减持/解禁风险未全面排除；取得半年报不冒充已取得Q3。'
 def features(rows):return table(['代码/名称','研究板块','收盘/涨跌%','RVOL5/10/20','换手%/变化pp','20/60/120位置%','MA5/10/20/60','CLV/14时后%'],[[s['code']+' '+s['name'],SECTORS.get(s['code'],'其他'),fmt(s['close'])+'/'+fmt(s['daily_change_pct']),'/'.join(fmt(s['rvol'][str(n)]) for n in (5,10,20)),fmt(s['turnover_pct'])+'/'+fmt(s['turnover_change_pct_points']),'/'.join(fmt(s['range_position_pct'][str(n)]) for n in (20,60,120)),'/'.join(fmt(s['ma'][str(n)]) for n in (5,10,20,60)),fmt(s['clv'])+'/'+fmt(s['tail_1400_close_pct'])] for s in rows])
 def pool_validation(rows):return table(['代码/名称','开盘观察%','最高观察%','最低观察%','收盘观察%'],[[r['code']+' '+r['name'],r.get('open_pct'),r.get('mfe_pct'),r.get('mae_pct'),r.get('close_pct')] for r in rows])
 common=f'已收盘交易日T={T}；行情截止北京时间15:00，实际本次冻结/完成{stamp}。未来计划日D={D}，D实际买入最早{EXIT}可卖。已核交易所2026日历，无该三日休市安排。参考收盘不是成交价；本轮不倒造D28盘前名单。'
 definitions='RVOL为T全日量除以前5/10/20个已完成交易日均量，分母不含T，非盘中量比。本文MA与20/60/120日位置为未复权且含T；原市场复盘用前复权、历史窗口不含T，复权与截点均不同，保留两套不覆盖。纽威10月20日0.42元、泰山10月21日0.06元现金除息尤其须区分。CLV=(收盘-低)/(高-低)，高低相同N/A。换手变化比较T27/T28真实新浪同口径快照。分钟数据是有日期价格点/累计量额，无逐笔、分钟内顺序、排队成交、9:25竞价或全历史换手；不能反推买卖或账户身份。'
 p=de['previous_whole_pool_summary']
 previous_text=f"先验证T27全部28只冻结候选：28/28原收盘锚与日线一致，收红{p['positive_n']}只，T28收盘观察均值{p['mean_pct']}%、中位{p['median_pct']}%，平均最高{p['mean_mfe_pct']}%、平均最低{p['mean_mae_pct']}%，{p['mae_le_minus5_n']}只盘中最低相对前收≤-5%。同一volume-price-20261027-close-v1-cohort跨市场/量价引用仅计一次。原综合/打板正式组均0只，无可核实策略盈亏。T28新指令之前没有合格的本任务D28影子冻结，不事后把今天赢家补入前推。市场复盘16:50:58已冻结D29纽威/横河研究对象，尚未到D29验证期；与本次纽威重叠是同一股票-计划日事件。"
 previous_table=pool_validation(de['previous_whole_pool'])
 stats_table=table(['版本','原样本N','独立日期','T+1 N','均值/中位%','平均最低%','T+2 N','均值/中位%'],[[r,v['frozen_sample_count'],v['independent_dates'],v['horizons']['1']['n'],fmt(v['horizons']['1']['mean_pct'])+'/'+fmt(v['horizons']['1']['median_pct']),v['horizons']['1']['mean_mae_pct'],v['horizons']['2']['n'],fmt(v['horizons']['2']['mean_pct'])+'/'+fmt(v['horizons']['2']['median_pct'])] for r,v in cum['vp_by_rule_version'].items()])
 stats_text='11个明确id的旧cohort共285条样本，284条原收盘可核；10月8日缺价1条保留但不补造，假期回溯另列。v4为196条/7个独立日期，T+1均值-0.081%、中位-0.467%、平均最低-4.269%；T+2为168条/6日、均值-0.969%、中位-1.720%。不是196笔已成交交易。1/2/3/5/10/20/30交易日节点、原形态/位置/制度分层与未成熟均保存在证据。未校准数量、最低佣金、手续费和滑点；旧20bp仅占位。成交N=0，策略净收益、策略胜率、盈亏比/退出质量均N/A；9:50/14:40及盘后独立。新增28条从D29之后前推，不用入选日涨幅证明有效。'
 market_days=[]
 for day in ('2026-10-26','2026-10-27',T):
  m=load(f'docs/research/market-review-{day}-evidence.json')['market'];market_days.append([day,m['standard_non_st_limit_up_sealed'],m['standard_non_st_failed_boards'],m['standard_non_st_limit_down'],round(m['standard_non_st_limit_up_sealed']/m['standard_non_st_limit_up_touched']*100,3),round(m['amount_yuan_full_scan']/1e8,2),m['advance'],m['decline']])
 emotion=table(['日期','主板阈值封板','触板未封代理','跌停代理','代理封板率%','全A成交亿元','涨','跌'],market_days)
 emotion+='\n\n三日表固定为新浪正常普通主板约10%阈值代理，非精确上限。T28另对160只阈值入口股票逐一取得腾讯同日上下限，160/160核验：精确可见封板59、触板108、触板未封49、跌停收盘7；49/108=45.370%为本核验范围炸板率，不冒称完整证券状态主表或全制度统计。纽威38.39低于当日38.40上限，仅触板未封。财联社15:09全制度口径71涨停/69炸板、约51%，稍后媒体72/69，原东财72加福莱独立补证73，来源时点/制度范围分别保留，不拼成同一分母。'
 emotion+='\n\nT26/T27退潮后，T28宽度4156涨/1238跌、沪指+0.91%、深指+2.02%、创业板+3.40%支持修复；盘中冲板兑现、机器人午后分歧和昨日高标断板仍反对直接定为强势。新影子情绪口径从本轮起冻结：下跌/(涨+跌)≥65%且代理炸板率≥40%为弱；上涨比例≥65%且代理炸板率≤25%为强；其余为震荡。T28是震荡中的修复，不能把它假称弱市样本证明弱市优势。原报告旧情绪标签不回写。'
 ladder=table(['正常主板连续板数','家数','代码/名称'],[[k,len(v),'、'.join(r['code']+r['name'] for r in v)] for k,v in de['board_ladder'][T]['layers'].items()])
 ladder+='\n\n原东财池72条不修改；福莱605488日线/新浪/腾讯T28收48.61等于当日上限48.61，单列补证后共73，普通主板59、其他制度14。福莱首次/末次封板时刻及开板次数未知，不从媒体“午后开板”推断最终未回封。普通主板可见最高襄阳000678五板、次高青岛001219/光洋002708三板，四板断层；一字/缩量加速不是普通成交保证。泰山当前首板、成品油零售可见高度1，角色待确认，不能借机器人高标给它套领涨地位。'
 progression=table(['层级','T27冻结分母','晋级','断板','停牌/缺失','晋级%'],[[k,v['prior_full_denominator'],v['advanced'],v['broken'],v['missing'],v['verified_advancement_pct']] for k,v in de['progression_main_10pct'].items()])
 denominator_table=table(['原层级','T27冻结股票','T28结果','收盘'],[[k,r['code']+' '+r['name'],r['status'],r['T_close']] for k,v in de['progression_main_10pct'].items() for r in v['rows']])
 progression+='\n\n分母用T27已发布41条原池及600826/600865两条原补证，不从T28成功名单倒推。正常主板1进2为5/26、2进3为2/8、3进4无原三板故N/A、4进5为1/3、5进6为0/1。媒体5/24等口径不改写本冻结分母。20%/30%/风险警示独立。上海九百600838虽断五板仍收涨5.109%，赛福天603028断四板仍收涨0.678%，不能把断板等同收跌；多伦603528收跌9.949%为负反馈。'
 sp=cum['twenty_prior_sessions_space_reference']
 space_text=f"空间参照取T之前20个实际交易日{sp['requested_sessions'][0]}—{sp['requested_sessions'][-1]}，取得/复用16池，缺{','.join(sp['missing_session_pools'])}；可见最高11板是新华传媒600825在10月16日，非完整20日最高证明。完整窗口最高、情绪周期起点/周期最高N/A。五板襄阳没有突破可见11板，更不能叫空间已打开；N天M板不当连续M板。"
 # Freeze research records only after prior validation; never feed formal alerts.
 selected_specs=[
  ('combined_pair',1,'603699','低位修复＋尾盘承接','H1/H3',[36.81,37.88],[37.88,38.39],35.88,34.50,39.16,'低长期位置12.496%，RVOL20=3.542、CLV0.9974、14时后+1.346%；较横河20%制度和高换手，10%制度便于同口径实验。','未收复MA20/60，不能叫趋势完成或封板；H1只是待证伪修复。半年现金流下降、Q3未取得，小额质押不当确定身份。','BK0545'),
  ('combined_pair',2,'603926','低中位放量修复','H1/H3',[16.40,17.06],[16.49,17.06],16.40,15.45,17.40,'RVOL20=3.391、收复MA60、120日位置30.168%，累计现金流改善；相较徕木亏损/高担保及神驰利润下滑，反证较少。','原20日高17.96未破，14时后0%只是封板价格持平，不证明尾盘主动吸筹；Q3单季收入利润下滑。','BK0481'),
  ('limitup_single',1,'000554','首板后首次分歧承接/回封','H2/H3',[6.63,6.96],None,6.42,6.03,6.96,'首板、120日位置39.13%，换手15.177%、RVOL20=4.86，突破原20日高6.50；Q3盈利及现金流支持相较高位缩量接力的研究顺序。','高换手放量可能是分歧而非吸筹；营收下降、油品主线不强，15:00封单不能沿用到D29。成品油高度可见1，角色待确认。',None)]
 shadow=[]
 for task,rank,c,model,hyp,pull,confirm,inv,struct,cap,why,risk,sector in selected_specs:
  s=lookup[c];sym=('sh' if c.startswith('6') else 'sz')+c;q=upper['provider_fields'][sym];quote_batch=next(b for b in upper['batches'] if sym in b['source'])
  if task=='combined_pair':trigger=f'D29竞价不高于{cap}；09:45与10:30两个有日期价格点都在{confirm[0]}—{confirm[1]}且当时累计VWAP不高于现价，再核验研究回踩区{pull[0]}—{pull[1]}的先后证据。无先后证据只作收盘价格观察，不认定触发或成交。'
  else:trigger='D29竞价6.63—6.96；09:30—10:30内有真实首次分歧后回封逐笔时序，并由当日带日期行情核验实际涨停上限，价格回到该上限且至少连续60秒可核验承接后，才记研究触发。分钟价点不能证明60秒或排队成交；无逐笔/队列证据触发与成交保持待验证。'
  shadow.append({'id':f'shadow-{task.replace("_","-")}-20261029-{c}-v1','role':'research_shadow','is_recommendation':False,'formal_buy_signal':False,'send_trade_notification':False,'parent_task_id':task,'report_ids':[IDS[task]],'rank':rank,'date':T,'T':T,'planned_entry_date':D,'signal_frozen_at':stamp,'recorded_at':stamp,'freeze_phase':'before_planned_session_open','eligible_forward_observation':True,'code':c,'name':s['name'],'market_event_id':f'cnA:{D}:{c}','board_regime':s['board_regime'],'daily_limit_pct':10,'reference_price':s['close'],'reference_price_at':T+'T15:00:00+08:00','reference_is_fill':False,'provider_quote_timestamp':q[30],'observed_T_upper_price':float(q[47]),'observed_T_lower_price':float(q[48]),'D_actual_upper_price':None,'D_upper_status':'must obtain dated D quote; not T close times 1.1','evidence_available_at':[{'source':raw['daily_histories'][c]['source'],'retrieved_at':raw['daily_histories'][c]['retrieved_at']},{'source':quote_batch['source'],'retrieved_at':quote_batch['retrieved_at']}],'sources':[s['source'],s['minute_checkpoints']['source'],quote_batch['source'],EV]+[files[k]['source'] for fc,ks,_ in FACTS if fc==c for k in ks],'theme':SECTORS[c],'research_rule_version':'weak_market_shadow_v1','parent_rule_version':'limitup_single_v2' if task=='limitup_single' else 'combined_limitup_watch_v5','model':model,'hypothesis_labels':hyp.split('/'),'market_emotion':'震荡','emotion_detail':'退潮后的修复，尚非已确认强势；弱市标签不回填','selection_reason':why,'formal_rejection_reason':risk,'independent_risk':risk,'pullback_or_auction_range':pull,'confirmation_range':confirm,'max_auction_price':cap,'observation_invalidation_below':inv,'structural_invalidation_below':struct,'trigger':trigger,'abandon':'D29高于冻结竞价上限、跌破观察失效、板块转弱、主参考股弱势扩散、连续开板或爆量不能推进即放弃该条件；日期/盘口/可成交性不能核验则不计触发成交。绝不由日线高低倒推顺序。','earliest_legal_exit_if_bought_at':EXIT+'T09:30:00+08:00','exit_rule':'若D29有可证实模拟入场，D30最早可卖；综合按D30 09:45首个可证明可成交报价尝试退出，打板按D30 09:30首个可证明可成交报价。强开/平开/弱开均遵守同一时点，不事后选择最高；跌停/停牌/排队未成交记录未退出并延后至下一个可证明成交时点。D29失效只能承受持仓风险，不能当天卖。','research_benchmark':'sh000300','sector_benchmark_proxy':sector,'sector_mapping_status':'按公开主营作研究代理，未声称供应商成分归属已核验','entry_triggered':None,'entry_fill_verified':None,'sealed_or_failed_after_entry':None,'executable_net_return_pct':None,'results':[]})
 # Each control is frozen now, never selected from D29 winners.
 controls=[]
 for c,label in [('603037','H1高位均线乖离对照'),('601956','H1等成交额高位置对照'),('603337','H3绝对涨幅/高位对照'),('603633','H2首板同流动性量级但基本面反证对照')]:
  s=lookup[c];controls.append({'code':c,'name':s['name'],'reference_price':s['close'],'reference_price_at':T+'T15:00:00+08:00','frozen_at':stamp,'source':s['source'],'snapshot':s,'role':'research_control_not_recommendation','label':label,'market_event_id':f'cnA:{D}:{c}','sector_liquidity_match':'601956与铁流成交额均约1.99亿元；603633约1.64亿元，其余非严格行业匹配，不能解释为已控制全部混杂','results':[]})
 hypotheses=[
  {'id':'H1','version':'weak_market_shadow_v1','frozen_at':stamp,'hypothesis':'低位量能＋尾盘承接的T+2/T+5/T+10超额价格分布和MAE优于高位放量加速','treatment_codes':['603699','603926'],'control_codes':['603037','601956'],'falsification':'在至少20—30个独立计划交易日复核中，同情绪/制度口径处理组中位超额收益不大于对照且MAE无改善则不支持；披露下行尾部和缺失比例，样本不足不宣称优势','boundary':'纽威有尾盘价格推进；铁流尾盘价格持平，仅作为未确认承接修复亚组，不给两者同样的资金身份结论'},
  {'id':'H2','version':'weak_market_shadow_v1','frozen_at':stamp,'hypothesis':'首板后首次分歧承接/回封相较直接追高，次日退出的尾部亏损较小','treatment_codes':['000554'],'control_codes':['000554','603633'],'paired_arms':{'A':'首次可核验分歧回封后按冻结触发观察','B':'D29开盘首个可交易报价的直接追高价格对照；同样受一字/无成交限制，不自动算成交'},'falsification':'A的合法退出可执行净收益分布若在同口径成本后不优于B或尾部风险无改善则不支持；没有逐笔/成交证据两臂仅报告价格观察','boundary':'同股票同D双臂是配对信号，不计两笔独立交易；603633单独风险对照，非同质经营样本'},
  {'id':'H3','version':'weak_market_shadow_v1','frozen_at':stamp,'hypothesis':'板块相对基准逆势强度比仅绝对涨幅更能解释隔夜承接','treatment_codes':['603699','603926','000554'],'control_codes':['603337'],'falsification':'按相同情绪、涨跌幅制度和日期分层后，超额价格与MAE均无改善则不支持；缺行业历史/成分映射时只用沪深300同日期基准并标限制','boundary':'T28为修复；通用设备/汽车零部件分别+3.65%/+3.47%，不是弱市逆势样本。泰山油品参照中国石化/中国石油，不虚构板块指数；不把本轮用于证明弱市假设。'}]
 m=market['market'];fail_ratio=m['standard_non_st_failed_boards']/m['standard_non_st_limit_up_touched'];advance_ratio=m['advance']/(m['advance']+m['decline'])
 cash_events=[{'id':f'{task.replace("_","-")}-{TAG}-cash-observation-v1','task_id':task,'report_id':IDS[task],'T':T,'planned_D':D,'frozen_at':stamp,'decision':'cash_no_qualified_formal_candidate','formal_candidate_count':0,'market_emotion':'震荡','objective_conditions':{'advance_ratio':advance_ratio,'proxy_failed_board_ratio':fail_ratio,'exact_visible_main_failed_ratio':49/108,'first_to_second':{'advanced':5,'denominator':26},'second_to_third':{'advanced':2,'denominator':8},'fifth_to_sixth':{'advanced':0,'denominator':1}},'reason':'宽度修复而冲板兑现偏高；高位断板与单季/现金流反证未解除，入选候选没有同时闭合可执行承接及隔夜风险。空仓不等于研究终止。','comparison_pool_codes':[s['code'] for s in de['deep_recomputed']],'rejected_alternatives':[s['code'] for s in shadow if s['parent_task_id']==task],'strategy_return_pct':None,'account_position_not_asserted':True,'results':[]} for task in ('combined_pair','limitup_single')]
 experiments={'schema_version':'research_shadow_experiment_v1','notice':'研究影子组及对照，非买入建议；独立于recommendations.json，不触发正式买入提醒。','T':T,'planned_D':D,'frozen_at':stamp,'research_rule_version':'weak_market_shadow_v1','report_ids':[IDS['combined_pair'],IDS['limitup_single']],'prior_validation_completed_before_freeze':True,'prior_validation_report_ids':[IDS['volume_price']],'prior_shadow_status':'本任务无D28盘前合格影子组；市场复盘D29纽威/横河尚未成熟，重叠代码日去重','signals':shadow,'controls':controls,'hypotheses':hypotheses,'formal_cash_observations':cash_events,'shared_source_shadow_report_id':IDS['market_review'],'benchmark':{'primary':'sh000300','source':sup['benchmarks']['sh000300']['source'],'horizons':['D close','D+1','D+2','D+5','D+10'],'price_return_anchor':'T已观察收盘；另存有证据的真实模拟入场/合法退出，二者不能混合','sector_proxy_evidence_key':'dated_industry_histories','sector_membership_verified':False},'review':{'first_review_independent_sessions_min':20,'first_review_independent_sessions_max':30,'count_unit':'不同计划交易日；同代码同D的跨任务/配对/重叠持有事件用market_event_id去重','required':['N与独立日期','缺失/未触发/无法成交比例','T+1/T+2/T+5/T+10价格分布及MFE/MAE','封板/炸板与合法T+1退出','同情绪/制度基准或行业流动性对照','可执行净收益含成本，仅数据足够时','正式空仓的机会成本和风险，不当用户账户收益'],'automatic_model_updates':False},'results':[]}
 shadow_text=table(['独立研究影子组，非买入建议','T28参考价/已核上限','模型/排序','支持','未过正式门槛'],[[s['code']+' '+s['name']+' / '+s['parent_task_id'],fmt(s['reference_price'])+'/'+fmt(s['observed_T_upper_price']),s['model']+'/'+str(s['rank']),s['selection_reason'],s['formal_rejection_reason']] for s in shadow])
 shadow_text+='\n\n冻结于'+stamp+'，全部D29开市前。纽威与市场复盘已冻结观察相同，按cnA:2026-10-29:603699关联，不多计交易。本次相较复盘横河替换为铁流：保持普通主板10%对照，横河换手23.675%、20%制度、累计盈利与现金流下降；不是降低重复率硬换。影子组不进recommendations.json，正式弹窗只读取原推荐；不宣称新增APP栏目已实现。'
 shadow_cards='\n\n'.join([f"{s['code']} {s['name']}｜{s['model']}\n参考{s['reference_price']}（T28收盘；非成交），当日上限{s['observed_T_upper_price']}；D29真实上限待带日期行情。{s['trigger']}\n观察失效{s['observation_invalidation_below']}，结构失效{s['structural_invalidation_below']}；{s['abandon']}\n{s['exit_rule']}\n独立风险：{s['independent_risk']}" for s in shadow])
 hypothesis_text=table(['预注册','可证伪问题','对照与边界'],[[h['id'],h['hypothesis'],h['falsification']+'；'+h['boundary']] for h in hypotheses])
 hypothesis_text+='\n\n基准固定同日期沪深300，必要时按强/震荡/弱、综合/打板和制度分层。已取得T28带日期的通用设备BK0545、汽车零部件BK0481历史，作为主营业务研究代理而非已核成分归属。行业总榜仅100/496可见、分页502和塑料历史503保留，不冒称行业全覆盖。对照凯众603037、东贝601956、杰克603337、徕木603633保留原价与相同观察节点。20—30个独立交易日首轮复核，今日新影子N=3个股票-计划日，已完成D29结果N=0、可核成交N=0；不足样本不能声称弱市高胜率。'
 comparisons=table(['真实备选/参考收盘','当前/计划板与角色','支持','未入选正式及相对落后原因'],[
 ['纽威603699/38.39','触板未封；修复待确认','长期低位、尾盘+1.346%、RVOL20 3.542','未收MA20/60、Q3未取得、现金流反证；仅综合影子第1'],
 ['铁流603926/17.06','首板/计划2；跟随待确认','低中位修复、MA60收复、累计现金流改善','未破17.96旧高、Q3单季下降；仅综合影子第2'],
 ['泰山000554/6.63','首板/计划2；成品油可见高度1','突破6.50、换手15.177%、季度盈利改善','油品中国石化-0.544%/中国石油+0.455%，缺主线合力；仅打板影子第1'],
 ['徕木603633/6.36','首板/计划2；连接器跟随','低中位、收MA60、成交额约1.64亿','前三季亏损8496万元、集团担保139.22%净资产；对照保留'],
 ['神驰603109/17.93','首板/计划2；动力修复','RVOL20 5.352、低中位MA60修复','未破未复权17.99旧高、Q3净利-64%；只低位长期研究'],
 ['横河300539/20.94','20%制度，不并10%板数','突破、尾盘推进+3.051%','换手23.675%、累计利润/现金流下滑；复盘影子继续独立，非本组'],
 ['澄星600078/9.42','首板/计划2；磷化工修复','累计利润增长、机构/股通信息可核','未收MA60、现金流同比下降、Q4项目减值反证'],
 ['福莱605488/48.61','换手首板，N天M板不当连板','独立补证封板、尾盘推进','MA20乖离51.923%、Q3净利-69.88%，排除高位加速'],
 ['襄阳000678/17.61','五板/计划6；机器人高度参考','可见最高板','季度仍亏、现金流弱、非低位首二板；不追最高'],
 ['青岛001219/16.48','三板/计划4；食品参考','原低位研究继续上行','当日一字价格不能证明可排到成交；不是新低位样本']])
 new_low=[]
 for c,(sector,invalid,model,reason,risk,key) in NEW_LOW.items():
  s=lookup[c];new_low.append({'id':f'low-position-{TAG}-{c}','date':T,'recorded_at':stamp,'code':c,'name':s['name'],'sector':sector,'primary_model':model,'research_rule_version':'low_position_30d_v1','feature_calculation_version':'unadjusted_MA_including_T_v3','day0_close':s['close'],'day0_change_pct':s['daily_change_pct'],'day0_amount_yi':s['amount_yi'],'day0_turnover_pct':s['turnover_pct'],'day0_rvol20':s['rvol']['20'],'day0_clv':s['clv'],'day0_range_position_pct':s['range_position_pct'],'day0_moving_averages':s['ma'],'invalid_close_below':invalid,'initial_invalidation_basis':'未来收盘跌破T信号日低点；原位冻结，不代表当天可卖或保证成交','snapshot':s,'reason':reason,'risk':risk,'sources':[s['source'],EV,files[key]['source']],'report_ids':[IDS['low_position']],'original_snapshot_verified':True,'eligible_for_model_statistics':True,'is_recommendation':False,'default_watch':False,'observations':[]})
 new_low_text=table(['新增30天研究，非推荐','原收盘/原失效','原模型与依据','反证'],[[s['code']+' '+s['name'],fmt(s['day0_close'])+'/'+fmt(s['invalid_close_below']),s['primary_model']+'；'+s['reason'],s['risk']] for s in new_low])
 low_table=table(['旧代码/名称','原日期','原价','T价','观察%','路径高/低%','原失效/曾破','自然/交易日'],[[v['code']+' '+v['name'],v['reference_date'],v['reference_close'],v['price_observation']['close'],v['close_return_pct'],fmt(v['path_mfe_pct'])+'/'+fmt(v['path_mae_pct']),fmt(v['original_invalid_close_below'])+'/'+str(v['ever_verified_close_below_original_invalid']),str(v['elapsed_natural_days'])+'/'+str(v['elapsed_trading_sessions'])] for v in de['low_validations']])
 low_model_table=table(['原模型','保留N','合格原快照N','成熟30自然日N','30日均值/中位%','曾破失效N'],[[r['model'],r['all_n'],r['eligible_n'],r['mature_30d_eligible_n'],fmt(r['frozen_30d_close_statistics']['mean_pct'])+'/'+fmt(r['frozen_30d_close_statistics']['median_pct']),r['ever_original_invalidation_broken_n']] for r in de['low_model_statistics']])
 low_prev='44条旧样本/43个代码全部日线路径完整，同股不同冻结日按原id保留，重叠信号不当独立成交。1/3/5/10/15/20/30自然日用不晚于目标日最近交易日，另存5/10/20/30交易日；6条虽自然日满30但原快照未验证，合格成熟30日模型N=0、成熟30交易日N=0，不混不同年龄收益宣称30天胜率。凯中002823收13.96，相对13.49为+3.484%，盘中高14.39低13.56，原失效12.25未破；峨眉山000888收9.52，相对10.10为-5.743%，CLV0.131且失MA60，原9.14未破仍保留失败反证，不能只看昨天涨停。新增3条只加库存，未来节点未知。'
 selected={s['code']:s for s in de['dragon_selected']}
 dragon_table=table(['代码/名称','披露期','收盘','买/卖/净万元','机构净万','股通净万','买1/卖1集中%','MA20乖离%/CLV'],[[s['code']+' '+s['name'],s['period'],s['close'],'/'.join(fmt(s[k]/1e4) for k in ('buy_cny','sell_cny','net_cny')),s['institution_net_wan'],s['stock_connect_net_wan'],fmt(s['buy_concentration_top1_pct'])+'/'+fmt(s['sell_concentration_top1_pct']),fmt(s['price_structure']['distance_ma20_pct'])+'/'+fmt(s['price_structure']['clv'])] for s in de['dragon_selected']])
 conditions={'600078':('磷化工首板，非已确认低位核心','D29 9:45/10:30仅在9.07上方且回踩9.42有承接继续观察；不能越过10.45历史压力且放量不推进或项目风险扩散则放弃。'), '001400':('二板/计划三板，铝型材跟随待确认','D29核验88.31及T低点支撑、板块共振，不能一字无普通成交；三日机构净卖不得写成单日。'), '002696':('首板/计划二板，原高位反包','D29只验证11.77的承接，不因机构净买追高；盘中失VWAP/连续开板或主线断层放弃。'), '600838':('五进六失败后的价格反例','D29观察13.99是否能有普通成交并稳定，不能因T28涨5%就把断板改成功晋级；弱开/跌停无流动性放弃。'), '603028':('四进五失败后的反例，不抄底','D29先核10.40是否有承接与可成交价格，T28低点不能当保证止损；延续高标负反馈或盘口缺失直接放弃。')}
 dragon_obs=[{'id':f'dragon-tiger-{TAG}-watch-{c}','date':T,'frozen_at':stamp,'planned_observation_date':D,'code':c,'name':selected[c]['name'],'reference_price':selected[c]['close'],'reference_price_at':T+'T15:00:00+08:00','board_regime':selected[c]['board_regime'],'selected_trade_id':selected[c]['selected_trade_id'],'disclosure_period':selected[c]['period'],'role':role,'condition':cond,'is_recommendation':False,'executed_trade':False,'research_rule_version':'dragon_tiger_original_contract','report_ids':[IDS['dragon_tiger']],'results':[]} for c,(role,cond) in conditions.items()]
 dragon_obs_table=table(['独立龙虎榜观察，非推荐','角色','D29核验/放弃'],[[s['code']+' '+s['name'],s['role'],s['condition']] for s in dragon_obs])
 dragon_prev=table(['原T27披露池制度','有T28价格N','收盘均值%','中位%','收红N'],[[b,v['n'],v['mean_pct'],v['median_pct'],v['positive_n']] for b,v in de['dragon_previous_by_board'].items()])
 dragon_focus=pool_validation(de['dragon_previous_focused_eight'])
 vp_findings='典型5例：①纽威低长期位置、RVOL20 3.542、CLV0.9974和尾盘+1.346支持修复，但差一分钱未封、未收MA20/60否定“确认主升”；②铁流RVOL20 3.391、收复MA60，价格停在板上不是已证实尾盘吸筹；③泰山首次越过6.50、换手15.177%，检验首次分歧而非直接追一字；④横河20%制度突破/尾盘推进与23.675%换手和经营反证并存，保持独立制度；⑤福莱MA20乖离51.923%、Q3利润下降，即使收盘封板也作为高位兑现风险对照。高位爆量滞涨/长上影、放量下跌、缩量上涨等按原冻结形态分层见全28与累计台账，不能只挑成功例子。对买点的影响是等待有时序证据的承接，对退出的影响是冻结合法次日时点；H1/H2/H3见独立实验。'
 provider_note='本轮5575条原始行情、5572只有效股票；120/120收盘OHLC交叉一致，28只深筛。575个日线请求574份当日有效，唯一元道退301139已原公告核实摘牌，不伪造缺失日价格；97份分钟价点带T28日期，含旧低位及上一/本批池，16组重点席位查询成功。3日涨停池及16/20历史池保留原始返回/失败，行业分页502和塑料历史503据实记录。缺完整逐笔、9:25竞价、队列成交、点时证券状态和成本；当前连接可用不等于长期SLA。'
 risk_boundary='正式组0只，不生成正式买入区间或账户交易。研究影子触发/放弃/退出规则单独冻结；D29实际买入最早D30 09:30后可卖，买入日炸板不能当天止损。强开/平开/弱开按预先固定窗口尝试退出，不选择最高价；跌停/停牌/排队未成保持未退出，失效位不是保证成交价。所有组仍模拟验证，不自动转实盘、不融资借款、不推动重仓。'
 common_boundary='不恢复量化，不改变任务时间/启停或运行策略参数。APP无内置大模型推理/自动权重训练；本轮完整分析来自实际研究与原始核验，不用自动扫描冒充深度研究。研究影子仅在完整报告/独立实验文件呈现，正式建仓提示只读取recommendations；研究数据发布不需重装APK。写入、CI/容器、准确SHA的Railway SUCCESS及公开API均成功后才称APP同步。'
 volume_body='\n\n'.join([common,'结论：完整独立量价研究，正式候选0；冻结28条完整新样本，研究影子另存。','一、全A入口/定义\n'+provider_note+'\n'+definitions,'二、先验证全部旧池\n'+previous_text,previous_table,'三、28只完整研究快照\n'+features(de['deep_recomputed']),'四、结构、反例与具体反馈\n'+vp_findings,'五、累计前推与版本\n'+stats_table,stats_text,'六、研究时间窗口\n保留9:30—9:45、9:45—10:30、10:30—11:30、13:00—14:00、14:00—14:30、14:30—15:00六窗。全部深筛及旧池时点见证据，只有价格点不评选最佳收益窗口；触发次序/撤单/成交缺证，窗口策略净收益N/A。新D29信号若买入最早D30卖。','七、独立影子假设，不升级为正式信号\n'+shadow_text,hypothesis_text,'八、原公告反证\n'+official_text,common_boundary])
 low_body='\n\n'.join([common,'结论：完整低位30天研究，新3条、44条旧样本全路径继续，总47条；正式交易候选0。','一、全A入口与替代比较\n'+provider_note+'\n'+definitions,comparisons,'二、新增研究、固定失效\n'+new_low_text,'三、全部旧样本及到期复盘\n'+low_prev,low_table,'四、按原模型统计\n'+low_model_table+'\n30日胜率/盈亏比/10%与20%收益占比因合格成熟N=0而N/A；当前年龄不同的观察不能冒充成熟结果。','五、量价与短期验证\n'+previous_text+'\n'+vp_findings,'六、原公告及反证\n'+official_text,'七、下一验证和独立影子\n泰山验证6.50突破能否守住，神驰/铁流验证MA60修复能否越过17.99/17.96旧高；三条原失效6.03/16.31/15.45不得后移。纽威未收MA20/60，仅修复影子，不冒充已合格30天启动。'+risk_boundary,shadow_text,common_boundary])
 profile_count=len(profiles['profiles']);profile_rows=sum(p['observed_stock_period_rows'] for p in profiles['profiles']);profile_multi=sum(p['distinct_disclosure_dates']>1 for p in profiles['profiles'])
 dragon_body='\n\n'.join([common,'结论：完整龙虎榜研究，78条原因行/67股、8只原始席位及同花顺同周期核验、5条独立条件观察，正式交易候选0。','一、市场/高度/晋级/空间\n'+emotion,ladder,progression,space_text,'二、席位结构及证据\n'+dragon_table,'8/8按TRADE_ID、代码和单日/多日期原因匹配买卖前五，分别与东财汇总与同花顺同周期收盘一致。江顺001400本次为多日，机构-101.242万元、股通+1010.995万元；不得写成T28单日净额。百洋机构+640.673万元、总榜净买8148.84万元仍是高位反包风险。桂发祥机构净卖7422.965万元；九百/赛福天总榜净卖4013.85/3598.15万元；多伦股通净买1619.042万元同时总榜净卖5821.80万元并跌停，否定“股通净买必涨”。营业部/机构/股通标签不证明资金身份、锁仓、做T或对倒。',f'三、公共席位画像\nT27/T28共{profile_count}个准确营业部代码/名称画像、{profile_rows}条股票-披露期观察、{profile_multi}个跨日；另{len(profiles["generic_channel_rows_not_merged_as_accounts"])}条机构/股通通用行不合并成账户。原T26及更早画像保留在各自原报告。当前可观察关联股票/板数/位置，不足以推断持仓周期、做T、兑现或稳定风格，不生成标签胜率。','四、先验证原T27完整77股\n'+dragon_prev+'\n76只取得T28价格，301139原公告核实10月28日摘牌，保留不可交易/无报价结果；不删样本、不当0收益。上表只按制度分别计算76个可观察值，分母缺项披露。',dragon_focus,'五、5只D29观察卡\n'+dragon_obs_table+'\n逐只须核D29竞价/开盘/量价/板块/承接，不能用收盘后披露反填T28盘中；D29买入最早D30卖，缺实时盘口只观察，不默认成交。','六、量价共振/背离与样本统计\n'+vp_findings+'\n席位组合×位置×板块×情绪×封板质量的可执行N、胜率、净收益/盈亏比/MAE与退出质量均待验证。引用VP同源样本不再重复计数。',official_text,provider_note,common_boundary])
 limitup_body='\n\n'.join([common,'结论：D29正式打板0只，空仓；独立研究影子第1泰山石油000554，非买入建议，不发正式买入信号。规则limitup_single_v2不降低风险门槛。','一、先情绪后否决\n'+emotion,'二、高度/主线/空间/逐层晋级\n'+ladder,progression,space_text,'三、独立扫描与备选比较\n5572只有效入口、120广泛、28深筛，覆盖至少10个研究板块；ST/退市、新股无上限、一字排队、高位连续缩量加速与爆量滞涨先否决；20%/30%与10%制度分开。',comparisons,'四、正式否决及空仓观测事件\n虽宽度修复，精确可见触板未封49/108，高标九百五进六失败、多伦四进五跌停，油品参照中国石化-0.544%/中国石油+0.455%缺合力，泰山营收下降且放量15%换手需验证首次分歧。其余徕木亏损担保、神驰单季利润弱、福莱高位乖离优先否决。正式空仓事件与完整比较池独立冻结；不是因未来竞价尚未知就停止研究。','五、研究影子、参考价与固定条件\n'+shadow_text,shadow_cards,'六、前推假设及统计\n'+hypothesis_text,'七、上一样本/退出\nD28正式v2为0，累计正式v2候选0、成交0；v1仅龙溪600592原16.20及原未入场条件保留，新的日线价格观察与原参考分别记录，不改v1成v2。首板/二板/回封、情绪/高度/主线/空间/长假分别统计；封板与赚钱率分开，未成熟影子不制造胜率。'+risk_boundary,previous_text,stats_table,stats_text,'八、事实、风险与逐股分母\n'+official_text,denominator_table,provider_note,common_boundary])
 deps=table(['同T完整模块','报告id','支持/反对'],[['market_review',IDS['market_review'],'5572→120→28、宽度修复，但冲板兑现高；原报告正式0与两条研究影子保留'],['volume_price',IDS['volume_price'],'新28全池：低位修复/尾盘推进支持影子；旧28虽中位+1.808仍13只最低≤-5%反对直接追高'],['low_position',IDS['low_position'],'44条旧全路径＋新3；铁流/泰山低中位，纽威未收MA20/60不冒充确认趋势'],['dragon_tiger',IDS['dragon_tiger'],'原始席位8只交叉核验，股通净买与跌停并存；缺榜不编席位，买方标签不证明承接']])
 combined_body='\n\n'.join([common,'结论：正式综合双标0只；研究影子前2为纽威股份603699、铁流股份603926。打板另按v2正式0、研究影子泰山000554；两套实验/回执/统计独立。影子不是买入建议。','一、四份同T完整前置\n'+deps+'\n复用market_review完整报告及真实completed，实际补做其余三个完整模块；自动扫描/配置审计/eligible=false不作前置。量化已取消。','二、独立全池/替代与重复\n'+provider_note+'\n'+definitions,features(de['deep_recomputed']),comparisons,'T28深筛与可取的T22/23/26/27四日报告重叠5/28=17.857%（百洋/优德/凯众/福莱/宇树）；5日窗口缺T21、10日窗口缺更多，严格5/10日重复率N/A。正式本组5/10日无新候选，不把研究池重复率当正式推荐率；重选纽威是新尾盘/对照证据，市场原影子与本任务关联去重。','三、三日情绪/晋级/空间\n'+emotion,ladder,progression,space_text,'四、先验证上一批，量价发现及累计\n'+previous_text,previous_table,vp_findings,stats_table,stats_text,'五、正式空仓事件与新影子\n'+shadow_text,shadow_cards,'六、预注册对照，不做事后选赢家\n'+hypothesis_text,'七、低位长期和资金反证\n'+new_low_text+'\n'+low_prev,dragon_table,official_text,'八、执行边界与下一交易日重点\n'+risk_boundary+'\nD29重点核验修复能否转承接、纽威MA20下修复是否失败、铁流16.40—16.49能否承接、泰山首板后第一次分歧及油品同伴、高标襄阳/青岛/光洋负反馈是否扩散。任何日内实际买入后失效仍须承受T+1限制；影子不能触发实盘提示。',provider_note,common_boundary])
 bodies={'volume_price':volume_body,'low_position':low_body,'dragon_tiger':dragon_body,'limitup_single':limitup_body,'combined_pair':combined_body}
 titles={'volume_price':'量价完整研究｜10月28日全池验证、28条冻结与影子假设','low_position':'低位启动30天｜10月28日新增3条、44条旧样本全量验证','dragon_tiger':'龙虎榜完整研究｜10月28日8只席位核验、77条旧池不删失败','limitup_single':'打板v2｜10月29日正式空仓，泰山石油为独立研究影子','combined_pair':'综合双标｜10月28日四项齐备；正式空仓、纽威与铁流影子研究'}
 summaries={'volume_price':'5572→120→28；旧28中位+1.808%，13只最低≤-5%；v4 196条/7日，不当实盘收益。','low_position':'新增泰山、神驰、铁流3条非推荐；44条旧路径完整、合格成熟30日N=0。','dragon_tiger':'78理由行/67股、8只席位与同花顺同周期核验；旧77保留摘牌1只，76只可观察。','limitup_single':'D29正式0只；泰山000554独立研究影子、盘前冻结，不触发正式信号。','combined_pair':'同T四项完整齐备；正式0只，影子纽威603699/铁流603926，原始条件独立冻结。'}
 rules={'volume_price':'volume_price_close_v4','low_position':'low_position_30d_v1','dragon_tiger':'dragon_tiger_original_contract','limitup_single':'limitup_single_v2','combined_pair':'combined_limitup_watch_v5'}
 sources=list(dict.fromkeys([EV,EXP,'docs/research/market-review-2026-10-28-evidence.json','https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml','https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData','https://data.eastmoney.com/stock/tradedetail.html','https://data.10jqka.com.cn/market/longhu/','https://api3.cls.cn/share/article/2517769','https://qt.gtimg.cn/q=sh603699,sh603926,sz000554']+[f['source'] for f in files.values()]))
 new_reports=[];new_receipts=[]
 for task,body in bodies.items():
  rid=IDS[task];run_id=f"{task.replace('_','-')}-{TAG}-scheduled-close-{'v2' if task=='limitup_single' else 'v1'}"
  r={'id':rid,'date':T,'market_date':T,'task_id':task,'track':task if task in ('volume_price','low_position','dragon_tiger') else 'market_review','run_id':run_id,'title':titles[task],'summary':summaries[task],'body':body.strip(),'sources':sources,'report_type':'full_trading_research' if task=='combined_pair' else 'full_daily_research','eligible_for_integrated_research':task!='limitup_single','analysis_completed':True,'status':'completed','published_at':stamp,'recorded_at':stamp,'market_data_cutoff_at':T+'T15:00:00+08:00','data_cutoff_at':stamp,'planned_entry_date':D,'earliest_legal_exit_date_if_bought':EXIT,'research_rule_version':rules[task],'provenance':'contemporaneous_after_close_research','candidate_count':0,'recommendation_ids':[],'evidence_file':EV,'full_scan_count':5572,'broad_pool_count':120,'deep_pool_count':28,'codes':[s['code'] for s in de['deep_recomputed']],'shadow_experiment_file':EXP}
  if task=='low_position':r.update(new_sample_count=3,new_sample_ids=[s['id'] for s in new_low],previous_samples_verified=44,codes=sorted({s['code'] for s in low['items']+new_low}))
  if task=='dragon_tiger':r.update(observation_count=5,signal_observations=dragon_obs,codes=[s['code'] for s in de['dragon_selected']])
  if task in ('combined_pair','limitup_single'):r.update(strategy='limitup_single_v2' if task=='limitup_single' else 'combined_limitup_watch',group='close',decision='cash_no_qualified_candidate',formal_cash_observation=next(c for c in cash_events if c['task_id']==task),research_shadow_candidates=[s for s in shadow if s['parent_task_id']==task],research_shadow_count=sum(s['parent_task_id']==task for s in shadow))
  if task=='combined_pair':r.update(dependency_report_ids=[IDS[t] for t in ('market_review','volume_price','low_position','dragon_tiger')],cohort_label='综合盘后组')
  if task=='limitup_single':r.update(full_20_session_space_reference_available=False)
  new_reports.append(r);new_receipts.append({'id':run_id+'-completed','run_id':run_id,'task_id':task,'date':T,'trigger':'scheduled','started_at':START,'completed_at':stamp,'recorded_at':stamp,'status':'completed','summary':summaries[task],'report_ids':[rid],'recommendation_ids':[],'analysis_completed':True,'eligible_for_integrated_research':task!='limitup_single','delivery_status':'repository_prepared_not_yet_ci_or_production_verified','sources':[EV,EXP]})
 # Remaining append operations are assembled below; one Git commit publishes all.
 research['items'].extend(new_reports);runs['items'].extend(new_receipts)
 for s in low['items']:
  obs=next(r for r in de['low_validations'] if r['origin_cohort_id']==s['id'])
  s.setdefault('observations',[]).append({**obs,'recorded_at':stamp,'calculated_at':de['calculated_at']})
 low['items'].extend(new_low);low['updated_at']=stamp
 vp['items'].extend([
  {'id':'volume-price-20261027-validation-20261028-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
   'origin_cohort_id':'volume-price-20261027-close-v1-cohort','rule_version':'volume_price_close_v4','full_validation_completed':True,
   'full_pool_summary':de['previous_whole_pool_summary'],'full_pool_validations':de['previous_whole_pool'],'executed_trade_count':0,
   'eligible_for_model_statistics':False,'statistical_scope':'price_observation_not_executable_strategy'},
  {'id':'volume-price-historical-validation-20261028-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
   'cohort_ids':[r['origin_cohort_id'] for r in cum['vp_all_cohort_validations']],'frozen_sample_count':285,'matched_original_close_count':284,
   'rule_version_groups':cum['vp_by_rule_version'],'evidence_file':EV,'executed_trade_count':0,'eligible_for_model_statistics':False,
   'note':'Frozen cohorts and versions remain distinct; descriptive price observations, no hypothetical fills or net returns.'},
  {'id':'volume-price-20261028-close-v1-cohort','date':T,'task_id':'volume_price','frozen_at':stamp,'report_ids':[IDS['volume_price']],
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
  r.setdefault('results',[]).append({'id':r['id']+'-price-review-20261028','date':T,'market_date':T,'recorded_at':stamp,
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
   'evidence_status':'verified_daily_price_observation_not_trade_return','fact_note':f"原日期{r['reference_date']}，T28收盘{r['price_observation']['close']}，原失效位{r['original_invalid_close_below']}；曾收破={r['ever_verified_close_below_original_invalid']}。",
   'validation':['原自然日和交易日节点独立，未成熟不补结果','以原失效位核查收盘路径，未以价格回升抹去失败'],
   'risk':'价格观察不证明实际成交、固定退出净收益、资金身份或30天稳定胜率。','report_ids':[IDS['low_position']],
   'sources':[raw['daily_histories'][stock['code']]['source'],EV]}
  stock['history'].append(ep);stock_updates.append({'code':stock['code'],'history_id':ep['id']})
 for s in new_low:
  assert not any(r['code']==s['code'] for r in catalog['items'])
  ep={'id':f"research-stock-{s['code']}-{TAG}-origin-v1",'date':T,'recorded_at':stamp,'title':'新增30天研究样本，非短线交易推荐',
   'reason':s['reason'],'evidence_status':'verified_closed_daily_snapshot_with_official_filing_risk_notes',
   'fact_note':f"{s['name']}T28收盘{s['day0_close']}，原失效收盘位{s['invalid_close_below']}；未来节点尚未知。",
   'validation':['按1/3/5/10/15/20/30自然日与5/10/20交易日滚动前推','验证放量后的承接与板块同步，不将形态认定账户身份'],
   'risk':s['risk'],'report_ids':[IDS['low_position']],'sources':s['sources']}
  catalog['items'].append({'code':s['code'],'name':s['name'],'sector':s['sector'],'role':'research','default_watch':False,'history':[ep]})
  stock_updates.append({'code':s['code'],'history_id':ep['id']})
 catalog['updated_at']=stamp
 base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 evidence={'market_date':T,'planned_entry_date':D,'earliest_legal_exit_if_bought':EXIT,'actual_started_at_utc':START,'actual_completed_at':stamp,'base_main':base,
  'reused_market_report_id':IDS['market_review'],'reused_market_report_sha256':hashlib.sha256(json.dumps(market_report,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
  'initial_failure_results':initial_failures,'initial_failed_records':initial_failed_records,'sina_pages':raw['sina_pages'],'daily_histories':raw['daily_histories'],'minute_price_points':raw['minute_price_points'],
  'retry_checks':ext,'lhb_lists':raw['lhb_lists'],'seat_queries':raw['seat_queries'],'limit_up_pools':raw['limit_up_pools'],
  'derived':de,'cumulative':cum,'supplement':sup,'official_queries':official,'extra_official_queries':extra,
  'prefreeze_official_queries':load('tmp/combined-20261028-prefreeze-announcements.json'),
  'delisting_exact_name_query':load('tmp/combined-20261028-delist-name-query.json'),
  'official_files':{k:{a:b for a,b in r.items() if a not in ('pdf_path','text_path','local_pdf','local_text')} for k,r in files.items()},
  'official_verified_fact_notes':fact_notes,'ths_summary_rows':ths['tables'][5],'ths_source':ths['source'],'seat_profiles':profiles,
  'raw_quoted_upper_prices':upper,'exact_main_price_limit_verification':exact,
  'industry_top_100':load('tmp/combined-20261028-industry-quotes.json'),'industry_full_attempt':load('tmp/combined-20261028-industry-full.json'),
  'industry_retry':load('tmp/combined-20261028-industry-retry.json'),'dated_industry_histories':load('tmp/combined-20261028-industry-histories.json'),
  'new_low_samples':new_low,'new_dragon_observations':dragon_obs,'stock_history_updates':stock_updates,'research_shadow_experiments':experiments,
  'limitations':['16/20 prior session pools, full historical highest and cycle start unknown','No 9:25 auction, full historical minute OHLC/ticks, queue/order fills, exhaustive point-in-time security status or calibrated transaction costs',
   '301139 delisted T28: retained without exchange price or zero return; original failure attempts retained',
   'Industry top list only 100/496; subsequent pages fail, two dated sector histories are research proxies, constituent membership unverified',
   'Old missing anchors and unverified/retrospective samples retained outside eligible statistics',
   'No executable win rate, hypothetical fill, automatic strategy weights or quant research; no shadow in formal recommendations']}
 encoded=gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)
 exp_encoded=json.dumps(experiments,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
 manifest={'base_main':base,'market_date':T,'planned_entry_date':D,'actual_started_at_utc':START,'analysis_completed_at':stamp,
  'new_report_ids':[r['id'] for r in new_reports],'reused_report_ids':[IDS['market_review']],'new_recommendations':0,
  'new_low_samples':len(new_low),'old_low_observations_appended':44,'new_volume_samples':28,'old_frozen_recommendation_results_appended':len(recs['items']),
  'stock_history_updates':stock_updates,'evidence_file':EV,'evidence_sha256':hashlib.sha256(encoded).hexdigest(),
  'shadow_experiment_file':EXP,'shadow_experiment_sha256':hashlib.sha256(exp_encoded.encode()).hexdigest(),
  'research_shadow_count':3,'formal_cash_observation_count':2,'hypothesis_ids':['H1','H2','H3'],
  'task_registry_changed':False,'schedules_changed':False,'quant_research_restored':False}
 assert datetime.fromisoformat(START)<=datetime.fromisoformat(stamp)<=datetime.now(timezone.utc)
 documents={'backend/data/research.json':research,'backend/data/task_runs.json':runs,'backend/data/volume_price_samples.json':vp,
  'backend/data/low_position_samples.json':low,'backend/data/recommendations.json':recs,'backend/data/research_stocks.json':catalog,
  'app/src/main/assets/research_stocks.json':catalog,'docs/research/combined-pair-20261028-publication-manifest.json':manifest}
 serialized={p:json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n' for p,d in documents.items()}
 serialized[EXP]=exp_encoded
 # Finish all parsing and serialization first; one repository commit is atomic.
 for p,content in serialized.items():
  target=ROOT/p;temp=target.with_suffix(target.suffix+'.tmp');temp.write_text(content);temp.replace(target)
 (ROOT/EV).write_bytes(encoded)
 for task,body in bodies.items():(ROOT/f'docs/research/{IDS[task]}.md').write_text('# '+titles[task]+'\n\n'+body.strip()+'\n\n来源：\n\n'+'\n'.join('- '+s for s in sources)+'\n')
 print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
