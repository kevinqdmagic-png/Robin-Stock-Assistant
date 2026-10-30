"""Assemble analyst-reviewed T30 research, immutable D1102 plans and real receipts.

This dated archival program does not rank stocks or place trades. The separate
review file contains the explicit analytical decisions; all evidence must exist
and prior shadows must have been checked before a new freeze is possible.
"""
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import Counter
import copy, gzip, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from learning_loop import is_session,nth_session_after
from prepare_completion_20261023 import pct
T='2026-10-30'; D='2026-11-02'; EXIT='2026-11-03'; TAG='20261030'
START='2026-10-30T09:38:34+00:00'
EV=f'docs/research/combined-pair-{TAG}-evidence.json.gz'
EXP='docs/research/shadow-experiments-20261102-v1.json'
OLD_EXP='docs/research/shadow-experiments-20261030-v1.json'
VALIDATION='docs/research/shadow-validation-20261030-v1.json'
TASKS=('market_review','volume_price','low_position','dragon_tiger','combined_pair','limitup_single')
IDS={t:f'{t.replace("_","-")}-{TAG}-close-'+('v2' if t=='limitup_single' else 'v1') for t in TASKS}
def load(p): return json.loads((ROOT/p).read_text())
def fmt(v): return 'N/A' if v is None else str(round(v,3)) if isinstance(v,(float,int)) and not isinstance(v,bool) else str(v)
def table(h,rows):
    return '\n'.join(['|'+'|'.join(h)+'|','|'+'|'.join('---' for _ in h)+'|']+['|'+'|'.join(fmt(v).replace('|','/') for v in r)+'|' for r in rows])
def main():
    review=load('tmp/analyst-combined-20261030.json')
    assert review['analysis_reviewed'] is True
    research=load('backend/data/research.json');runs=load('backend/data/task_runs.json')
    low=load('backend/data/low_position_samples.json');vp=load('backend/data/volume_price_samples.json')
    recs=load('backend/data/recommendations.json');catalog=load('backend/data/research_stocks.json')
    for t in TASKS[1:]:
        assert not any(r.get('task_id')==t and r['date']==T and r.get('report_type') in ('full_daily_research','full_trading_research') for r in research['items']), 'reuse existing '+t
    mr=next(r for r in research['items'] if r['id']==IDS['market_review'])
    assert mr['eligible_for_integrated_research'] is True
    assert any(r.get('status')=='completed' and r.get('report_ids')==[mr['id']] for r in runs['items'])
    raw=load(f'tmp/combined-{TAG}-raw.json');original_raw=copy.deepcopy(raw)
    ext=load(f'tmp/combined-{TAG}-extension.json')
    for k in ['daily_histories','minute_price_points','seat_queries','limit_up_pools']:
        raw[k].update(ext.get(k,{}))
    de=load(f'tmp/combined-{TAG}-derived.json');cum=load(f'tmp/combined-{TAG}-statistics.json')
    sup=load(f'tmp/combined-{TAG}-supplement.json');quote=load(f'tmp/combined-{TAG}-quote-upper-check.json')
    exact=load(f'tmp/combined-{TAG}-exact-main-limit-check.json');ths=load(f'tmp/combined-{TAG}-ths.json')
    files=load(f'tmp/combined-{TAG}-official-files.json');profiles=load(f'tmp/combined-{TAG}-seat-profiles.json')
    old_validation=load('tmp/shadow-validation-20261030.json');old_exp=load(OLD_EXP)
    market=load('docs/research/market-review-2026-10-30-evidence.json')
    assert de['crosscheck']['recomputed_broad']==120 and len(de['deep_recomputed'])==28 and not de['crosscheck']['ohlc_mismatches']
    assert de['low_summary']['count']==len(low['items']) and de['low_summary']['all_paths_complete']
    assert de['previous_whole_pool_summary']['n']==28
    assert all(s['seat_reconciliation']['matched'] and s['ths_close_match'] for s in de['dragon_selected'])
    assert old_validation['summary']['observed_n']==3
    now=datetime.now(timezone.utc);stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    assert now<datetime.fromisoformat(D+'T09:30:00+08:00')
    assert datetime.fromisoformat(old_validation['recorded_at'])<now
    assert all(is_session(date.fromisoformat(d)) for d in [T,D,EXIT])
    sectors=review['sectors'];lookup={s['code']:s for s in de['broad_recomputed']}
    for s in de['deep_recomputed']:
        s.update(sector_research_label=sectors[s['code']],signal_frozen_at=stamp,rule_version='volume_price_close_v4',is_recommendation=False)
    daily={c:r['bars'] for c,r in raw['daily_histories'].items() if r.get('ok')}
    def features(rows):
        return table(['代码/名称','研究板块','收盘/涨跌%','RVOL5/10/20','换手%/变化pp','20/60/120位置%','MA5/10/20/60','CLV/14时后%'],[[s['code']+' '+s['name'],sectors.get(s['code'],'其他'),fmt(s['close'])+'/'+fmt(s['daily_change_pct']),'/'.join(fmt(s['rvol'][str(n)]) for n in [5,10,20]),fmt(s['turnover_pct'])+'/'+fmt(s['turnover_change_pct_points']),'/'.join(fmt(s['range_position_pct'][str(n)]) for n in [20,60,120]),'/'.join(fmt(s['ma'][str(n)]) for n in [5,10,20,60]),fmt(s['clv'])+'/'+fmt(s['tail_1400_close_pct'])] for s in rows])
    def observations(rows):
        return table(['代码/名称','开盘观察%','最高观察%','最低观察%','收盘观察%'],[[s['code']+' '+s['name'],s.get('open_pct'),s.get('mfe_pct'),s.get('mae_pct'),s.get('close_pct')] for s in rows])
    facts=table(['代码','原公告事实及反证'],[[r['code'],r['fact']] for r in review['facts']])
    qualitative=table(['完整深筛','模型/角色','支持','反证与正式否决'],[[s['code']+' '+s['name'],review['deep_reviews'][s['code']]['model'],review['deep_reviews'][s['code']]['support'],review['deep_reviews'][s['code']]['against']] for s in de['deep_recomputed']])
    price_def='全日RVOL=当日量/此前5、10、20个完整交易日均量，分母不含T，不称盘中量比。本轮各模块MA与区间位置均用未复权日线且含T；历史独立市场报告前复权/此前窗口保持原样，不混算。CLV=(收盘−最低)/(最高−最低)，高低相同N/A。分钟为带日期的离散价格点和累计量额，不是分钟OHLC、逐笔、竞价、买卖队列或成交证据。'
    common=f'研究已收盘T={T}，行情截止北京时间15:00；实际冻结/分析完成{stamp}。计划D={D}；若D买入，最早{EXIT}可卖。参考价不等于成交。'+price_def
    provider=f"本次实际执行market_review完整模块并在同次原子发布中复用其真实报告，补齐其他三模块。正价入口{market['coverage']['positive_quote_entry_count']}条，4条当日有效OHLCV缺失单列（688121/601326/688496/605258），{market['coverage']['same_day_positive_OHLCV_count']}条有效当日成交报价；广泛120、深筛28，{len(set(sectors.values()))}个研究标签。日线当前有效{sum(r.get('ok',False) for r in raw['daily_histories'].values())}/{len(raw['daily_histories'])}，日期合格分钟价点{sum(r.get('ok',False) for r in raw['minute_price_points'].values())}/{len(raw['minute_price_points'])}。已发布T29未复权历史只用带T30日期的腾讯真实OHLCV追加，新代码单独取得历史；21条新取得完整日线与追加历史OHLCV交叉一致。采集分阶段落盘，无连接中断结果被采用。301139已摘牌，688121当日日线缺失；均不在本日深筛/旧50低位必需路径。两次席位BUY超时原返回保留并已重试成功，青岛001219两源无T30榜故不补造席位。13只真实重点、26项有效买卖查询全部金额核对且13/13同花顺同披露期收盘一致。失败、缺失及重试均保留，不把有限入口或价格点冒充全市场逐笔监控。"
    p=de['previous_whole_pool_summary']
    previous=f"先验证T29原28只全池，观察N={p['n']}，收红{p['positive_n']}只；收盘均值{p['mean_pct']}%、中位{p['median_pct']}%，平均最高{p['mean_mfe_pct']}%、平均最低{p['mean_mae_pct']}%，{p['mae_le_minus5_n']}只最低相对前收≤−5%。同一池跨报告只关联一次，不计为28笔交易。正式综合/打板原均0只，未补造入场。"
    shadow_validation_text=table(['D30原影子','收盘观察%','最高/最低观察%','原条件核验','成交/净收益'],[[r['code']+' '+r['name'],r.get('close_observation_pct'),fmt(r.get('MFE_price_observation_pct'))+'/'+fmt(r.get('MAE_price_observation_pct')),r.get('entry_status')+'；'+'；'.join(r.get('trigger_evidence',[])),'无已核成交；N/A'] for r in old_validation['signals']])
    shadow_validation_text+='\n\n以原T29收盘为价格锚；本批D30三只均未满足原必要条件，实际成交0。T+1=10月30日，T+2=11月2日；原计划D30买入最早11月2日可卖，未发生的买入不产生假想退出。此前T28/D29的三只及全部原对照继续追加T30结果，原未触发状态不变；已观察2个独立计划交易日、6个股票-D事件。新计划D1102入场最早11月3日卖出，不能混用两批时间轴。逐股及所有原对照见'+VALIDATION+'。'
    shadow_validation_text+='\n\n'+table(['更早计划D','原信号','至T30收盘观察%','原入场状态'],[[batch['planned_D'],r['code']+' '+r['name'],r['close_observation_pct'],r['entry_status']] for batch in old_validation['all_frozen_experiment_followups'] for r in batch['signals']])
    shadow_validation_text+='\n\n'+table(['独立市场影子D','股票','至T30收盘观察%','与综合共用事件'],[[r['planned_D'],r['code']+' '+r['name'],r['close_observation_pct'],r['shared_market_event_with_combined']] for r in old_validation['independent_market_shadow']])
    shadow_validation_text+='\n\n中国卫星与综合同股同D关联；广联航空及横河精密原市场影子各自保留原条件不重建，不把日线观察当成交。'
    cumulative=table(['版本','原冻结条目','合格前推条目','独立原日期','T+1可观察N','均值/中位%','T+2 N','均值/中位%'],[[k,v['frozen_sample_count'],v.get('forward_eligible_count'),v['independent_dates'],v['horizons']['1']['n'],fmt(v['horizons']['1']['mean_pct'])+'/'+fmt(v['horizons']['1']['median_pct']),v['horizons']['2']['n'],fmt(v['horizons']['2']['mean_pct'])+'/'+fmt(v['horizons']['2']['median_pct'])] for k,v in cum['vp_by_rule_version'].items()])
    cumulative+='\n\n10月21日后补的28条历史材料单列retrospective，不进入前推统计；其他缺原价样本保留且不补造。全部1/2/3/5/10/20/30节点及原形态、价格位置、制度分层保留。价格观察条目可能有重叠持有期，非独立交易数。真实可执行成交N=0；净收益、胜率、盈亏比、费用滑点及退出质量N/A。20bp旧占位未经数量、最低佣金和成交校准，不作净收益。'
    days=[]
    for day in ['2026-10-28','2026-10-29',T]:
        m=load(f'docs/research/market-review-{day}-evidence.json')['market']
        days.append([day,m['standard_non_st_limit_up_sealed'],m['standard_non_st_failed_boards'],m['standard_non_st_limit_down'],m['advance'],m['decline'],m['amount_yuan_full_scan']/1e8])
    emotion=table(['日期','主板阈值封板代理','触板未封代理','跌停代理','上涨','下跌','全A成交亿元'],days)
    emotion+=f"\n\n三日同口径新浪普通非ST主板阈值代理，不与媒体全制度拼分母。T30另取得当日实际上下限：核验{exact['price_limit_verified_n']}/{exact['candidate_count']}只入口股票，可见封板{exact['closed_at_upper_n']}、触板{exact['touched_upper_n']}、触板未封{exact['touched_not_sealed_n']}、收盘跌停{exact['closed_at_lower_n']}，未核清代码{exact['unverified_codes']}。仅此入口范围，不声称完整点时证券主表。"
    m=market['market'];up=m['advance']/(m['advance']+m['decline']);failed=m['standard_non_st_failed_boards']/m['standard_non_st_limit_up_touched']
    assert 1-up>=.65 and failed>=.4
    emotion+=f'\n\n沿用已冻结weak_market_shadow_v1情绪定义：下跌占涨跌家数≥65%且代理炸板率≥40%为弱；上涨≥65%且代理炸板率≤25%为强，其余震荡。T30上涨{up*100:.3f}%、代理炸板{failed*100:.3f}%，分类弱。创业板−4.13%、科创50−5.48%、三进四断层及旧池回落为负反馈；消费/航运/银行部分相对强为正证据，仍不足以把全市场定为强势。'
    ladder=table(['普通主板梯队','家数','股票'],[[k,len(v),'、'.join(s['code']+s['name'] for s in v)] for k,v in de['board_ladder'][T]['layers'].items()])
    progression=table(['晋级层级','T29事前完整分母','晋级','断板','缺失','比例%'],[[k,v['prior_full_denominator'],v['advanced'],v['broken'],v['missing'],v['verified_advancement_pct']] for k,v in de['progression_main_10pct'].items()])
    denominators=table(['原层级','冻结股票','T30结果','收盘'],[[k,r['code']+' '+r['name'],r['status'],r['T_close']] for k,v in de['progression_main_10pct'].items() for r in v['rows']])
    progression+='\n\n分母为T29已发布并逐股核验的完整普通主板各层池，不按T30赢家倒推；各制度分开。断板并不等于收跌，逐股原分母完整保留。'
    sp=cum['twenty_prior_sessions_space_reference']
    space=f"空间板以T之前20交易日为固定参照，现取得{sp['available_pools']}/20池，缺{sp['missing_session_pools']}；可见最高{sp['visible_maximum_boards']}，完整20日最高和情绪周期起点仍未知。不能从今日梯队宣称空间已经打开，也不把N天M板当连续M板。"
    comparisons=table(['候选/备选','当前/计划板及角色','比较理由/独立风险'],[[r['code']+' '+lookup[r['code']]['name']+'/'+fmt(lookup[r['code']]['close']),r['role'],r['reason']] for r in review['comparisons']])
    shadows=[]
    for spec in review['shadows']:
        c=spec['code'];s=lookup[c];sym=('sh' if c.startswith('6') else 'sz')+c;f=quote['provider_fields'][sym]
        assert f[30].startswith(TAG) and abs(float(f[3])-s['close'])<.011
        batches=quote.get('batches',[])+quote.get('additional_touch_and_negative_batches',[])
        batch=next(b for b in batches if sym in b.get('provider_fields',{}))
        sh={**spec,'id':f"shadow-{spec['parent_task_id'].replace('_','-')}-20261102-{c}-v1",'role':'research_shadow','is_recommendation':False,
            'formal_buy_signal':False,'send_trade_notification':False,'report_ids':[IDS[spec['parent_task_id']]],'T':T,'date':T,'planned_entry_date':D,
            'name':s['name'],'signal_frozen_at':stamp,'recorded_at':stamp,'freeze_phase':'before_planned_session_open','eligible_forward_observation':True,
            'market_event_id':f'cnA:{D}:{c}','board_regime':s['board_regime'],'daily_limit_pct':10,'reference_price':s['close'],
            'reference_price_at':T+'T15:00:00+08:00','reference_is_fill':False,'provider_quote_timestamp':f[30],
            'observed_T_upper_price':float(f[47]),'observed_T_lower_price':float(f[48]),'D_actual_upper_price':None,
            'D_upper_status':'Require date-verified D provider field, never assume previous close times 1.1',
            'research_rule_version':'weak_market_shadow_v1','parent_rule_version':'limitup_single_v2' if spec['parent_task_id']=='limitup_single' else 'combined_limitup_watch_v5',
            'market_emotion':'弱','evidence_available_at':[{'source':raw['daily_histories'][c]['source'],'retrieved_at':raw['daily_histories'][c]['retrieved_at']},{'source':batch['source'],'retrieved_at':batch['retrieved_at']}]+[{'source':files[k]['source'],'retrieved_at':files[k]['retrieved_at']} for k in spec.get('official_fact_keys',[])],
            'sources':[raw['daily_histories'][c]['source'],batch['source'],EV]+[files[k]['source'] for k in spec.get('official_fact_keys',[])],
            'reference_stocks':review['reference_stocks'],'earliest_legal_exit_if_bought_at':EXIT+'T09:30:00+08:00',
            'exit_rule':f'D买入最早{EXIT}可卖；综合在该日09:45首个可证明能成交报价尝试退出，打板为09:30首个可证明能成交报价。强/平/弱开采用同一固定窗口；跌停、停牌或排队未成交则保留未退出并顺延，不择最高价。买入当日失效不能当日卖。',
            'research_benchmark':'sh000300','entry_triggered':None,'entry_fill_verified':None,'sealed_or_failed_after_entry':None,
            'executable_net_return_pct':None,'weekend_overnight_sample':False,'signal_weekend_gap':True,'long_holiday_sample':False,
            'signal_T_horizon_dates':{str(h):nth_session_after(date.fromisoformat(T),h).isoformat() for h in [1,2,5,10]},
            'planned_D_horizon_dates':{str(h):nth_session_after(date.fromisoformat(D),h).isoformat() for h in [1,2,5,10]},'results':[]}
        shadows.append(sh)
    controls=[]
    for spec in review['controls']:
        s=lookup[spec['code']]
        controls.append({**spec,'name':s['name'],'reference_price':s['close'],'reference_price_at':T+'T15:00:00+08:00','frozen_at':stamp,
            'role':'research_control_not_recommendation','market_event_id':f"cnA:{D}:{s['code']}",'snapshot':s,'source':s['source'],'results':[]})
    cash=[{'id':f'{task.replace("_","-")}-{TAG}-cash-observation-v1','task_id':task,'report_id':IDS[task],'T':T,'planned_D':D,'frozen_at':stamp,
           'decision':'cash_no_qualified_formal_candidate','formal_candidate_count':0,'market_emotion':'弱',
           'objective_conditions':{'advance_ratio':up,'proxy_failed_board_ratio':failed,'main_progression':{k:{q:r[q] for q in ['prior_full_denominator','advanced','broken','missing']} for k,r in de['progression_main_10pct'].items()}},
           'reason':review['formal_cash_reason'],'comparison_pool_codes':[s['code'] for s in de['deep_recomputed']],
           'rejected_alternatives':[r['code'] for r in review['comparisons']],'strategy_return_pct':None,'account_position_not_asserted':True,'results':[]} for task in ['combined_pair','limitup_single']]
    experiment={'schema_version':'research_shadow_experiment_v1','notice':'独立研究影子，非买入建议；不写正式recommendations、不触发正式通知。',
        'T':T,'planned_D':D,'frozen_at':stamp,'research_rule_version':'weak_market_shadow_v1','report_ids':[IDS['combined_pair'],IDS['limitup_single']],
        'prior_validation_completed_before_freeze':True,'prior_validation_file':VALIDATION,'prior_validation_recorded_at':old_validation['recorded_at'],
        'signals':shadows,'controls':controls,'hypotheses':review['hypotheses'],'formal_cash_observations':cash,
        'benchmark':{'primary':'sh000300','source':sup['benchmarks']['sh000300']['source'],'horizon_axes':['signal_T:1,2,5,10','planned_D:0,1,2,5,10'],
           'price_anchor':'T close, not a fill','sector_context':review['sector_context'],'industry_constituents_verified':False},
        'review':copy.deepcopy(old_exp['review']),'independent_market_shadow_report_id':IDS['market_review'],'results':[]}
    for h in experiment['hypotheses']:h.update(frozen_at=stamp,version='weak_market_shadow_v1',original_preregistration_file=OLD_EXP)
    shadow_table=table(['独立影子，非买入建议','排序/模型','T参考价/已核T上限','相对入选依据','正式未过/独立风险'],[[s['code']+' '+s['name']+' / '+s['parent_task_id'],str(s['rank'])+'/'+s['model'],fmt(s['reference_price'])+'/'+fmt(s['observed_T_upper_price']),s['selection_reason'],s['formal_rejection_reason']] for s in shadows])
    cards='\n\n'.join([f"{s['code']} {s['name']}｜{s['model']}\n{stamp}盘前冻结；T收盘{s['reference_price']}、T实际上限{s['observed_T_upper_price']}，D真实上限待核。\n{s['trigger']}\n失效：{s['invalid']}\n放弃：{s['abandon']}\n{s['exit_rule']}\n独立风险：{s['independent_risk']}" for s in shadows])
    hypothesis=table(['预注册','问题/反证标准','本轮处理与对照/边界'],[[h['id'],h['hypothesis']+'；'+h['falsification'],h['boundary']] for h in experiment['hypotheses']])
    hypothesis+='\n\n20—30个独立实际计划交易日首轮复核；按强/震荡/弱、综合/打板、制度、版本分组，披露缺失、未触发、未成交比例、收益分布、下行尾部和同口径基准。已观察2个独立D日，长节点尚未成熟，不能宣称高胜率。重叠信号按code-D关联，不把同股配对或重叠持有重复计交易。'
    new_low=[]
    for spec in review['new_low']:
        c=spec['code'];s=lookup[c]
        assert not any(r['code']==c for r in low['items']), 'do not duplicate an existing low cohort without a new independent signal'
        disclosed_codes={r['SECURITY_CODE'] for r in raw['lhb_lists'][T]['payload']['result']['data']}
        new_low.append({'id':f'low-position-{TAG}-{c}-v1','date':T,'code':c,'name':s['name'],'sector':sectors[c],
            'primary_model':spec['model'],'tags':spec['tags'],'day0_close':s['close'],'daily_change_pct':s['daily_change_pct'],
            'amount_cny':s['amount_yi']*1e8,'turnover_pct':s['turnover_pct'],'range_position_pct':s['range_position_pct'],
            'rvol':s['rvol'],'ma':s['ma'],'snapshot':s,'invalid_close_below':spec['invalid_close_below'],'invalid_basis':spec['invalid_basis'],
            'reason':spec['reason'],'risk':spec['risk'],'original_snapshot_verified':True,'eligible_for_model_statistics':True,
            'is_recommendation':False,'frozen_at':stamp,'recorded_at':stamp,'report_ids':[IDS['low_position']],
            'rule_version':'low_position_30d_v1','calendar_horizons':[1,3,5,10,15,20,30],'trading_horizons':[5,10,20],
            'sources':[s['source'],EV]+[files[k]['source'] for k in spec.get('official_fact_keys',[])],
            'lhb_disclosed_on_T':c in disclosed_codes,'fund_structure':'Public price/volume and original financial statements only; no confirmed fund identity; no seat invented when absent',
            'moving_average_state':{str(n):s['close']>s['ma'][str(n)] for n in [5,10,20,60]},
            'short_term_tracking':{'planned_D':D,'earliest_legal_exit_if_bought':EXIT,'entry_triggered':None,'entry_fill_verified':None,'executable_net_return_pct':None},
            'observations':[]})
    new_low_text=table(['新研究样本，非推荐','模型/初始收盘失效','依据','风险'],[[s['code']+' '+s['name']+'/'+fmt(s['day0_close']),s['primary_model']+'/'+fmt(s['invalid_close_below']),s['reason']+'；'+s['invalid_basis'],s['risk']] for s in new_low])
    low_table=table(['旧样本','原日/原价','当前收盘/观察%','路径最高/最低%','收盘最大回撤%','原失效/曾收破','自然/交易日龄','30自然日合格'],[[s['code']+' '+s['name'],s['reference_date']+'/'+fmt(s['reference_close']),fmt((s['price_observation'] or {}).get('close'))+'/'+fmt(s['close_return_pct']),fmt(s['path_mfe_pct'])+'/'+fmt(s['path_mae_pct']),s['max_close_to_close_drawdown_pct'],fmt(s['original_invalid_close_below'])+'/'+str(s['ever_verified_close_below_original_invalid']),str(s['elapsed_natural_days'])+'/'+str(s['elapsed_trading_sessions']),s['eligible_for_model_statistics'] and s['thirty_natural_days_matured']] for s in de['low_validations']])
    low_models=table(['原模型','全部N','合格N','成熟30自然日合格N','曾收破初始失效N'],[[r['model'],r['all_n'],r['eligible_n'],r['mature_30d_eligible_n'],r['ever_original_invalidation_broken_n']] for r in de['low_model_statistics']])
    low_summary=f"旧{len(low['items'])}条均继续跟踪；30自然日到期{de['low_summary']['mature_calendar_30']}条，原快照/资格/路径均合格的成熟N={de['low_summary']['eligible_mature_calendar_30']}。原1/3/5/10/15/20/30自然日目标，休市用此前最近交易日并明确报价日；5/10/20交易日节点另存。所有失败及跌破原位保留，未用反弹消除失败。成熟样本不足，不报30日高胜率或10%/20%获利比例。"
    dragon_table=table(['龙虎榜','单日/多日','收盘','买/卖/净万元','机构/股通净万元','买/卖第一席占比','量价/反证'],[[r['code']+' '+r['name'],r['period'],r['close'],fmt(r['buy_cny']/1e4)+'/'+fmt(r['sell_cny']/1e4)+'/'+fmt(r['net_cny']/1e4),fmt(r['institution_net_wan'])+'/'+fmt(r['stock_connect_net_wan']),fmt(r.get('buy_concentration_top1_pct'))+'/'+fmt(r.get('sell_concentration_top1_pct')),review['dragon_reviews'].get(r['code'],'参见原始席位与量价快照；无账户身份或成交结论')] for r in de['dragon_selected']])
    dragon_obs=[]
    selected={r['code']:r for r in de['dragon_selected']}
    for spec in review['dragon_observations']:
        s=selected[spec['code']]
        dragon_obs.append({**spec,'id':f'dragon-tiger-{TAG}-watch-'+spec['code'],'date':T,'frozen_at':stamp,'planned_observation_date':D,
            'name':s['name'],'reference_price':s['close'],'reference_price_at':T+'T15:00:00+08:00','board_regime':s['board_regime'],
            'selected_trade_id':s['selected_trade_id'],'disclosure_period':s['period'],'is_recommendation':False,'executed_trade':False,
            'research_rule_version':'dragon_tiger_original_contract','report_ids':[IDS['dragon_tiger']],'results':[]})
    dragon_cards=table(['龙虎榜独立观察','角色','D1102竞价/开盘/量价/板块确认与放弃'],[[s['code']+' '+s['name'],s['role'],s['condition']] for s in dragon_obs])
    dragon_previous=table(['原T29披露池制度','可观察N','收盘均值/中位%','收红N'],[[b,v['n'],fmt(v['mean_pct'])+'/'+fmt(v['median_pct']),v['positive_n']] for b,v in de['dragon_previous_by_board'].items()])
    boundary='影子及低位/龙虎榜观察不是买入建议，不进入正式recommendations或买入通知。无Level-2、逐笔队列与成本闭环，不声称持续盯盘、确认资金身份、实际成交或净收益。D买入当日失效不能当天卖，涨停浮盈不等于可实现盈利；跌停/停牌可能无法退出。保留量化取消、四模块、打板v2和原任务调度，不自动训练或调整权重。纯数据不用重装APK；CI/容器、准确SHA的Railway SUCCESS和公开API均通过后才能称APP同步。'
    official_note='原PDF哈希、URL、真实HTTP成功取证时间与正文日期分别保存；路径标10月31日但本轮10月30日已实际HTTP可取的材料仅用于此后D1102预案，不倒填T30盘中催化或假设精确首次披露时刻。查询为空不等于风险清零，非穷尽证券状态、减持/解禁/监管检查。'
    repeat=json.dumps(de['repeat_audit'],ensure_ascii=False)
    vp_body='\n\n'.join([common,'结论：完整量价研究，新增28条冻结，正式候选0；独立影子另存。',provider,'一、先验证旧28全池\n'+previous,observations(de['previous_whole_pool']),'二、先检验D30影子与所有原对照\n'+shadow_validation_text,'三、完整28快照\n'+features(de['deep_recomputed']),'四、逐只模型、反例和量价反馈\n'+qualitative,review['volume_findings'],'五、累计及原标签分层\n'+cumulative,'六、时间窗口\n六窗09:30—09:45、09:45—10:30、10:30—11:30、13:00—14:00、14:00—14:30、14:30—15:00均保留；09:30/09:45/10:30/午盘/14:00后和收盘价格点见证据。缺成交与分钟内顺序，不评选可实现盈利的最佳窗口；9:50/14:40与盘后不混统计。','七、新影子与可证伪下一步\n'+shadow_table,hypothesis,'八、原公告反证\n'+facts,official_note,boundary])
    low_body='\n\n'.join([common,f'结论：完整低位30天研究，新增{len(new_low)}条，旧{len(low["items"])}条全路径维护；不当短线买入。',provider,comparisons,'一、新增模型、初始失效及反例\n'+new_low_text,'二、旧样本、到期与失败\n'+low_summary,low_table,'三、原模型统计\n'+low_models,'四、量价和上一批短期验证\n'+previous,review['low_findings'],'五、公告和独立风险\n'+facts,official_note,'六、下次继续检验\n'+review['next_validation'],shadow_table,boundary])
    dragon_body='\n\n'.join([common,'结论：完整龙虎榜研究；原始买卖前五与东财汇总、同花顺同披露期交叉核验，观察与正式推荐分开。',provider,'一、三日情绪/高度/晋级/空间\n'+emotion,ladder,progression,space,'二、席位和量价支持/反证\n'+dragon_table,'机构/股通通用标签不能合并成真实账户；营业部可见交易不能确认某游资、量化、锁仓、做T或对倒。多日披露与单日分别保存；当日收盘后榜单只用于未来D计划，不补填当日盘中。',f"三、公开营业部画像\n保留旧画像；T29/T30两期新增比较{len(profiles['profiles'])}个准确营业部代码/名称、{sum(p['observed_stock_period_rows'] for p in profiles['profiles'])}条股票-披露期观察；{len(profiles['generic_channel_rows_not_merged_as_accounts'])}条机构/股通通用行独立。持有周期、兑现、做T和稳定风格未知，不以数次营业部数据推胜率。",'四、先验证T29全部披露股票\n'+dragon_previous,observations(de['dragon_previous_focused_eight']),'五、D1102独立条件观察\n'+dragon_cards,'六、量价共振与背离\n'+review['dragon_findings']+'\n按席位组合×位置×板块×情绪×封板质量的可执行样本N=0；净收益、策略胜率、盈亏比及退出质量待验证。不能将同源VP样本重复计数。',facts,official_note,boundary])
    limit_body='\n\n'.join([common,'结论：正式打板0只，空仓；研究影子第1 '+next(s['name']+s['code'] for s in shadows if s['parent_task_id']=='limitup_single')+'，非买入建议。limitup_single_v2条件不放宽。','一、先验证上一批\n'+shadow_validation_text+'\n原v1龙溪600592原16.20及未入场条件继续冻结，新版本不重算旧样本。','二、三日情绪和优先否决\n'+emotion,review['formal_cash_reason'],'三、高度板/空间/逐股晋级\n'+ladder,progression,space,denominators,'四、独立筛选和至少三只备选\n'+comparisons,'普通主板10%、创业科创20%、北交30%及风险警示分别处理。ST/退市/无涨跌幅上市初期、缺流动性、一字排队、高位连续缩量加速、爆量滞涨先否决；不默认涨停可以买到。','五、研究卡，保持原价/触发/失效\n'+shadow_table,cards,'六、首板/二板/回封、情绪/主线及配对对照\n'+hypothesis,review['limitup_findings'],'七、公告与风险\n'+facts,official_note,boundary])
    deps=table(['同T完整前置','报告ID','本次支持/反对'],[[t,IDS[t],review['dependency_findings'][t]] for t in TASKS[:4]])
    combined_body='\n\n'.join([common,'结论：正式综合双标0只；综合影子前2 '+ '、'.join(s['name']+s['code'] for s in shadows if s['parent_task_id']=='combined_pair')+'。打板正式0与独立研究影子另列；研究继续，正式门槛不放松。','一、四份同T完整报告及真实completed\n'+deps+'\n本轮先实际完成独立market_review，再补齐其他三模块；六份完整报告在同一原子提交发布；自动观察、配置审计和eligible=false不作前置，量化不恢复。','二、先验证上一全池和D30影子\n'+previous,observations(de['previous_whole_pool']),shadow_validation_text,'三、全A入口、完整深筛和逐股裁决\n'+provider,features(de['deep_recomputed']),qualitative,'四、替代、重选与5/10日覆盖\n'+comparisons+'\n'+repeat+'\n缺完整日期则严格窗口重复率N/A，不补0；正式0只不报推荐重复率。与独立市场报告重叠的股票-D共用市场事件，不额外计一笔交易。','五、情绪、高度、晋级和空间\n'+emotion,ladder,progression,space,'六、正式空仓事件、独立影子及固定退出\n'+review['formal_cash_reason'],shadow_table,cards,'七、H1—H3与同口径对照\n'+hypothesis,review['sector_context'],'八、量价、低位长期及龙虎榜反证\n'+review['volume_findings'],new_low_text,low_summary,dragon_table,facts,official_note,'九、累计验证和下一步\n'+cumulative,review['next_validation'],boundary])
    bodies={'volume_price':vp_body,'low_position':low_body,'dragon_tiger':dragon_body,'limitup_single':limit_body,'combined_pair':combined_body}
    titles={'volume_price':'量价完整研究｜10月30日全池与D30影子核验、28条新冻结','low_position':f'低位启动30天｜10月30日新增{len(new_low)}条、旧50条不删失败','dragon_tiger':'龙虎榜完整研究｜10月30日席位交叉、全池验证与独立观察','limitup_single':'打板v2｜11月2日正式空仓，独立研究影子','combined_pair':'综合双标｜10月30日四项齐备，正式空仓与D1102双轨研究'}
    rules={'volume_price':'volume_price_close_v4','low_position':'low_position_30d_v1','dragon_tiger':'dragon_tiger_original_contract','combined_pair':'combined_limitup_watch_v5','limitup_single':'limitup_single_v2'}
    sources=list(dict.fromkeys([EV,EXP,VALIDATION,'docs/research/market-review-2026-10-30-evidence.json','https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml',ths['source']]+[r['source'] for r in files.values() if r.get('ok')]))
    new_reports=[];new_runs=[]
    for task,body in bodies.items():
        rid=IDS[task];run_id=f'{task.replace("_","-")}-{TAG}-scheduled-close-'+('v2' if task=='limitup_single' else 'v1')
        summary=review['summaries'][task]
        report={'id':rid,'date':T,'market_date':T,'task_id':task,'track':task if task in TASKS[1:4] else 'market_review','run_id':run_id,
            'title':titles[task],'summary':summary,'body':body,'sources':sources,'report_type':'full_trading_research' if task=='combined_pair' else 'full_daily_research',
            'eligible_for_integrated_research':task!='limitup_single','analysis_completed':True,'status':'completed','published_at':stamp,'recorded_at':stamp,
            'market_data_cutoff_at':T+'T15:00:00+08:00','data_cutoff_at':stamp,'planned_entry_date':D,'earliest_legal_exit_date_if_bought':EXIT,
            'research_rule_version':rules[task],'provenance':'contemporaneous_after_close_research','candidate_count':0,'recommendation_ids':[],
            'evidence_file':EV,'full_scan_count':market['coverage']['positive_quote_entry_count'],'active_OHLCV_count':market['coverage']['same_day_positive_OHLCV_count'],'inactive_or_missing_current_OHLCV_count':4,'broad_pool_count':120,'deep_pool_count':28,
            'codes':[s['code'] for s in de['deep_recomputed']],'shadow_experiment_file':EXP,'prior_shadow_validation_file':VALIDATION}
        if task=='low_position':report.update(new_sample_count=len(new_low),new_sample_ids=[s['id'] for s in new_low],previous_samples_verified=len(low['items']),codes=sorted({s['code'] for s in low['items']+new_low}))
        if task=='dragon_tiger':report.update(observation_count=len(dragon_obs),signal_observations=dragon_obs,codes=[s['code'] for s in de['dragon_selected']])
        if task in ['combined_pair','limitup_single']:report.update(strategy='limitup_single_v2' if task=='limitup_single' else 'combined_limitup_watch',group='close',decision='cash_no_qualified_candidate',formal_cash_observation=next(c for c in cash if c['task_id']==task),research_shadow_candidates=[s for s in shadows if s['parent_task_id']==task],research_shadow_count=sum(s['parent_task_id']==task for s in shadows))
        if task=='combined_pair':report.update(dependency_report_ids=[IDS[t] for t in TASKS[:4]],cohort_label='综合盘后组')
        if task=='limitup_single':report.update(full_20_session_space_reference_available=sp['coverage_complete'])
        new_reports.append(report);new_runs.append({'id':run_id+'-completed','run_id':run_id,'task_id':task,'date':T,'trigger':'scheduled',
            'started_at':START,'completed_at':stamp,'recorded_at':stamp,'status':'completed','summary':summary,'report_ids':[rid],'recommendation_ids':[],
            'analysis_completed':True,'eligible_for_integrated_research':task!='limitup_single','delivery_status':'repository_prepared_not_yet_verified','sources':[EV,EXP,VALIDATION]})
    research['items'].extend(new_reports);runs['items'].extend(new_runs)
    old_low_count=len(low['items'])
    for s in low['items']:
        obs=next(r for r in de['low_validations'] if r['origin_cohort_id']==s['id']);s.setdefault('observations',[]).append({**obs,'recorded_at':stamp,'calculated_at':de['calculated_at']})
    low['items'].extend(new_low);low['updated_at']=stamp
    cohorts=cum['vp_all_cohort_validations'];sample_n=sum(c['sample_count'] for c in cohorts)
    vp['items'].extend([
        {'id':'volume-price-20261029-validation-20261030-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
         'origin_cohort_id':'volume-price-20261029-close-v1-cohort','rule_version':'volume_price_close_v4','full_validation_completed':True,'full_pool_summary':p,
         'full_pool_validations':de['previous_whole_pool'],'executed_trade_count':0,'eligible_for_model_statistics':False,'statistical_scope':'price_observation_not_executable_strategy'},
        {'id':f'volume-price-historical-validation-{TAG}-v1','date':T,'task_id':'volume_price','recorded_at':stamp,'report_ids':[IDS['volume_price']],
         'cohort_ids':[c['origin_cohort_id'] for c in cohorts],'frozen_sample_count':sample_n,'matched_original_close_count':sum(v['original_close_matches_unadjusted_bar'] for c in cohorts for v in c['validations']),
         'rule_version_groups':cum['vp_by_rule_version'],'evidence_file':EV,'executed_trade_count':0,'eligible_for_model_statistics':False},
        {'id':f'volume-price-{TAG}-close-v1-cohort','date':T,'task_id':'volume_price','frozen_at':stamp,'report_ids':[IDS['volume_price']],
         'rule_version':'volume_price_close_v4','feature_calculation_version':'unadjusted_MA_including_T_v3','data_cutoff_at':T+'T15:00:00+08:00',
         'broad_pool_count':120,'broad_pool_verified_count':120,'deep_screen_count':28,'eligible_for_model_statistics':True,
         'statistical_scope':'future_price_observation_not_trade_profitability','provenance':'contemporaneous_full_market_research','samples':de['deep_recomputed']}])
    bench={b['date']:b for b in sup['benchmarks']['sh000001']['bars']}
    for r in recs['items']:
        by={b['date']:b for b in daily.get(r['code'],[])};anchor=r.get('planned_entry_date') or r['date'];a=by.get(anchor);signal=by.get(r['date']);hs=[]
        for h in [1,2,3,5,10,20,30]:
            target=nth_session_after(date.fromisoformat(anchor),h).isoformat();cur=by.get(target);mature=target<=T;ds=[];day=date.fromisoformat(anchor)+timedelta(days=1)
            while day<=min(date.fromisoformat(target),date.fromisoformat(T)):
                if is_session(day):ds.append(day.isoformat())
                day+=timedelta(days=1)
            missing=[d for d in ds if d not in by];path=[by[d] for d in ds if d in by];ok=bool(mature and a and cur and not missing)
            bp=pct(bench[target]['close'],bench[anchor]['close']) if ok and target in bench and anchor in bench else None;ret=pct(cur['close'],a['close']) if ok else None
            hs.append({'h':h,'date':target,'status':'price_observed' if ok else 'missing' if mature else 'pending','close_pct':ret,
                'high_observation_pct':pct(max(b['high'] for b in path),a['close']) if ok else None,'low_observation_pct':pct(min(b['low'] for b in path),a['close']) if ok else None,
                'benchmark_pct':bp,'excess_price_observation_pct':round(ret-bp,3) if ret is not None and bp is not None else None,'missing_sessions':missing if mature else []})
        ref=r.get('reference_price');cur=by.get(T)
        r.setdefault('results',[]).append({'id':r['id']+'-price-review-'+TAG,'date':T,'market_date':T,'recorded_at':stamp,
            'report_ids':[IDS['limitup_single'] if r.get('task_id')=='limitup_single' else IDS['combined_pair']],
            'status':'price_observation_only' if cur else 'missing_daily_price','observed_daily':cur,'anchor_date':anchor,'anchor_close':a['close'] if a else None,
            'anchor_definition':'planned-entry-date close, retained as price-only baseline, not a fill','signal_date':r['date'],'signal_daily_close':signal['close'] if signal else None,
            'original_frozen_reference_price':ref,'T_close_vs_signal_daily_close_pct':pct(cur['close'],signal['close']) if signal and cur else None,
            'T_close_vs_original_reference_pct':pct(cur['close'],ref) if cur and isinstance(ref,(int,float)) and ref>0 else None,'horizons':hs,
            'trigger_status':'original_no_entry_preserved' if r['id']=='limitup-single-20261008-600592-v1' else 'not_reconstructed_from_daily_extremes',
            'executed_trade':False,'executable_net_return_pct':None,'source':raw['daily_histories'].get(r['code'],{}).get('source'),
            'fee_and_slippage_status':'unverified orders/quantity/minimum commission/slippage; no net profit'})
    stock_updates=[]
    for stock in catalog['items']:
        observations_for_code=[r for r in de['low_validations'] if r['code']==stock['code']]
        if not observations_for_code:continue
        r=observations_for_code[-1]
        ep={'id':f'research-stock-{stock["code"]}-{TAG}-low-followup-v1','date':T,'recorded_at':stamp,'title':'原低位样本价格和初始失效继续验证',
            'reason':stock['name']+'继续原样本跟踪，不把短期价格表现当作30天结论或交易收益。','evidence_status':'verified_daily_price_observation_not_trade_return',
            'fact_note':f"原日期{r['reference_date']}、原参考{r['reference_close']}；当前收盘{(r['price_observation'] or {}).get('close')}，观察{r['close_return_pct']}%；原失效{r['original_invalid_close_below']}、曾收破={r['ever_verified_close_below_original_invalid']}。",
            'validation':['原自然日/交易日节点和失败保留','资格、失效位及旧理由不回写'],
            'risk':'价格观察缺分钟成交与可执行退出证据；历史失效不因反弹消失。','report_ids':[IDS['low_position']],
            'sources':[raw['daily_histories'][stock['code']]['source'],EV]}
        stock['history'].append(ep);stock_updates.append({'code':stock['code'],'history_id':ep['id']})
    for c in sorted({s['code'] for s in new_low+shadows}):
        stock=next((s for s in catalog['items'] if s['code']==c),None);s=lookup[c];spec=next((a for a in review['new_low'] if a['code']==c),None)
        sh=next((a for a in shadows if a['code']==c),None);linked=[IDS['low_position']] if spec else []
        if sh:linked.append(IDS[sh['parent_task_id']])
        ep={'id':f'research-stock-{c}-{TAG}-research-v1','date':T,'recorded_at':stamp,'title':'新增完整研究理由，非买入指令',
            'reason':(spec['reason'] if spec else '')+'；'+(sh['selection_reason'] if sh else ''),
            'evidence_status':'dated_daily_snapshot_and_official_filings_with_explicit_risks','fact_note':f"{s['name']}T30收盘{s['close']}，正式交易候选0，原始条件独立冻结。",
            'validation':['D1102后按原规则前推，未触发与失败均保留','T+1合法退出及费用成交不足则只作价格观察'],
            'risk':(spec['risk'] if spec else '')+'；'+(sh['independent_risk'] if sh else ''),'report_ids':list(dict.fromkeys(linked)),
            'sources':[s['source'],EV]+[files[k]['source'] for k in (spec or sh).get('official_fact_keys',[])]}
        if stock:stock['history'].append(ep)
        else:catalog['items'].append({'code':c,'name':s['name'],'sector':sectors[c],'role':'research','default_watch':False,'history':[ep]})
        stock_updates.append({'code':c,'history_id':ep['id']})
    # A new official fact about an existing researched stock needs its own
    # independent reason history, even when today's price follow-up also exists.
    for fact in review['facts']:
        stock=next((s for s in catalog['items'] if s['code']==fact['code']),None)
        if stock is None or fact['code'] in {s['code'] for s in new_low+shadows}:continue
        ep={'id':f'research-stock-{stock["code"]}-{TAG}-official-facts-v1','date':T,'recorded_at':stamp,
            'title':'原公告的新核验与反证','reason':stock['name']+'完整原公告核验追加；原关注理由与历史风险不回写。',
            'evidence_status':'original_company_filing_retrieved_with_timestamp_and_hash','fact_note':fact['fact'],
            'validation':['持续核对经营现金、扣非和单季反证','只使用真实HTTP可得之后的材料，不补当日盘中原因'],
            'risk':'公告事实不构成买入许可，原始版本及未排除的风险保留。','report_ids':[IDS['combined_pair']],
            'sources':[files[k]['source'] for k in fact['official_fact_keys']]+[EV]}
        stock['history'].append(ep);stock_updates.append({'code':stock['code'],'history_id':ep['id']})
    # Every previously frozen signal is reviewed, including non-low names.
    prior_rows=old_validation['signals']+[r for batch in old_validation['all_frozen_experiment_followups'] for r in batch['signals']]
    for r in prior_rows:
        stock=next((s for s in catalog['items'] if s['code']==r['code']),None)
        if stock is None:continue
        ep={'id':f'research-stock-{stock["code"]}-{TAG}-shadow-validation-v1','date':T,'recorded_at':stamp,
            'title':'原影子条件核验，非新推荐','reason':stock['name']+'原冻结信号继续验证，未触发不改为成交。',
            'evidence_status':'dated_price_observation_and_original_trigger_validation','fact_note':f"原T={r['origin_signal_T']}，计划D={r['planned_D']}；T30收盘观察{r['close_observation_pct']}%；{r['entry_status']}。",
            'validation':r.get('trigger_evidence',[]),'risk':'没有实际买卖、逐笔队列和可执行净收益证据；最高价不等于策略盈利。',
            'report_ids':[IDS['combined_pair']],'sources':[VALIDATION]+r['sources']}
        stock['history'].append(ep);stock_updates.append({'code':stock['code'],'history_id':ep['id']})
    catalog['updated_at']=stamp
    # Only result lists of the previous experiment are extended. No freeze,
    # price, rank, trigger, invalidation, or hypothesis field is modified.
    for key in ['signals','controls']:
        for s in old_exp[key]:
            obs=next(r for r in old_validation[key] if r['code']==s['code']);assert not any(r.get('date')==T for r in s['results']);s['results'].append(copy.deepcopy(obs))
    for c in old_exp['formal_cash_observations']:
        c['results'].append({'id':c['id']+'-review-'+TAG,'date':T,'recorded_at':stamp,'formal_new_candidates':0,
            'actual_orders_claimed':False,'account_PnL':None,'shadow_price_summary':old_validation['summary'],'source':VALIDATION})
    old_exp['results'].append({'date':T,'recorded_at':stamp,'summary':old_validation['summary'],'validation_file':VALIDATION})
    older_experiment_updates={}
    for batch in old_validation['all_frozen_experiment_followups']:
        path=batch['origin_experiment'];prior=load(path)
        for key in ['signals','controls']:
            for frozen in prior[key]:
                obs=next(r for r in batch[key] if r['code']==frozen['code'])
                assert not any(r.get('date')==T for r in frozen['results'])
                frozen['results'].append(copy.deepcopy(obs))
        for cash_obs in prior['formal_cash_observations']:
            cash_obs['results'].append({'id':cash_obs['id']+'-review-'+TAG,'date':T,'recorded_at':stamp,
                'formal_new_candidates':0,'actual_orders_claimed':False,'account_PnL':None,
                'shadow_price_summary':batch['summary'],'source':VALIDATION})
        prior['results'].append({'date':T,'recorded_at':stamp,'summary':batch['summary'],'validation_file':VALIDATION})
        older_experiment_updates[path]=prior
    base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    evidence={'market_date':T,'planned_entry_date':D,'earliest_legal_exit_if_bought':EXIT,'actual_started_at_utc':START,'actual_completed_at':stamp,'base_main':base,
        'market_module_executed_this_run':True,'market_report_id':IDS['market_review'],'market_report_sha256':hashlib.sha256(json.dumps(mr,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        **{k:raw[k] for k in ['sina_pages','daily_histories','minute_price_points','lhb_lists','seat_queries','limit_up_pools']},
        'initial_failed_records':{k:{c:r for c,r in original_raw[k].items() if not r.get('ok')} for k in ['daily_histories','minute_price_points','seat_queries','limit_up_pools']},
        'retry_checks':ext,'independent_direct_bar_checks':raw['independent_direct_bar_checks'],'checkpointed_failed_seat_attempts':{p.name:load(str(p.relative_to(ROOT))) for p in (ROOT/'tmp/t30-inputs/failed-attempts/seats').glob('*.json')},'derived':de,'cumulative':cum,'supplement':sup,'official_queries':load(f'tmp/combined-{TAG}-announcements.json'),
        'extra_official_queries':load(f'tmp/combined-{TAG}-extra-announcements.json'),'official_files':{k:{a:v for a,v in r.items() if a!='text'} for k,r in files.items()},
        'context_quotes':load(f'tmp/combined-{TAG}-context-quotes.json'),
        'official_verified_fact_notes':review['facts'],'ths_source':ths['source'],'ths_summary_rows':ths['tables'][5],'seat_profiles':profiles,
        'raw_quoted_upper_prices':quote,'exact_main_price_limit_verification':exact,'analyst_deep_review':review,
        'prior_shadow_validation':old_validation,'research_shadow_experiments':experiment,'new_low_samples':new_low,'new_dragon_observations':dragon_obs,'stock_history_updates':stock_updates,
        'limitations':['No 9:25 auction/ticks/full minute OHLC/queue fills or calibrated costs','Industry mapping is research context, not verified constituents',
            'Retrospective recovery and unverified anchors excluded from forward statistics','Partial historical ladder and point-in-time security-master coverage disclosed','No shadow in formal recommendations and no automatic strategy or weight updates']}
    encoded=gzip.compress(json.dumps(evidence,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)
    manifest={'base_main':base,'market_date':T,'planned_entry_date':D,'actual_started_at_utc':START,'analysis_completed_at':stamp,
        'new_report_ids':[IDS['market_review']]+[r['id'] for r in new_reports],'reused_report_ids':[],'market_module_executed_this_run':True,'new_recommendations':0,
        'new_low_samples':len(new_low),'old_low_observations_appended':old_low_count,'new_volume_samples':28,
        'old_frozen_recommendation_results_appended':len(recs['items']),'stock_history_updates':stock_updates,'evidence_file':EV,
        'evidence_sha256':hashlib.sha256(encoded).hexdigest(),'shadow_experiment_file':EXP,'prior_shadow_validation_file':VALIDATION,
        'research_shadow_count':len(shadows),'formal_cash_observation_count':2,'hypothesis_ids':['H1','H2','H3'],
        'task_registry_changed':False,'schedules_changed':False,'quant_research_restored':False}
    docs={'backend/data/research.json':research,'backend/data/task_runs.json':runs,'backend/data/volume_price_samples.json':vp,
        'backend/data/low_position_samples.json':low,'backend/data/recommendations.json':recs,'backend/data/research_stocks.json':catalog,
        'app/src/main/assets/research_stocks.json':catalog,EXP:experiment,OLD_EXP:old_exp,VALIDATION:old_validation,
        f'docs/research/combined-pair-{TAG}-publication-manifest.json':manifest,f'docs/research/combined-pair-{TAG}-analyst-review.json':review,**older_experiment_updates}
    serialized={p:json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n' for p,d in docs.items()}
    assert datetime.fromisoformat(START)<=datetime.fromisoformat(stamp)<=datetime.now(timezone.utc)
    for p,s in serialized.items():
        path=ROOT/p;tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(s);tmp.replace(path)
    (ROOT/EV).write_bytes(encoded)
    for task,body in bodies.items():(ROOT/f'docs/research/{IDS[task]}.md').write_text('# '+titles[task]+'\n\n'+body+'\n\n来源：\n\n'+'\n'.join('- '+s for s in sources)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
