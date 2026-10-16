#!/usr/bin/env python3
"""Atomically stage Oct 16 full component reports and a frozen combined decision.

Only appends to historical records. No order placement and no invented fills.
The caller must validate, commit, deploy an exact SHA and verify production.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone, date
import json
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

from publish_market_review_20261016 import SECTOR
from research_evidence_io import load_evidence

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"backend/data"
EFILE="docs/research/combined-pair-2026-10-16-evidence.json"
T="2026-10-16"
START="2026-10-16T09:37:18+00:00"
IDS={t:t.replace("_","-")+"-20261016-close-v1" for t in ("volume_price","low_position","dragon_tiger","combined_pair")}
MARKET_ID="market-review-20261016-close-v1"
MODEL="combined_limitup_watch_v5"
PDF_ZD="https://static.cninfo.com.cn/finalpage/2026-08-13/1225470157.PDF"
PDF_FIN="https://static.cninfo.com.cn/finalpage/2026-10-08/1225591062.PDF"
TRIGGER="10月19日9:25竞价及9:30开盘均在17.40—18.10；核验正常主板10%交易、无停牌/ST/除权变化及真实涨停价。09:45—10:30内，先有17.35—17.60普通成交回踩，回踩5分钟成交量低于此前等长上冲窗口，且不破17.30；再连续5个一分钟价格点不低于17.78并向17.90推进。中信海直000099与万丰奥威002085均不低于昨收-2%且至少一只上涨；同口径全A红盘不少于2800、普通主板跌停不多于14。全部成立且有真实普通成交后，仅在17.80—18.05研究入场。缺任一时点、量价、证券状态或成交证据，不认定触发或买入。"
INVALID="竞价/开盘不在17.40—18.10；一字或只有排队报价；可见成交已高于18.30；回踩破17.30、跌破17.20、反复开板且量大价不进；对照或市场条件不成立；10:30仍未完成顺序确认；不能取得新鲜有效数据，均放弃。不得尾盘临时追入或换第二只。"
EXIT="若10月19日真实买入，最早10月20日卖出。10月20日弱开或跌破17.20时，在首个可证明可成交的时点退出全部；否则在09:30后首个普通可成交时点退出50%，余下各25%分别在首次达到18.80、19.20的可成交时点退出，未达目标的余量10:30首个可成交时点退出；若先跌破17.72则余量优先退出。仅当完整数量、时序、成交、费用可核验才计算净收益；跌停无买盘、停牌或委托未成保留敞口，后续只追加最早可执行退出，不虚构止损价成交。"


def load(name):return json.loads((DATA/name).read_text())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
def f(value,d=2):return "N/A" if value is None else f"{value:.{d}f}"
def sg(value,d=2):return "N/A" if value is None else f"{value:+.{d}f}"
def table(headers,rows):
    return "\n".join(["|"+"|".join(headers)+"|","|"+"|".join("---" for _ in headers)+"|"]+
                     ["|"+"|".join(str(v).replace("|","/") for v in r)+"|" for r in rows])


def report(task,title,summary,body,e,stamp,**extra):
    return {"id":IDS[task],"date":T,"market_date":T,"task_id":task,
            "track":"market_review" if task=="combined_pair" else task,
            "title":title,"summary":summary,"body":body,"sources":list(dict.fromkeys(e["sources"]+[p['source'] for p in e.get('issuer_primary_pdf_checks',[])]+[PDF_ZD,PDF_FIN,"https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml"])),
            "report_type":"full_daily_research","eligible_for_integrated_research":True,
            "published_at":stamp,"recorded_at":stamp,"data_cutoff_at":stamp,
            "market_data_cutoff_at":"2026-10-16T15:35:45+08:00",
            "run_id":task.replace("_","-")+"-20261016-scheduled-093718z",
            "evidence_file":EFILE,"provenance":"contemporaneous_close_research",**extra}


def volume_report(e,stamp):
    samples=e["volume_price"]["deep_samples"]
    previous=e["volume_price"]["previous_validations"]
    stats=e["volume_price"]["previous_statistics"]
    rows=[]
    for s in samples:
        rows.append([s["code"]+" "+s["name"],SECTOR[s["code"]],s["board_limit_regime"],
                     f(s["close"])+"/"+sg(s["daily_change_pct"])+"%",f(s["turnover_pct"]),
                     "/".join(f(s["rvol"][str(n)]) for n in (5,10,20)),
                     f(s["range_position_pct"]["120"],1),f(s["clv"],3),sg(s["distance_ma20_pct"]),
                     sg(s["tail_return_1400_to_1500_pct"]),s["structure"]])
    sample_table=table(["代码/名称","板块","制度","收盘/涨跌","换手%","RVOL5/10/20","120日位置%","CLV","距MA20%","14点后%","阶段"],rows)
    validation=table(["代码","开盘观察%","日高观察%","日低观察%","收盘观察%","分钟检查点数"],
                     [[r["code"],sg(r.get("open_return_pct")),sg(r.get("high_observation_pct")),sg(r.get("low_observation_pct")),sg(r.get("close_return_pct")),len(r.get("minute_checkpoints",{}))] for r in previous])
    structures=Counter(s["structure"] for s in samples)
    body=f"""一、范围、冻结与口径

T=2026-10-16；实际研究完成/冻结时间{stamp}。复用market-review-20261016-close-v1的全A有效5570只入口、120只广泛池，并对完整28只深筛独立核验。上一日28只先完成前推，随后冻结本日新28只；原样本不删。行情事实截止15:35:45，公告及披露资料截止本次实际抓取时间，完整来源/路径在{EFILE}。

RVOL5/10/20=当日量/此前5、10、20个已完成交易日均量，不含T作为分母。盘中量比没有同一时点核验快照，留空，不能与收盘RVOL混用。CLV=(收盘-最低)/(最高-最低)，高低相等时N/A。位置采用前复权120日高低区间；参考报价用未复权原价，二者不拼成收益。MA距离本轮统一为含T收盘的MA20；上一个复盘的“前一完成日MA”口径保留，数值略有差异不是行情被改写。

版本volume_price_close_v4于今天冻结：纠正10%和20%制度混标，20%股票涨约10%不称涨停；前收计算的上限仅作核对参考，不是D日官方上限。旧版本不修改，也不把本次标签修正当作经过验证的获利因子。28只原价OHLC均与Sina收盘快照一致；112只前复权历史、113只原价历史、54只五日价格点为本轮实际抓取范围，IPO中泰国际601091前复权历史缺T，保留失败、不纳入深筛统计。

二、全28只量价冻结快照

{sample_table}

每只还留有信号时间、5/10/20相对量、20/60/120位置、MA5/10/20/60、振幅、前5/20高点、尾盘量占比、9:30/9:45/10:30/午盘/14:00后/收盘价格点及来源。量比缺失；换手变化只对与前池重合的股票计算，未重合的T-1换手不臆造。分时为价格点和累计量额，不是核验OHLC、逐笔或订单簿；9:25竞价缺失，点间瞬时路径和排队成交未知。

三、五个展示样本与反例（展示不是全池替代）

1. 中鼎股份000887：收17.72、RVOL20=2.96、CLV1.000、120日位置22.4%，成交11.17亿元。11:30封住后14:40价格点17.47，14点后最低可见点17.32，收盘回17.72；尾盘量约占45%，说明经历交换后回收，而非始终一字锁住。这支持研究次日承接，却不证明锁仓或“建仓完成”。MA20仍在股价上方、次日可能高开兑现，是直接反证。
2. 龙建股份600853：RVOL20=5.42、CLV0.730、120日位置51.5%、距本轮MA20约+7.68%，尾盘-0.55%；是试板后分歧，不是已确认突破。低位启动模型可留档，但板块同步和价格推进弱于本轮最终标的。
3. 安达维尔300719：RVOL20=6.10、CLV0.721、距MA20约+4.33%、120日位置34.4%，为20%制度下未封板的放量推进；14点后-0.96%且中报亏损，不能机械把“军工涨”当成隔夜安全。
4. 丰倍生物603334：120日位置11.0%、RVOL20=3.51，但尾盘-2.13%，收盘低于MA5/MA10。这是“低位+放量”仍可能假启动的前推反例，作为低位研究样本而非综合推荐。
5. 冰山冷热000530/慈文传媒002343：高乖离、高换手、量大；中鼎同属涨停但位置与交换结构不同。不能只因封板或席位标签把拥挤风险抹去。润本股份形态尚可，但10月19日3.01257亿股首发限售股上市流通的原公告构成事件风险，优先剔除。

低位首次放量、放量突破和分歧再转强本轮有观察对象；“突破后缩量回踩”“缩量上涨”没有满足严格冻结定义的新增样本，计0而非证明失效。对放量下跌、长上影和高位爆量的验证沿用上一池全部失败记录；没有原始条件的形态不补造信号。

四、上一池28/28全部前推结果

{validation}

收盘为正8/28；开盘观察均值{sg(stats['mean_open_return_pct'])}%、中位{sg(stats['median_open_return_pct'])}%；收盘观察均值{sg(stats['mean_close_return_pct'])}%、中位{sg(stats['median_close_return_pct'])}%；日高均值{sg(stats['mean_high_observation_pct'])}%、日低均值{sg(stats['mean_low_observation_pct'])}%。这是10月15日收盘到16日的价格观察，不是策略胜率。同期上证价格观察+0.24%，同基期均值相对差约-2.08个百分点，不能当策略超额净收益。

按昨日冻结形态的分组统计及所有分钟检查点见台账；跨任务同一股票/日期关联原cohort，不能重复计样本。统计区间仅10月15→16日，规则v3，执行样本N=0：全池没有统一可核验的触发/成交/两侧退出，净收益均值、中位、盈亏比、可执行MFE/MAE与退出质量均N/A。9:50/14:40组没有可复算同口径成交对照，不能比较策略优劣；长假组不混入本组。

五、发现、买点/退出影响与新假设

上一池在市场修复时中位数仍-2.75%，否定“昨日高量强势就默认次日持有获利”。佛塑全天高12.05低于12.20，明确未触发；恩捷先回踩后最高可见点48.23未收复48.60，且日低45.71越过46.35，但缺OHLC/逐笔，严谨记“未验证完整触发”，不认定成交，也不把开盘高于48.60当入场。两只均没有可执行净收益。

本轮结构计数：{dict(structures)}。H4冻结：修复期中，低中位正常主板、适度相对量、尾盘分歧后回收且多路公开买方通道的样本，只有下一交易日顺序完成缩量回踩—再收复—板块/市场确认，才可能改善最早T+2退出。中鼎为前推、丰倍为尾盘回吐对照、冰山/慈文为高乖离对照、润本为公告风险对照；当前样本不足，不给概率、稳定胜率或自动训练承诺。10月19日若买，最早20日卖，买入日失效无法当天止损；20bp往返只作未校准费用/滑点占位，成交量、费用和买卖证据齐备前不报净收益。"""
    return report("volume_price","量价研究与验证｜2026-10-16 全28只前推与分歧承接", "完整28只新快照及上一28/28验证；价格收盘中位-2.753%，执行样本N=0；冻结v4制度/均线口径修正。",body,e,stamp,
                  model_version="volume_price_close_v4",frozen_sample_codes=[s["code"] for s in samples],coverage={"all_a":5570,"broad_pool":120,"deep":28,"previous_verified":28},deep_screen_samples=samples)


def low_report(e,stamp):
    old=e["low_position"]["existing_validations"]
    new=e["low_position"]["new_candidates"]
    body=f"""A. 新增低位启动样本（非短线买入指令）

T=2026-10-16，实际完成{stamp}。复用同日全A5570只扫描入口、120只广泛池，对28只深筛逐只重算120日位置、均线和相对量。沿用low_position_30d_v1：非旧代码、120日位置≤55%、RVOL20在2—6、CLV≥0.72、当日涨1.5%—8%、距MA20为0—15%。只有2只达到原门槛，不凑3—8只；高位连续加速、20%高波动或事件风险列比较，不自动进新池。

"""
    for s in new:
        body+=f"{s['code']} {s['name']}：收{s['close']:.2f}，涨{s['daily_change_pct']:.2f}%，成交{s['amount_cny']/1e8:.2f}亿元、换手{s['turnover_pct']:.2f}%，RVOL5/10/20={s['rvol']['5']:.2f}/{s['rvol']['10']:.2f}/{s['rvol']['20']:.2f}，20/60/120日位置="+"/".join(f(s['range_position_pct'][str(n)],1) for n in (20,60,120))+f"%，CLV{s['clv']:.3f}，MA5/10/20/60="+"/".join(f(s['ma'][str(n)],3) for n in (5,10,20,60))+f"。初始失效：收盘跌破信号日低点{s['low']:.2f}，原位冻结不后移。标签为低中位放量/待承接，不能称主力建仓完成。14点后{s['tail_return_1400_to_1500_pct']:+.2f}%；"+("尾盘回吐且MA5/10未上拐，偏反例，对综合组形成反对。" if s['code']=="603334" else "中期区间位置约一半，不是绝对底部，未封板/题材孤立风险使其仅列独立30天观察。")+"\n\n"
    body+=f"""B. 既有全部24样本，成功/失败均保留

{table(['代码/名称','原始参考','当前收盘观察%','路径MFE%','路径MAE%','自然日/交易日','当前收盘破原失效'],[[r['code']+' '+r['name'],f(r.get('reference_close')),sg(r.get('close_return_pct')),sg(r.get('path_mfe_pct')),sg(r.get('path_mae_pct')),str(r.get('elapsed_natural_days'))+'/'+str(r.get('elapsed_trading_sessions')),'是' if r.get('observed_close_below_original_invalid') else '否'] for r in old])}

24/24取得原价日线路径，全部参考日价格与当前提供者原价核验一致。双环传动、宝信软件、五方光电、蓝色光标、天顺风能当前收盘低于原失效位，共5只；不删样本，不把已有大幅浮盈当已兑现。吉林化纤、蓝色光标是既有研究股，本轮只追加价格验证理由，原长期研究不覆盖。

佛塑/恩捷10月15日量价快照与本台账关联，今天短期价格观察分别-1.89%/-4.40%；低位长期失效位分别11.45/45.05，与综合短线恩捷46.35不同，不混用。短期未触发并不等于30天模型已结案。

C. 到期与节点口径

截至T，30自然日到期0只，不报30天胜率。每只已保存全部可得日线路径，统一1/3/5/10/15/20/30自然日附近（遇休市取不晚于目标日的最近交易日）及5/10/20交易日节点；节点日与真实录入时间分开。最大有利/不利变化从原参考到观察节点，是日线价格范围，不推断先高后低或可执行回撤。未触发/停牌/缺失和初始无完整快照样本均保留。

D. 模型统计、风险与下一假设

原始样本24，新增2；30日有效完成数0，30日均值/中位、胜率、盈亏比、10%/20%达标比例均N/A。按主模型、位置、板块保留计数，价格观察不能重复计作每日新交易；模型、板块、位置、自然日/交易日分组尚不足稳定结论。日线价格基准与成交策略分离，手续费/滑点未校准20bp占位不计入价格观察；可执行净收益N=0。

本轮假设：低位首次量增若尾盘回吐且未重新站上MA5/10，30天的后续推进可能弱于分歧后回收者。丰倍生物作为可证伪样本，不因次日上涨再回改“尾盘偏弱”；龙建观察3.69/3.78能否突破及收盘是否守3.32。中鼎股份120日位置22.4%支持低位线索，但今天涨停且仍低于MA20，不满足原30天新增门槛，因此只是综合组另模型的比较对象，不偷换本模型规则。

公告核验：龙建10月13日原文列截至9月底仅8474股已转，转股价4.59，未转余额约9.99961亿元；现价3.59低于转股价，不能说已有大规模转股砸盘，但未来稀释风险仍在。丰倍近公告为闲置募集资金现金管理赎回，未核实新的强业务催化；公告检索范围及失败项留档，不证明不存在未来减持/解禁。换手、席位只作线索，不认定机构中长期买入。"""
    return report("low_position","低位启动30天｜2026-10-16 全24样本验证与2只新增", "验证24/24，保留5只当前破原失效位；新增丰倍生物、龙建股份，30自然日到期0只。",body,e,stamp,
                  research_version="low_position_30d_v1",codes=[r["code"] for r in new],existing_sample_count=24,new_sample_count=len(new),matured_30_natural_days=0)


def dragon_report(e,stamp):
    dt=e["dragon_tiger"]
    samples=dt["selected_observations"]
    rows=[]
    for s in samples:
        rows.append([s['code']+' '+s['name'],s['selected_period_reason'],f(s['buy_cny']/1e8),f(s['sell_cny']/1e8),sg(s['net_cny']/1e8),f(s['buy_concentration_top1_pct']),f(s['sell_concentration_top1_pct']),s['seat_reconciliation']['aggregate_basis']])
    body=f"""一、范围、来源与情绪

T=2026-10-16，实际完成{stamp}。东方财富66条原因记录、去重59个证券代码（含制度不同证券），同花顺61行摘要；供应商范围差异不强行做同一分母。原始行、全部去重代码、上榜原因及金额留档。全市场3301涨/2127跌，缩量修复；连板网聚合61涨停/49炸板，来源自身提示聚合61与名单59不一致；本地普通主板计算56封板/54未封/14跌停，制度与来源口径分开。新华传媒复牌11板为高度，但一字、再次停牌核查及估值风险不支持普通可买。

二、5只独立龙虎榜观察/风险样本

{table(['代码/名称','所用统计区间/原因','买亿','卖亿','净亿','买一/买前五%','卖一/卖前五%','汇总口径'],rows)}

上表金额按股票+交易日+TRADE_ID+上榜区间核对。中鼎/冰山深市汇总为买卖前五披露行并集去重后的买卖总额；沪市按各侧前五。单侧买前五不能直接与并集汇总比较，机构专用同名行不能认定同一账户。尖峰为三日累计榜，不称单日净买或与单日直接求和。同花顺按表格顺序抓取的若干席位无法绑定区间，隔离为unverified_ths_seats；本轮只用已校验的东财明细，五只金额均通过。

"""
    conditions={
        "000887":"中鼎：正常主板首板、尾盘分歧回收；仅10月19日普通连续成交、17.35—17.60回踩守住后再站17.78、汽车/低空同伴不弱时观察；一字、高开超过18.30、破17.20或量大价不进放弃。两路买方通道及股通同向，但机构专用净卖约676万元，中期MA20未收复，不能称一致锁仓。",
        "600127":"金健：涨8.86%、换手38.14%、RVOL20仅1.08、120日位置79.8%；买卖两侧均见股通/总部等通道，双向活跃不证明做T。只作高位换手反例，未缩量守14.00并重站14.70、消费无扩散不观察；高开追涨、破13.75放弃，不入综合组。",
        "603668":"天马：首板，买侧机构专用约1865万元、卖侧约747万元，不得相减认作同一机构持仓；MA/价格调整口径异常（距MA20仍约-31.9%）未消除。只有核验公司行动/复权且普通回踩7.30不破、再站7.55并有养殖同伴时研究；缺任一项放弃，不因榜净买升级。",
        "600668":"尖峰：第二板，但本次金额是三日累计。RVOL20约11.94，距MA20约+18.5%；多通道买入与一号卖方集中约45.4%并存。次日只看非一字换手守8.50后回收8.80，医药建材有同伴才观察；高开超过+5%、破8.15或两次回封失败放弃，不用三日净买证明单日锁仓。",
        "000530":"冰山：连板网标4板、换手33.24%、120日高位，公开榜单净卖约1699.5万元；机构专用买卖都大、部分通道大额退出。只留高位风险对照；一字排队、反复开板、破7.32或冷链/冰雪同伴批量转弱均放弃，不跟标签买板。"}
    for s in samples:
        body+=conditions[s['code']]+"\n\n"
        body+="买前五："+"；".join(r['OPERATEDEPT_NAME']+"买"+f((r.get('BUY') or 0)/1e4)+"万元" for r in s['buy_seats_em'])+"。\n\n"
    prev=dt['previous_validations']; st=dt['previous_statistics']
    body+=f"""三、上一组5/5完整价格前推

{table(['代码','开盘%','日高%','日低%','收盘%'],[[r['code'],sg(r['open_return_pct']),sg(r['high_observation_pct']),sg(r['low_observation_pct']),sg(r['close_return_pct'])] for r in prev])}

远东涨6.42%、华林-2.60%、欢瑞-8.26%、超声-2.36%、冰山+9.96%；收盘观察均值{sg(st['mean_close_return_pct'])}%而中位{sg(st['median_close_return_pct'])}%，日低均值{sg(st['mean_low_observation_pct'])}%。两只正收盘掩盖了多数样本的负反馈，不能把榜单净买等同次日普遍溢价。7个时点价格检查点留档，9:25竞价缺失；无统一可验证成交，执行样本N=0、策略胜率/净收益/盈亏比N/A。

四、席位画像与样本统计

本轮仅累计10月15日5只观察到16日的价格结果、16日5只新样本；按席位组合、位置、板块、情绪、封板/三日榜类型分组均是小样本，不拟合权重。成都天府大道/西安西大街在中鼎为买方、上海分公司同日亦有买卖披露；金健总部/沪股通两侧活跃；冰山有大额双向机构专用。只能描述这些可核验通道记录，不能认定最终资金身份、游资本人、量化、对倒、做T、锁仓或持有天数。历史风格/次日兑现周期缺完整分钟和账户数据，继续待验证，不补编人物画像。

DT3假设：适中RVOL、低中位、尾盘回收且金额口径一致的多路买方样本，次日承接可能优于高换手净买、三日榜与高位放量板。中鼎为前推观察；金健/冰山/尖峰为相应反例。对综合组只给条件性支持中鼎，对龙建/安达维尔（本轮榜单未出现）保持中性，未上榜不证明无机构。所有新观察最早10月19日介入、20日卖出；买入日炸板不能当天卖，涨停也不能默认排队买到。"""
    return report("dragon_tiger","龙虎榜超短｜2026-10-16 席位口径核验、全前池验证与5只观察", "66条原因/59代码；5只席位按TRADE_ID及单日/三日区间核对，上一5只收盘中位-2.358%，无可执行胜率。",body,e,stamp,
                  research_version="dragon_tiger_close_v3",codes=[s['code'] for s in samples],full_seat_samples=samples,previous_validations=prev)


def combined_report(e,stamp):
    s=next(s for s in e['volume_price']['deep_samples'] if s['code']=='000887')
    body=f"""一、唯一决策与时间锁定

T=2026-10-16，组别“综合盘后组”，唯一决策id={IDS['combined_pair']}；模型{MODEL}，冻结于北京时间{stamp}。下一交易日T+1=10月19日；若真实买入，最早T+2=10月20日可卖。只选1只：000887中鼎股份，不为凑两只增加相关风险。量化痕迹已取消，不研究、不跟踪、不作为前置。

二、四份同T真实完整研究，分别归档

{table(['模块','报告id','完成范围','支持/反对'],[['市场复盘',MARKET_ID,'已于16:53:20完成，复用同日completed回执','5570→120→28；宽度修复但炸板高，反对追涨'],['量价',IDS['volume_price'],'28只新快照/前池28全部验证','中鼎低中位、RVOL2.96、尾盘交换后回收；反对高乖离/回吐'],['低位启动',IDS['low_position'],'24历史/2新增；到期0','中鼎位置22.4%支持，但涨停且低于MA20不合原30天新样本门槛；反证保留'],['龙虎榜',IDS['dragon_tiger'],'66原因/59代码/5只金额核验/上一5只验证','中鼎多路买方及股通，但机构专用净卖、并非锁仓']])}

三、独立重新筛选与替代比较

同日全A有效5570只入口、广泛120只、深筛28只（至少10类板块），本轮额外取113只原价日线、112只前复权历史和54只五日价格点。复用同日全市场入口有原始文件与报告，不冒充本轮第二次全A扫描；全28只重新核验，而不是复制市场复盘的安达维尔/龙建两只。最终中鼎在市场复盘的深筛池内，但依据本轮量价、席位和公告复核重新排序。

- 安达维尔300719：主线支持、位置34.4%、相对量6.10，但20%制度，尾盘-0.96%、中报归母净亏约2479万元且存在再融资；对普通超短T+1退出风险高，列独立市场组，不升综合。
- 龙建股份600853：低位模型达标、RVOL5.42，但120日位置51.5%只是中位，试板未封、尾盘-0.55%、基建同伴持续性弱于汽车/低空，量能和流动性不及中鼎；不为凑第二只复制。
- 丰倍生物603334：低位11.0%却尾盘-2.13%、未站MA5/10，仅列低位30天反例。
- 润本股份603193：量价尚可，10月19日3.01257亿股（占总股本74.46%）首发限售股上市流通，公告风险否决；不等于这些股一定卖出。
- 冰山冷热000530/慈文传媒002343：中期乖离高、换手拥挤；中鼎的低位置、成交容量和回收结构相对好，但并不消除其炸板风险。
- 天马科技603668：席位正向但复权/均线异常未消除；尖峰600668三日榜、高相对量，均不替代可执行性。

近5实际交易日可用完整综合组为10月9/12/15日（3/5，13/14缺完整决定），中鼎在这些组中0次；近10日可用完整组也不连续，因此只报“已留存样本未重复”，不虚报完整5/10日重复率，不为了降低重复硬换股。

四、候选000887中鼎股份完整条件卡

模型：低中位反包首板后的分歧承接/板块共振，不是已经确认的中期趋势反转。冻结参考17.72元（10月16日15:00收盘，原价，非成交价）；日涨9.99%、成交11.17亿元、换手4.91%、RVOL5/10/20=3.18/3.28/2.96、CLV1.000、120日位置22.4%，本轮MA20约18.46，距其约-4.03%。14点后价格点最低17.32、14:40为17.47、收17.72，尾盘量约占45.0%。

席位：同一单日记录净买1.5226亿元（并集口径），买前五第一通道占32.9%；成都天府大道、西安西大街、上海分公司与深股通出现在买方。深股通披露净买约1322万元，同时机构专用披露净卖约676万元；不能说机构与游资一致，更不能说资金已锁仓。公司8月澄清腾讯云合作仅框架、未产生收入，10月8日更新可转债注册稿财务数据；本轮没有核实新的公司级订单/业绩催化，市场汽车/低空标签不证明Roadster、飞行汽车订单或合作落地。

10月19日确认：{TRIGGER}

研究介入区间17.80—18.05。支撑观察17.35—17.60/17.30，初始失效17.20（低于T尾盘可见17.32，留出波动但不是保证止损价）；T全天低16.00为更深反例，不把它后移成新止损。放弃条件：{INVALID}

若10月19日买后跌破17.20，A股T+1不能当天卖：不加仓、不摊低，不用盘中反抽虚构当日卖出；保留到最早10月20日并承担跳空、跌停及流动性风险。T+1涨停只形成浮盈，直接涨停/一字无真实普通成交记未成交，不记入场。

10月20日及更晚退出冻结：{EXIT}

涨停路径仅为假设：19日先缩量守17.35—17.60→重站17.78/17.90→汽车/低空扩散→回收MA20附近18.46→18.80/19.20；按T收17.72静态计算19日正常10%上限约19.49，真实涨停价须当天核验，20日涨停价取决于19日实际收盘，不能预填。反例：高开透支、尾盘回封次日兑现、低于MA20反弹失败、行业一日游或机构卖方扩大。即使T+2涨停也不保证退出成交或之后溢价；不报未校准涨停概率。

五、上一综合组T+1真实验证

000973佛塑：开11.99、高12.05、低11.79、收11.96，相对原参考12.19收盘观察-1.89%；全天最高低于必要12.20，明确未触发、未成交，执行收益N/A。

002812恩捷：开48.99、高49.35、低45.71、收46.26，参考48.39收盘观察-4.40%；09:31价格点47.88进入回踩区，之后最高可见价格点48.23，未验证先回踩后收复48.60，日低还越过46.35。原market_review写“未触发”；本轮证据分级收紧为“可得价格点未验证完整顺序，未认定触发/成交，日内失效位已越过”。缺分钟OHLC/逐笔不能排除点间短时触价，不虚构确定成交或净收益，也不把盘中+1.98%当已赚。

上一全28池收盘均值-1.835%、中位-2.753%，日高均值+3.864%、日低均值-5.477%；与本组没有成交收益的事实分开。价格观察不是策略盈利。新组仅一个冻结候选、未来触发与可执行收益样本仍0；下一批继续记录9:25、开盘、9:45、10:30、午盘、14点后、收盘，3/5/10/20/30交易日及MFE/MAE，保留失败/未触发/停牌/无法成交。费用滑点20bp未校准，未取得数量、两侧成交、税费前策略净收益N/A。

六、量价研究与验证及下一交易日重点

全28只冻结快照与前池28/28已在独立volume_price报告及台账，不只最终标的。新版本v4将涨停制度和MA截止口径分开，combined v5进一步冻结顺序、5分钟量比较及50/25/25退出权重，只向后验证，不能回看改原条件。H5：在宽度修复但昨日活跃股仍负反馈时，低中位+适度RVOL+分歧回收+披露买方通道的组合，是否比高乖离爆量组改善T+2可执行退出；当前无校准证据，待前推。

10月19日关键：①炸板/跌停不再扩散、全A宽度维持；②中鼎普通回踩成交及汽车/低空同伴承接；③18.46附近量增是否推动价格，而不是放量滞涨。不满足则0只入场。独立打板D=10月16日缺失事前报告，本轮补盘后v2审计，不制造当天打板候选，也不把审计当按时完成；不混入本组推荐。

术语：CLV为收盘在全天高低区间的位置；RVOL为相对过去完成交易日均量；MFE/MAE是冻结参考后的最大有利/不利价格变化，缺成交时只能作价格观察。APP不内置大模型、不自动训练权重，也不因使用次数增加自然提高胜率。"""
    return report("combined_pair","盘后综合双标｜2026-10-16 仅中鼎股份条件观察", "四份同T完整研究齐备；全A5570→120→28，只选中鼎股份1只用于10月19日竞价后二次验证，最早20日退出。",body,e,stamp,
                  model_version=MODEL,strategy="combined_limitup_watch",codes=["000887"],selected_codes=["000887"],coverage={"all_a_entry":5570,"broad_pool":120,"deep_reviewed":28,"selected":1},
                  dependency_report_ids=[MARKET_ID,IDS['volume_price'],IDS['low_position'],IDS['dragon_tiger']],planned_entry_date="2026-10-19",earliest_legal_exit_date_if_bought="2026-10-20")


def limitup_audit(e,stamp):
    contexts=e.get('limitup_market_contexts',{})
    rows=[]
    archived_kpi={'2026-10-13':{'limit_up':67,'zhaban':21,'limit_down':10,'max_board':3},
                  '2026-10-14':{'limit_up':36,'zhaban':30,'limit_down':13,'max_board':4},
                  '2026-10-15':{'limit_up':36,'zhaban':7,'limit_down':26,'max_board':5}}
    for day in ('2026-10-13','2026-10-14','2026-10-15'):
        meta=contexts.get(day,{}).get('public_metadata',{}).get('kpi') or archived_kpi[day]
        rows.append([day,meta.get('limit_up','待补'),meta.get('zhaban','待补'),meta.get('limit_down','待补'),meta.get('max_board','待补')])
    body=f"""本报告是实际于{stamp}完成的盘后补证，计划交易日D=2026-10-16，D盘前最新完成日T=10月15日。D已经收盘，无该日事前冻结报告、候选、证券状态、盘口或成交回报；本轮不能重新编一个10月16日打板推荐，更不能把今天结果塞回昨日已知。独立原配置/历史不改变。

一、v2固定先后顺序的回溯核查

最近三日可得情绪：
{table(['日期','封板聚合','炸板','跌停','最高板'],rows)}

本表在本轮逐日名单接口返回403时，复用仓库已冻结的10月15日打板v2、10月15日市场复盘中已有数值，不称本轮重新拿到了完整名单；10月13/14最高为当时活跃可交易普通主板可见高度，新华传媒停牌另列。逐日明细接口限制没有绕过，错误写入证据，完整逐层分母仍缺失。

10月13日修复，14日再退潮，15日普跌；收盘只有429涨/5108跌，涨停36、跌停26—28（来源/制度分开），首板晋级2/21、二板以上4/15。高位缩量/断板负反馈和低层晋级低同时存在。T=10月15日新华传媒停牌，历史空间参照10板不是当日可交易高板；16日复牌11板是D实际发生的新事实，严禁用于伪造D盘前选股。

高度/空间/分层：10月15日按公开聚合可见最高5板，逐层普通主板名单与停牌/断板分母仍缺完整可复算来源；原总体晋级率不能硬拆为每层。T前20个交易日可确认至少曾到10板，但缺全窗口完整历史，不把“至少10”说成完整20日最高。补证保留这些缺项，未达完整v2事前执行门槛。

二、至少三只真实T备选（均为回溯风险比较，不是D荐股）

- 冰山冷热000530：T收6.93、换手41.05%、RVOL20约16.99、高位封板，D买入可行性不明；D实际收7.62不能倒推盘前应选或排队可买。
- 华林证券002945：T收15.39封板、相对量6.42、120日位置约74.9%；D实际收14.99（约-2.60%），说明封板/榜净买不等于隔夜溢价。
- 远东股份600869：T收18.08、相对量1.19而榜单净买高，缺首次放量确认；D实际上涨只作为反例，不重写昨日选择。
- 欢瑞世纪000892：T高换手、低CLV、尾盘回吐；D收跌8.26%，风险验证不是策略亏损。

原v1龙溪股份600592保持10月8日未触发/无持仓、10月9日D+1仅价格观察；v2此前已归档4轮完整盘前决定均空仓，新候选和可验证成交0。今天没有事前决定，不能把缺报算第5轮空仓；首板/二板/回封的策略封板率、炸板率、净收益、盈亏比、尾部亏损全部N/A。

三、不可恢复边界与下一步

9:25、09:35—10:30回封时序、真实涨停价/证券状态、持续盘口、队列成交和事前冻结条件缺失，盘后日线/价格点不能恢复。未接Level-2、不承诺持续盯盘。本次真实回执blocked表示原D事前交付无法补成按时完成，附本完整审计；不是waiting登记。D=10月19日新的独立v2盘前研究应以当时最新公告和同一规则重新冻结，当前不发布替代打板标的，也不擅改任务时间/启停。若今后D=19真实买入最早20日卖出；买入当日炸板不可当天卖，停牌/跌停不能保证退出。"""
    return {"id":"limitup-single-20261016-retro-v2","date":T,"task_id":"limitup_single","track":"market_review",
            "title":"每日打板v2补证｜10月16日缺事前冻结，不补造当日荐股",
            "summary":"已按v2复核T三日环境、空间/晋级缺项与四只真实备选；D已收盘且无事前条件/盘口，原交付仍blocked。",
            "body":body,"sources":e['sources']+["https://lianban.net/days/2026-10-15.html"],"published_at":stamp,
            "recorded_at":stamp,"data_cutoff_at":stamp,"report_type":"retrospective_review",
            "eligible_for_integrated_research":False,"provenance":"retrospective_evidence_audit",
            "planned_entry_date":T,"latest_completed_trading_day":"2026-10-15","research_rule_version":"limitup_single_v2",
            "candidate_count":0,"recommendation_ids":[],"not_a_contemporaneous_cash_decision":True,"evidence_file":EFILE}


def add_observations(e,stamp,recs,volume,low):
    prior_index={r['code']:r for r in e['prior_combined']}
    for rec in recs['items']:
        if rec.get('id') not in ('combined-pair-20261015-000973-close-v1','combined-pair-20261015-002812-close-v1'):continue
        row=prior_index[rec['code']]
        observation={**row,"id":rec['id']+'-t1-20261016',"date":T,"market_date":T,"as_of":T,
                     "recorded_at":stamp,"horizon":1,"reference_price":rec['reference_price'],
                     "report_ids":[IDS['combined_pair']],"price_observation_only":True,
                     "entry_fill_status":"no_verified_entry","executable_mfe_pct":None,"executable_mae_pct":None,
                     "status":"not_triggered" if rec['code']=='000973' else "trigger_not_verified_in_available_price_points",
                     "invalidation_reached":False if rec['code']=='000973' else True}
        if rec['code']=='002812':observation['trigger_status']='full_sequence_not_verified_minute_points_not_ohlc'
        rec.setdefault('results',[]).append(observation)

    # Append missing 1/3/5/10/20/30-session price nodes for all saved combined
    # originals when actual dated daily bars are available. Never invent fills.
    for rec in recs['items']:
        if rec.get('strategy')!='combined_limitup_watch':continue
        bars=e['raw_daily_histories'].get(rec['code'])
        if not bars:continue
        subsequent=[b for b in bars if rec['date']<b['date']<=T]
        ref=rec.get('reference_price')
        if not ref:continue
        for h in (1,3,5,10,20,30):
            if len(subsequent)<h:continue
            end=subsequent[h-1]; result_id=rec['id']+f'-price-node-{h}-{end["date"].replace("-","")}'
            if any(r.get('id')==result_id for r in rec.get('results',[])):continue
            path=subsequent[:h]
            rec.setdefault('results',[]).append({
                "id":result_id,"date":end['date'],"market_date":end['date'],"as_of":end['date'],"recorded_at":stamp,
                "horizon":h,"status":"price_observation_only","reference_price":ref,"close":end['close'],
                "close_return_pct":round((end['close']/ref-1)*100,3),
                "daily_path_mfe_pct":round((max(b['high'] for b in path)/ref-1)*100,3),
                "daily_path_mae_pct":round((min(b['low'] for b in path)/ref-1)*100,3),
                "price_observation_only":True,"trigger_status":"see_original_frozen_trigger_and_prior_results",
                "entry_fill_status":"not_reconstructed_from_daily","executable_net_return_pct":None,
                "source_report_ids":[IDS['combined_pair']],"source_urls":["https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"],
                "note":"迟到补证用真实recorded_at；节点日不是推荐发布时间；日高低不推断成交顺序，成本和可执行净收益未知。"})

    previous=e['volume_price']['previous_validations']
    volume['items'].append({"id":"volume-price-20261015-validation-20261016-v1","date":T,"kind":"forward_validation",
                           "task_id":"volume_price","recorded_at":stamp,"origin_cohort_id":"volume-price-20261015-close-v1-cohort",
                           "rule_version":"volume_price_close_v3","report_ids":[IDS['volume_price']],
                           "full_pool_summary":e['volume_price']['previous_statistics'],"full_validation_completed":True,
                           "executable_sample_count":0,"eligible_for_model_statistics":True,
                           "full_pool_validations":[{**r,"id":"volume-price-20261015-"+r['code']+"-validation-20261016",
                                                     "date":T,"recorded_at":stamp,"report_ids":[IDS['volume_price']],
                                                     "full_validation_completed":True,"eligible_for_model_statistics":True,
                                                     "reference_verified_against_current_provider":True,
                                                     "origin_cohort_id":"volume-price-20261015-close-v1-cohort",
                                                     "daily_high_price_excursion_pct":r['high_observation_pct'],
                                                     "daily_low_price_excursion_pct":r['low_observation_pct']} for r in previous]})
    volume['items'].append({"id":"volume-price-20261016-close-v1-cohort","date":T,"task_id":"volume_price",
                           "report_ids":[IDS['volume_price']],"rule_version":"volume_price_close_v4","frozen_at":stamp,
                           "data_cutoff_at":"2026-10-16T15:35:45+08:00","broad_pool_count":120,"deep_screen_count":28,
                           "eligible_for_model_statistics":True,"provenance":"contemporaneous_close_research",
                           "samples":e['volume_price']['deep_samples'],"rule_change":e['volume_price']['rule_change']})
    by_id={s['id']:s for s in low['items']}
    for observation in e['low_position']['existing_validations']:
        sample=by_id[observation['origin_cohort_id']]
        sample.setdefault('observations',[]).append(dict(observation,recorded_at=stamp))
        bars=e['raw_daily_histories'][sample['code']]
        original=date.fromisoformat(sample['date'])
        nodes=[]
        for h in (1,3,5,10,15,20,30):
            target=date.fromordinal(original.toordinal()+h)
            if target>date.fromisoformat(T):continue
            allowed=[b for b in bars if sample['date']<=b['date']<=target.isoformat()]
            if allowed:nodes.append({'kind':'natural_day','horizon':h,'target_date':target.isoformat(),'bar':allowed[-1]})
        post=[b for b in bars if sample['date']<b['date']<=T]
        for h in (5,10,20):
            if len(post)>=h:nodes.append({'kind':'trading_session','horizon':h,'target_date':post[h-1]['date'],'bar':post[h-1]})
        for n in nodes:
            nid=sample['id']+f"-{n['kind']}-{n['horizon']}"
            if any(x.get('id')==nid for x in sample['observations']):continue
            b=n['bar']; ref=sample['day0_close']; path=[x for x in bars if sample['date']<x['date']<=b['date']]
            sample['observations'].append({"id":nid,"date":b['date'],"recorded_at":stamp,"target_date":n['target_date'],
                                           "horizon":n['horizon'],"horizon_type":n['kind'],"close":b['close'],
                                           "close_return_pct":round((b['close']/ref-1)*100,3),
                                           "path_mfe_pct":round((max(x['high'] for x in path)/ref-1)*100,3) if path else None,
                                           "path_mae_pct":round((min(x['low'] for x in path)/ref-1)*100,3) if path else None,
                                           "observation_type":"price_observation","executable_net_return_pct":None,
                                           "report_ids":[IDS['low_position']],"source_urls":observation['source_urls'],
                                           "note":"自然日遇休市取不晚于目标日最近交易日；迟到录入不冒充当时已知。"})
    for s in e['low_position']['new_candidates']:
        low['items'].append({"id":"low-position-20261016-"+s['code'],"date":T,"recorded_at":stamp,
                             "code":s['code'],"name":s['name'],"sector":SECTOR[s['code']],"primary_model":"低中位放量推进/平台确认",
                             "day0_close":s['close'],"invalid_close_below":s['low'],"initial_invalidation_basis":"收盘跌破信号日低点；不后移",
                             "original_snapshot_provenance":"contemporaneous_full_market_and_crosschecked_daily",
                             "original_snapshot_verified":True,"eligible_for_model_statistics":True,
                             "day0_rvol20":s['rvol']['20'],"day0_turnover_pct":s['turnover_pct'],"day0_amount_yi":s['amount_cny']/1e8,
                             "day0_clv":s['clv'],"day0_range_position_pct":s['range_position_pct'],"day0_moving_averages":s['ma'],
                             "snapshot":s,"report_ids":[IDS['low_position']],"observations":[],"sources":[EFILE,s['daily_source']]})
    low['updated_at']=stamp


def main():
    e=load_evidence(ROOT/EFILE)
    assert len(e['volume_price']['deep_samples'])==28
    assert all(s['seat_reconciliation']['matched'] for s in e['dragon_tiger']['selected_observations'])
    assert len(e['low_position']['existing_validations'])==24
    now=datetime.now(timezone.utc); stamp=now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
    utc=now.isoformat(timespec='seconds')
    research,recs,runs,volume,low=map(load,['research.json','recommendations.json','task_runs.json','volume_price_samples.json','low_position_samples.json'])
    if any(r['id']==IDS['combined_pair'] for r in research['items']):
        print('duplicate decision: no report or candidate changed');return
    reports=[volume_report(e,stamp),low_report(e,stamp),dragon_report(e,stamp),combined_report(e,stamp)]
    research['items'].extend(reports)
    audit=limitup_audit(e,stamp); research['items'].append(audit)
    newrec={"id":"combined-pair-20261016-000887-close-v1","date":T,"published_at":stamp,"task_id":"combined_pair",
            "code":"000887","name":"中鼎股份","group":"close","group_label":"综合盘后组","strategy":"combined_limitup_watch",
            "model":MODEL,"reason":"全28只重新裁决后仅保留中鼎；120日低中位、适度RVOL、11.17亿元容量、尾盘交换回收及金额已核对的多通道买方；MA20未收复、机构通道净卖和高开买不到为反证。",
            "reference_price":17.72,"reference_price_time":"2026-10-16T15:00:00+08:00","reference_price_market_date":T,
            "reference_price_source":"https://qt.gtimg.cn/q=sz000887","reference_price_cross_check":"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000887,day,,,180,none",
            "trigger":TRIGGER,"invalid":INVALID,"exit_plan":EXIT,"sources":reports[-1]['sources'],"provenance":"contemporaneous",
            "report_ids":[IDS['combined_pair']],"planned_entry_date":"2026-10-19","earliest_legal_exit_date_if_bought":"2026-10-20",
            "entry_price_condition_range":[17.80,18.05],"invalid_level":17.20,
            "rules":{"version":MODEL,"frozen_at":stamp,"entry_sequence_required":True,"entry_window_cn":["09:45","10:30"],
                     "auction_open_range":[17.40,18.10],"pullback_range":[17.35,17.60],"pullback_floor":17.30,
                     "reclaim":17.78,"hold_minute_price_points":5,"invalid_level":17.20,
                     "peer_codes":["000099","002085"],"peers_each_min_change_pct":-2,"at_least_one_peer_positive":True,
                     "same_scope_advance_min":2800,"ordinary_mainboard_limit_down_max":14,
                     "exit_weights_pct":[50,25,25],"remaining_exit_deadline_cn":"10:30",
                     "cost_assumption":{"round_trip_bps":20,"calibrated":False,"use_for_executable_statistics":False}},
            "frozen_snapshot":next(s for s in e['volume_price']['deep_samples'] if s['code']=='000887'),
            "results":[{"id":"combined-pair-20261016-000887-close-v1-frozen","recorded_at":stamp,"market_date":"2026-10-19",
                        "status":"pending_auction_revalidation","trigger_status":"not_observable_before_entry_day",
                        "entry_fill_status":"not_entered","executed_trade":False,"executable_net_return_pct":None}]}
    add_observations(e,stamp,recs,volume,low)
    recs['items'].append(newrec)
    for r in reports:
        runs['items'].append({"id":r['run_id']+'-completed',"run_id":r['run_id'],"task_id":r['task_id'],"date":T,
                              "trigger":"scheduled","started_at":START,"recorded_at":utc,"completed_at":utc,"status":"completed",
                              "summary":r['summary'],"report_ids":[r['id']],"analysis_completed":True,
                              "recommendation_ids":[newrec['id']] if r['task_id']=='combined_pair' else [],"sources":[EFILE],
                              "started_at_scope":"本次实际综合执行开始，含该模块读取、取证与分析；独立归档"})
    runs['items'].append({"id":"limitup-single-20261016-retro-audit-blocked","run_id":"limitup-single-20261016-retro-audit",
                          "task_id":"limitup_single","date":T,"trigger":"scheduled","started_at":START,"recorded_at":utc,
                          "completed_at":utc,"status":"blocked","summary":"D=10月16日事前报告缺失；已完成盘后v2补证审计，不能恢复当时冻结/盘口，不补造荐股或冒称按时完成。",
                          "report_ids":[audit['id']],"recommendation_ids":[],"analysis_completed":False,"sources":[EFILE]})
    # Existing watchlist reasons append separately; never auto-add a local watch.
    catalog=load('research_stocks.json')
    for code in ('000420','300058'):
        stock=next(s for s in catalog['items'] if s['code']==code)
        obs=next(s for s in e['low_position']['existing_validations'] if s['code']==code)
        stock['history'].append({"id":f"research-stock-{code}-20261016-low-validation","date":T,"recorded_at":stamp,
                                 "title":"30天台账日线验证（非新推荐）","reason":f"{stock['name']}原样本保留，本次收盘相对初始参考{obs['close_return_pct']:+.2f}%；不是成交策略收益。",
                                 "evidence_status":"verified_daily_price_observation","fact_note":"原始快照、失效位与旧理由不改写；本轮仅日线补证。",
                                 "validation":["继续原30自然日与5/10/20交易日节点；未到期不报成功率。"],"risk":"不能从日线高低推断进出顺序、资金身份或可执行净收益。",
                                 "report_ids":[IDS['low_position']],"sources":[EFILE]})
    catalog['items'].append({"code":"000887","name":"中鼎股份","sector":"汽车零部件","role":"research","default_watch":False,
                             "history":[{"id":"research-stock-000887-20261016-combined","date":T,"recorded_at":stamp,
                                         "title":"综合盘后组条件观察，不是长期买入结论","reason":newrec['reason'],
                                         "evidence_status":"verified_same_day_daily_seats_and_issuer_risk","fact_note":"参考17.72是收盘报价；10月19日顺序条件未发生，不代表已成交。",
                                         "validation":[TRIGGER,"最早10月20日合法退出；后续只追加触发、失败、成交/无法成交及价格节点。"],
                                         "risk":INVALID+" 公司已明确腾讯云框架合作未产生收入；可转债与低于MA20风险保留。",
                                         "report_ids":[IDS['combined_pair'],IDS['dragon_tiger']],"sources":[EFILE,PDF_ZD,PDF_FIN]}]})
    for name,doc in [('research.json',research),('recommendations.json',recs),('task_runs.json',runs),('volume_price_samples.json',volume),('low_position_samples.json',low),('research_stocks.json',catalog)]:save(DATA/name,doc)
    save(ROOT/'app/src/main/assets/research_stocks.json',catalog)
    for r in reports+[audit]:
        (ROOT/'docs/research'/ (r['id']+'.md')).write_text(r['body']+'\n')
    print(json.dumps({"completed_at":utc,"reports":[r['id'] for r in reports],"candidate":newrec['id'],"limitup":audit['id']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
