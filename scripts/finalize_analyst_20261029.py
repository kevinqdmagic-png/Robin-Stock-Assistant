"""Record the final human analytical comparison after dated evidence review."""
from pathlib import Path
from datetime import datetime,timezone
import json
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text())
r=load('tmp/analyst-combined-20261029.json');de=load('tmp/combined-20261029-derived.json')
lookup={s['code']:s for s in de['broad_recomputed']}
assert len(de['deep_recomputed'])==28 and not de['crosscheck']['ohlc_mismatches']
assert de['low_summary']['all_paths_complete']
assert all(s['seat_reconciliation']['matched'] and s['ths_close_match'] for s in de['dragon_selected'])
assert load('tmp/shadow-validation-20261029.json')['summary']['necessary_conditions_disproved_n']==3
r['deep_reviews']['002275']['model']='中位首板/异常放量'
r['deep_reviews']['002275']['support']='Q3扣非改善、正经营现金流，首板日有换手与分歧后收盘回封的价格证据；适合H2条件实验。'
r['deep_reviews']['002275']['against']='60日位置99.448%、120日62.069%，不叫低位30天样本；RVOL20约14.893，异常量与反复开板可能是供给冲击。尾盘持平不证明主动吸筹。'
r['deep_reviews']['605179']['model']='中位回撤反弹/尾盘正向对照'
r['deep_reviews']['605179']['against']='前20日曾到31.48且振幅很大，不因60日区间位置较低就当首次低位启动；Q3亏损、11月3日除息均保留。'
r['shadows']=[
 {'parent_task_id':'combined_pair','rank':1,'code':'600118','theme':'卫星研制/航天价格共振','model':'低长期位置放量修复＋逆势板块',
  'hypothesis_labels':['H1','H3'],'H1_arm':'low_position_volume_tail_flat_partial_not_full_H1',
  'selection_reason':'120日位置10.924%、RVOL20=3.151、CLV=1；航天同伴价格逆势、成交31.134亿元。相较广联20%制度与持续亏损，主板10%同口径且Q3盈利改善；相较高位光洋，位置和财务反证较少。',
  'formal_rejection_reason':'弱市仅14.179%上涨；未越59.72原20日高，未收复MA60=58.295，累计经营现金净流出4.1317亿元；封板和高基数增长不证明次日可执行退出。',
  'independent_risk':'低长期位置不等于趋势反转；T29尾盘0%只表封价持平，未证实主动承接或资金身份。D30高开/放量滞涨、航天同伴转弱和高标负反馈均可使假设失败。',
  'pullback_or_auction_range':[53.66,54.78],'confirmation_range':[54.78,55.90],'max_auction_price':57.02,
  'observation_invalidation_below':52.75,'structural_invalidation_below':50.55,
  'trigger':'D30必须另核9:25竞价≤57.02；先有53.66—54.78回踩与随后承接的带时序证据，09:45与10:30两个日期合格报价均在54.78—55.90且不低于各时点累计VWAP；航天参考广联300900/晨光600501不能同时转弱。53.66/54.78分别为T收盘约96%/98%的假设观察带，不冒充已经验证支撑。没有顺序、竞价或成交证据只作价格观察，不认定买入。',
  'invalid':'D30任一有日期价点跌破52.75（约T日MA20）即停止新触发；50.55为T日最低结构参照。日内买入后的失效不赋予当日卖出权。',
  'abandon':'竞价超过57.02、没有真实回踩顺序、价格不在确认带/低于累计VWAP、板块转弱、高标风险扩散或上限/交易状态不能核实时放弃；不以最高价倒推成交。',
  'official_fact_keys':['600118-q3']},
 {'parent_task_id':'combined_pair','rank':2,'code':'603279','theme':'过滤设备','model':'低位箱体突破后首次承接待验证',
  'hypothesis_labels':['H1'],'H1_arm':'low_position_volume_tail_negative_partial_not_full_H1',
  'selection_reason':'120日位置22.198%、RVOL20=6.404，收12.49越过原20日高11.80并收复MA60=11.71583；Q3利润改善、累计经营现金为正。相较一鸣近期宽幅反弹/单季亏损、爱建扣非亏损，基础反证较少；相较桂林60日顶端，更适合低位价格实验。',
  'formal_rejection_reason':'T29触12.57上限后未封，14时后−0.557%，不满足已经确认尾盘承接；累计归母和现金流仍下降，设备板块持续性未核清。',
  'independent_risk':'低位突破可能是假突破；尾盘回落是反证，不给完整H1正向标签。每股0.50元仅分红方案、实施日未知，不计成D30收入；弱市中再次放量可能兑现。',
  'pullback_or_auction_range':[11.97,12.24],'confirmation_range':[12.24,12.49],'max_auction_price':12.74,
  'observation_invalidation_below':11.97,'structural_invalidation_below':11.80,
  'trigger':'D30另核9:25竞价≤12.74；先出现11.97—12.24回踩并有其后承接的时序证据，09:45与10:30两个有日期价点均在12.24—12.49且不低于当时累计VWAP。11.97取T日最低、11.80为原20日高；12.24约T收盘98%，是假设确认带。缺先后证据不确认触发或成交。',
  'invalid':'D30任一日期合格价点跌破11.97停止新触发；收盘跌破11.80记录原突破结构失效，不下移；买入当日不能止损卖出。',
  'abandon':'竞价超12.74、反复冲板不能推进、承接失去/确认价低于VWAP、高标跌停负反馈扩散、盘口或证券状态无法核实即放弃。',
  'official_fact_keys':['603279-q3','603279-利润分配']},
 {'parent_task_id':'limitup_single','rank':1,'code':'002275','theme':'中药','model':'中位换手首板后第一个交易日分歧/二板确认',
  'hypothesis_labels':['H2'],'current_boards':1,'planned_boards':2,'theme_visible_height':1,'theme_height_scope':'本研究已核中药参考范围，非全行业主表','role_in_theme':'待确认',
  'selection_reason':'T29首板、换手4.095%、成交3.098亿元；Q3扣非+25.35%、累计经营现金为正。相较爱建扣非亏、景津触板未封、海阳单季利润下降和高位一字接力，选择独立首板分歧研究。',
  'formal_rejection_reason':'120日位置62.069%、60日99.448%，并非低位30天样本；RVOL20=14.893且T29可见反复开板，弱市和行业同伴不强的风险未过正式门槛。',
  'independent_risk':'大成交可能是分歧供给而非吸筹；累计营收/归母/现金流略降。每股0.15元是待实施分红方案；无当日龙虎榜不编造席位。普通成交、排队与封单持续性仍未知。',
  'pullback_or_auction_range':[13.62,14.30],'confirmation_range':None,'max_auction_price':14.30,
  'observation_invalidation_below':13.15,'structural_invalidation_below':12.67,
  'trigger':'D30另核9:25竞价13.62—14.30；只研究09:35—10:30累计换手2—12%内第一次可核实分歧后的回封。必须取得D30真实上限（不以13.62×1.1替代），价格回到上限且在上限×98%与当时累计VWAP之上至少连续60秒有可核承接；事前参考000999华润三九、600329达仁堂同一时刻均较T29收盘涨≥3%，且高标负反馈不扩散。没有逐笔连续性/9:25/队列证据，完整触发与成交均待验证；一字排队不默认可买。',
  'invalid':'D30有日期价点跌破13.15（T29 10:30价点，非已验证固有支撑）停止新触发；12.67为T29低点结构参照，12.58为此前20日高。买入当日炸板仍不能当日卖。',
  'abandon':'竞价不在13.62—14.30、无首次分歧时序、累计换手超12%、两只中药参照不足+3%、连续开板/撤单/爆量不推进、高标风险扩散或盘口/上限不能核实即放弃。',
  'paired_control':'同股D30第一个可证明可成交的开盘报价直接追高价格对照；也须受一字/停牌/无成交约束，不能默认一笔模拟成交。',
  'official_fact_keys':['002275-q3','002275-利润分配','002275-资产减值']}
]
r['new_low']=[
 {'code':'600118','model':'低位量能修复','tags':['低位修复','航天价格共振','尾盘持平未证承接'],'invalid_close_below':50.55,'invalid_basis':'T29最低50.55，初始冻结；原20日高59.72和MA60未收复，不叫确认主升。',
  'reason':'中国卫星120日位置10.924%、60日31.605%，RVOL20=3.151，收复短中均线的第一轮修复；以未来价格/承接验证，未认定资金身份。',
  'risk':'未收复MA60，累计经营现金流为负；航天高热与次日开板、周末隔夜均有风险。','official_fact_keys':['600118-q3']},
 {'code':'603279','model':'低位箱体突破','tags':['箱体突破','放量','尾盘分歧未确认'],'invalid_close_below':11.80,'invalid_basis':'T前20日最高11.80为突破结构原位；T29最低11.97作较近观察线，原结构失效不下移。',
  'reason':'景津装备120日位置22.198%，收12.49越过11.80原箱顶、收复MA60，季度利润改善；保留触板未封和尾盘回落这一反证。',
  'risk':'累计净利/经营现金流下降，分红方案未实施；突破可失败，首日涨幅不代表30天有效。','official_fact_keys':['603279-q3','603279-利润分配']},
 {'code':'603382','model':'低中位箱体修复','tags':['低中位修复','放量突破','经营现金改善'],'invalid_close_below':17.50,'invalid_basis':'T29最低17.50冻结；19.61为原20日高、19.10017为MA60，只作后续结构参照。',
  'reason':'海阳科技120日位置36.421%、60日43.583%，收19.87越过原20日高19.61并收复MA60；量能与现金流改善支持持续研究，未称已确定长期反转。',
  'risk':'Q3与累计归母仍下降，换手11.257%、次日承接未知；减持/担保/证券状态核查非穷尽。','official_fact_keys':['603382-q3']}
]
r['controls']=[
 {'code':'002708','label':'H1/H3高位接力与流动性近似对照','hypothesis_labels':['H1','H3'],'matching_note':'光洋28.874亿元与卫星31.134亿元为同一成交量级、主板10%/同日弱市；行业、板数和盈利差异未消除。'},
 {'code':'600715','label':'H1高位连续放量对照','hypothesis_labels':['H1'],'matching_note':'主板10%、120日位置100%，对照低位样本；11.549亿元高于景津5.534亿元，非严格行业/流动性匹配。'},
 {'code':'600643','label':'H2首板同流动性量级但扣非亏损对照','hypothesis_labels':['H2'],'matching_note':'成交2.769亿元对桂林3.098亿元、换手约4%同量级；多元金融与中药不同，不能归因于单一形态。'},
 {'code':'605179','label':'H1尾盘推进但非首次低位启动反例','hypothesis_labels':['H1'],'matching_note':'尾盘+1.668%，前20日高31.48且Q3亏损、已知除息；保留为位置/财务混杂对照，非低位正式样本。'}
]
r['comparisons']=[
 {'code':'600118','role':'首板/计划二板；航天修复待确认','reason':'综合影子第1：低长期位置与逆势板块；现金流负、MA60下及59.72旧高未破否决正式。'},
 {'code':'603279','role':'触板未封/计划首板；设备突破待确认','reason':'综合影子第2：低长期位置、盈利/现金为正；尾盘回落未承接，保留假突破。'},
 {'code':'002275','role':'首板/计划二板；中药角色待确认','reason':'打板影子第1：正利润与现金、换手适中优于扣非亏损对照；60日顶部、异常RVOL反证使正式仍0。'},
 {'code':'600643','role':'首板/计划二板；金融跟随待确认','reason':'同流动性对照，长120日位置40.559%；但扣非亏损、弱市银行与多元金融不能直接画等号，次于桂林。'},
 {'code':'603382','role':'首板/计划二板；化纤修复','reason':'现金改善和MA60修复进入30天研究；单季利润下降和换手11.257%，未进前三影子。'},
 {'code':'300900','role':'20%制度航天反弹；原复盘影子独立保留','reason':'长期位置低、行业强，但累计与Q3仍亏、经营现金流负；选择10%制度且盈利的景津以比较不同模型，不为降低重复率替换。'},
 {'code':'605179','role':'食品首板/计划二板；尾盘正向反例','reason':'尾盘+1.668%但前20日宽幅波动、Q3亏损、11月3日除息；不因短期回撤位置较低叫底部首次启动。'},
 {'code':'600501','role':'首板/计划二板；航天同伴待确认','reason':'主题同步、Q3转正；累计与扣非仍亏、经营现金净流出较大，次于卫星。'},
 {'code':'002708','role':'四板/计划五板；可见高度参考','reason':'机构/股通单日净买与回封并存，但扣非亏损、120日顶端与高换手，不追高度。'}
]
r['dragon_reviews']={
'000530':'机构净买与首板收强并存，但37.923%换手是隔夜波动反证。',
'000678':'机构净买10630.729万元、股通+3737.999万元仍五进六失败；净买不保证封板或退出。',
'001219':'多日披露与一字四板，普通成交未证；控制权仍筹划，不能当确定交易完成。',
'002149':'机构净卖1433.822万元、股通净买5393.624万元，方向分歧，不把单通道认定为合力。',
'002172':'多日机构+2563.945万元不可改写成单日；接力和高换手风险仍在。',
'002708':'单日机构+3354.064万元、股通+3925.241万元；高位换手回封与最新扣非亏损并列。',
'002943':'多日机构−4184.190万元、股通−2156.292万元，不能把二板上涨归因为机构合力。',
'600643':'股通净买460.090万元、总榜净买2341.752万元仍不抵消扣非亏损。',
'600715':'股通净卖5503.524万元、总榜净卖10486.829万元仍封板，是席位方向与价格背离。',
'600838':'总榜净卖2097.005万元、收13.63；原断板风险保留，不因早盘反弹改成功晋级。',
'603028':'机构净买1348.967万元、总榜净买1591.973万元仍收跌停9.36；净买不能证明可执行盈利。',
'603528':'股通净买166.101万元但收跌停7.98，不能套股通买入优势。',
'605179':'机构净卖908.088万元、股通+1621.538万元，尾盘回封但Q3亏损；非统一资金身份。'}
r['dragon_observations']=[
 {'code':'002149','role':'材料分歧方向对照','condition':'D30先核9:25不高于32.96；09:45/10:30均有普通成交且在31.66上方并不低于当时VWAP，卫星/航空参照不同时转弱才继续研究；跌破T低28.88、放量不能推进、盘口/竞价缺证则放弃，不默认买入。'},
 {'code':'600643','role':'首板与扣非亏损反例','condition':'D30竞价≤4.34、开盘不一字排队，09:45/10:30核4.14上承接及VWAP；跌破4.14、板块失同步或反复开板即停止新观察。净买不能抹掉扣非亏损，无竞价/盘口证据不确认触发。'},
 {'code':'000678','role':'最高板断板负反馈，只作风险参照','condition':'D30先核18.57能否获得普通交易承接及板块同步；再弱开/跌破18.57、封跌停无流动性或放量滞涨均作否定。不是抄底或新买入卡，不因净买上亿元改判成功晋级。'},
 {'code':'002943','role':'多日席位与二板背离对照','condition':'D30竞价不可一字排队，开盘后须重新核27.62附近承接、VWAP和机器人同伴；跌破24.52或高标转弱、反复开板、量能不能推进即放弃；多日净卖与亏损反证不删除。'},
 {'code':'605179','role':'尾盘回封/除息与亏损反例','condition':'D30竞价≤24.25，09:45/10:30核23.38与当时VWAP的承接，食品参照不能同时转弱；无时序、失23.38、爆量不推进即停止新观察。11月3日除息单列；D30若买最早11月2日可卖，不能从最高价推成交。'}]
q=load('tmp/combined-20261029-quote-upper-check.json');ctx=load('tmp/combined-20261029-context-quotes.json')
r['reference_stocks']=[]
for c,role in [('000678','五进六失败高标'),('001219','四板高度'),('002708','四板高度'),('300900','航天20%同伴'),('600501','航天10%同伴'),('002149','材料10%同伴'),('000999','中药确认同伴'),('600329','中药确认同伴'),('600436','中药价格旁证')]:
 sym=('sh' if c.startswith('6') else 'sz')+c;f=ctx.get('provider_fields',{}).get(sym) or q['provider_fields'][sym]
 assert f[30].startswith('20261029')
 source=ctx['source'] if sym in ctx['provider_fields'] else next(b['source'] for b in q['batches'] if sym in b.get('provider_fields',{}))
 r['reference_stocks'].append({'code':c,'name':f[1],'role':role,'reference_close':float(f[3]),'date':'2026-10-29','provider_timestamp':f[30],'source':source,'observation_window':'D30 09:25及09:35—10:30，必须重新取得当时真实数据','extra_abandon':'000678失18.57且001219/002708任一低于T29收盘5%以上，或任一高标封跌停，暂停新的影子触发；价格点不能证明盘口流动性。'})
r['hypotheses'][0].update(treatment_codes=[],partial_low_position_codes=['600118','603279'],control_codes=['002708','600715','605179'],
 boundary='本次卫星尾盘持平、景津尾盘−0.557%，均为低位放量但尾盘承接未确认亚组，不计完整H1正向处理样本；保留负证据，不能事后随结果改分组。一鸣尾盘正向但近期宽幅波动作混杂对照。')
r['hypotheses'][1].update(treatment_codes=['002275'],control_codes=['002275','600643'],paired_arms={'A':'原卡第一次可核分歧回封','B':'原卡第一个可证明成交的开盘报价价格对照'})
r['hypotheses'][2].update(treatment_codes=['600118'],control_codes=['002708'],boundary='T29航天逆势的部分业务价格篮子，不声称行业成分或订单利润贡献已核。卫星31.134亿元、光洋28.874亿元同量级，但行业/板数/财务差异未被控制。')
r['low_findings']='新增卫星、景津、海阳3条分别研究长期低位修复/箱体突破/低中位修复；卫星还在MA60下、景津尾弱、海阳利润下降，各自反证保留。桂林60日位置99.448%且120日62.069%，仅作短期首板研究，不放入30天低位新样本；一鸣虽60日位置较低但前20日曾宽幅波动，不当首次低位启动。旧泰山/神驰/铁流原失效6.03/16.31/15.45不变。'
r['summaries']={
'volume_price':'5573→120→28；旧28中位−3.011%；D29原3影子必要条件均未触发，0已核成交；新28按原v4冻结。',
'low_position':'旧47条/46代码全路径验证；新增卫星600118、景津603279、海阳603382三条非推荐，合格成熟30日N=0。',
'dragon_tiger':'75原因行/69股，13只席位与同花顺同周期核验；原T28全部67股验证，5条D30独立条件观察。',
'combined_pair':'四份同T完整齐备；D30正式0，影子中国卫星600118/景津装备603279，条件与风险独立冻结。',
'limitup_single':'D30正式打板0；独立影子桂林三金002275，非买入建议；旧D29泰山未达实际涨停上限，无入场。'}
r['analysis_reviewed']=True;r['analyst_review_completed_at_utc']=datetime.now(timezone.utc).isoformat()
(ROOT/'tmp/analyst-combined-20261029.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'analysis_reviewed':True,'shadow_codes':[s['code'] for s in r['shadows']],'new_low_codes':[s['code'] for s in r['new_low']],'old_shadow_triggers_verified_before_new_freeze':True,'reviewed_at':r['analyst_review_completed_at_utc']},ensure_ascii=False))
