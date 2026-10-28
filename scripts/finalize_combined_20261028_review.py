"""Finish the per-stock analytical review before publishing the frozen signals.

The original 01:44:05 signal freeze is preserved. This separately timestamped
review documents the whole pool, and corrects report-completion timestamps to
the actual end of analysis; it never revises prior published records.
"""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import gzip,hashlib,json
from publish_combined_20261028 import ROOT,IDS,T,D,EV,EXP,table
REVIEW={
 '000554':('低中位箱体突破','收6.63超过原20日高6.50、MA60转回上方，量增能推进；午后板上价格持平。','RVOL5 5.44及换手15.18%容易次日分歧；营收下降、油品同伴未共振，不能确定资金建仓。'),
 '300539':('放量突破/尾盘再推进','超过19.68旧高，CLV0.967、14时后+3.051%，有后续价格推进。','20%制度、MA20乖离23.83%、换手23.68%；累计利润/现金流下降，排除本次10%主板影子但保留复盘原影子。'),
 '300980':('低位放量修复失败风险','长期位置11.09%、相对量4.87，提供低位大成交对照。','收盘低于MA20、CLV0.549、尾盘-0.569%，未破24.66旧高；Q3利润大降，不把低位即等同吸筹。'),
 '605488':('高位放量加速/兑现风险对照','本日真实48.61封板与尾盘推进独立补证，原池遗漏不抹去。','MA20乖离51.92%、长期顶部，营收增而Q3净利大降；盘中开板与最终封板可以并存。'),
 '600828':('放量平台突破/二板接力','收4.92超过4.86旧高、CLV1、RVOL20 5.23，平台推进可观察。','长期位置74.76%、接力后隔夜依赖零售主线和高标反馈；无新的完整公告核验不声称经营无风险。'),
 '002696':('高位反包/尾盘推进','尾盘+6.036%、机构/总榜净买与本期价格推进同向。','长期位置91.91%、MA20乖离33.37%，尚未越12.40旧高；反包不是连续新增低位首板。'),
 '300549':('20%制度放量突破','超过16.23、尾盘+3.097%、CLV0.904，优于只有单笔拉升的形态。','RVOL20 5.99、换手16.38%且经营现金流-66.81%；不能把大成交直接认定机构身份。'),
 '603337':('高位放量加速/绝对强度对照','突破47.51、尾盘+2.155%、CLV1，为H3绝对强度真实对照。','长期顶部、MA20乖离32.70%，原公告机器人营收利润占比极低；不拿概念替代主营业绩。'),
 '603109':('低中位放量修复，尚非突破','长期位置31.67%、收复MA60，量增后价格收高。','未复权旧高17.99仍未破、尾盘持平不能证明主动承接；Q3归母-64%，仅入独立30天样本。'),
 '603037':('较高均线乖离突破/H1对照','突破11.87、RVOL20 3.48、收盘高位，记录强价格推进。','MA20乖离25.09%，虽120日位置仅63.53%仍属于高短期乖离亚组；不谎称所有时间尺度都高位。'),
 '001400':('低中位箱体突破/二板确认','突破86.66、长期位置16.86%，RVOL20 2.15，量能比极端爆量更温和。','本次选中的是多日龙虎榜，机构净卖与股通净买背离；二板后的隔夜晋级压力不得按低位标签豁免。'),
 '301225':('20%制度突破后高位分歧','超过65.88、相对量2.45，保留突破样本。','MA20乖离26.59%、CLV0.662、尾盘-1.736%，突破后兑现反例，不凭最高涨幅判断可实现收益。'),
 '688836':('历史不足下的高乖离分歧','短期均线向上、尾盘价格小幅推进，保留公开可观察事实。','120日位置/MA60历史不足N/A；MA20乖离39.20%、CLV0.645且未破737.50，不能补造长期低位或混主板10%统计。'),
 '300718':('放量反弹/承接未确认','长期位置24.88%、量增后相较均线有修复，留作低位反弹对照。','未破58.50、CLV0.606、尾盘仅+0.182%，后续承接不如横河/优德；公告与资金结构未全面核验。'),
 '600078':('低位放量修复/首板','长期位置13.26%、CLV1，累计利润改善，股通本期净买可核。','未收MA60、未破10.45，现金流下降且Q4项目减值；不是成熟主升，不能把季报累计增长当持续资金流入。'),
 '603131':('低中位平台突破','超过14.28、长期位置16.25%、RVOL20 3.53，属于真实突破研究。','尾盘板上持平不证明主动加仓；本轮未取得足够准确公告与详细席位证据，保留候选但正式淘汰。'),
 '002889':('高位反包/修复','CLV1、RVOL20 2.25，价格相较均线修复。','长期位置74.59%、未破17.31旧高，反包与创新高不同；主线持续与隔夜承接缺独立证据。'),
 '001296':('低中位放量修复','MA60附近修复、相对量3.37、CLV1；可见承接价格强于大上影。','仍未破20.75旧高；Q3归母-50.68%、累计现金流-65.98%，形态不能消除经营反证。'),
 '002172':('弱势中的相对缩量反弹','CLV1但RVOL20仅1.074，提供低量上行和强放量的对照。','收盘低于MA20约7.70%、未破6.27旧高；量小不等同抛压已完全耗尽，不能机械评为吸筹。'),
 '003028':('中位放量突破','超过24.53、RVOL20 3.46、CLV1，价格对大成交有推进。','长期位置50.66%、MA20乖离11.15%；缺独立完整公告/席位结构核验，不能单因智能控制标签认定主线核心。'),
 '603081':('放量修复，旧高待过','RVOL20 3.32、CLV1，修复价位与量能同向。','未破11.72旧高、MA20乖离16.25%，没有确认平台突破；题材持续、资金身份与催化未查全。'),
 '688286':('高乖离长上影/兑现风险','相对量2.38、尾盘+1.985%反映价格曾修复。','MA20乖离33.50%、CLV0.479，仍未破67.53；尾盘回升不能抹去上影和盘中回撤，20%制度另列。'),
 '603926':('低中位放量修复','长期位置30.17%、收复MA60、累计现金流改善，选择综合影子第2。','未破17.96，尾盘板上持平非已核主动资金；Q3单季下降，正式仍不合格，不能以年内累计数字掩盖。'),
 '300986':('低位放量但弱CLV修复','长期位置11.54%、RVOL20 3.19，作为大成交后未充分推进的反例。','CLV0.520、尾盘-0.365%、未破12.10；价格位置低不自动有可执行隔夜质量。'),
 '603699':('低位修复/尾盘承接待证','长期位置12.50%、CLV0.997、尾盘+1.346%，选择综合影子第1。','38.39距真实上限38.40差一分钱，未收MA20/60；Q3缺失/半年现金流下降与除息口径风险独立保留。'),
 '603633':('低中位放量修复/首板对照','长期位置29.45%、收复MA60、成交额1.64亿与铁流处于相近量级。','未破6.50；Q3仍亏、担保总额139.22%净资产；研究留对照而非因为便宜/机器人概念而推荐。'),
 '300421':('低中位放量修复','长期位置36.08%、CLV0.812、尾盘+1.398%，后续推进好于尾盘回落组。','仍未破18.26，20%制度、催化和席位结构未充分核验；不能按尾盘上行推断锁仓。'),
 '300473':('高位置突破/分歧','超过41.94旧高、RVOL20 1.76、尾盘+0.495%，保留突破样本。','120日位置93.52%、CLV0.746而非封板承接；低相对量与高位置结合不等于无抛压，20%制度独立。')}
def load(p):return json.loads((ROOT/p).read_text())
def main():
 research=load('backend/data/research.json');runs=load('backend/data/task_runs.json');manifest=load('docs/research/combined-pair-20261028-publication-manifest.json')
 e=json.loads(gzip.decompress((ROOT/EV).read_bytes()));x=load(EXP)
 assert 'analyst_deep_review' not in e,'Review already frozen; append a revision instead.'
 stamp=datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
 assert datetime.fromisoformat(stamp)<datetime.fromisoformat(D+'T09:30:00+08:00')
 rows=[];lhb=e['lhb_lists'][T]['payload']['result']['data'];lhbcodes={r['SECURITY_CODE'] for r in lhb}
 for s in e['derived']['deep_recomputed']:
  c=s['code'];model,support,risk=REVIEW[c]
  rows.append({'code':c,'name':s['name'],'analyst_review_recorded_at':stamp,'model':model,'support':support,'counterevidence':risk,
   'prior_20_high':s['previous_20_session_high'],'T_low_structural_reference':s['low'],
   'next_confirmation':'D29 9:25/9:45/10:30核验板块、VWAP与真实承接；如上破原20日高后仍能缩量回踩并重新推进才支持该突破假设，未过旧高者只叫修复。无时序/成交证据不计触发。',
   'abandon':'关键结构失守、爆量不能推进、板块转弱或状态/报价无法核验。价格跌破T低点用于结构反证，不保证能止损成交。',
   'flow_evidence':'本期公开龙虎榜有该代码；详细席位仅对本报告已核8只给数，不向其他股票编造席位。' if c in lhbcodes else '本轮当日可得龙虎榜未见该代码；不等同没有机构/游资交易，不推断资金身份。',
   'sources':[s['source'],s['minute_checkpoints']['source'],e['lhb_lists'][T]['source']],
   'entry_earliest_legal_exit_if_bought':'2026-10-30T09:30:00+08:00','is_recommendation':False})
 t=table(['28只逐股研究，非推荐','模型/阶段','支持','反证与未入选原因','旧高/T低结构参考'],[[r['code']+' '+r['name'],r['model'],r['support'],r['counterevidence'],str(r['prior_20_high'])+'/'+str(r['T_low_structural_reference'])] for r in rows])
 text='逐股分析补充｜实际完成'+stamp+'\n\n'+t+'\n\n所有股票D29的9:25/9:45/10:30、午盘/14时后/收盘继续验证。突破要求越过上表旧高后有可核验的回踩和价格再推进；未越旧高只叫修复。放量不推进、板块掉队或失T低点用于反证，无逐笔/排队证据不认定成交。入选当日不可卖，D29买入最早D30；原影子冻结'+x['frozen_at']+'与原始价格/条件保持，不改市场复盘或原推荐。完整逐股资金证据边界及来源见压缩原始证据。'
 e['analyst_deep_review']={'recorded_at':stamp,'rows':rows,'original_shadow_freeze_preserved':x['frozen_at'],'note':'Additional qualitative full-pool review before planned D open; original signal snapshots and chosen codes unchanged.'}
 for r in research['items']:
  if r['id'] not in manifest['new_report_ids']:continue
  old=manifest['analysis_completed_at'];r['body']=r['body'].replace('实际本次冻结/完成'+old,'本轮信号首次冻结'+old+'；完整分析完成'+stamp)
  r['published_at']=stamp;r['recorded_at']=stamp;r['analysis_completed_at']=stamp
  if r['task_id'] in ('volume_price','combined_pair'):
   r['body']+='\n\n'+text;r['analyst_deep_review_count']=28
  (ROOT/f'docs/research/{r["id"]}.md').write_text('# '+r['title']+'\n\n'+r['body']+'\n\n来源：\n\n'+'\n'.join('- '+s for s in r['sources'])+'\n')
 for a in runs['items']:
  if any(rid in manifest['new_report_ids'] for rid in a.get('report_ids',[])):
   a['completed_at']=stamp;a['recorded_at']=stamp
 e['actual_completed_at']=stamp
 blob=gzip.compress(json.dumps(e,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)
 manifest.update(analysis_completed_at=stamp,original_shadow_frozen_at=x['frozen_at'],analyst_deep_review_count=28,evidence_sha256=hashlib.sha256(blob).hexdigest())
 catalog=load('backend/data/research_stocks.json')
 history_ids={s['history_id'] for s in manifest['stock_history_updates']}
 for stock in catalog['items']:
  for h in stock['history']:
   if h['id'] in history_ids:h['recorded_at']=stamp
 catalog['updated_at']=stamp
 manifest['rationale_history_recorded_at']=stamp
 writes={'backend/data/research.json':research,'backend/data/task_runs.json':runs,'docs/research/combined-pair-20261028-publication-manifest.json':manifest,'backend/data/research_stocks.json':catalog,'app/src/main/assets/research_stocks.json':catalog}
 encoded={p:json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n' for p,v in writes.items()}
 for p,v in encoded.items():(ROOT/p).write_text(v)
 (ROOT/EV).write_bytes(blob)
 print(json.dumps({'completed_at':stamp,'frozen_shadow_preserved':x['frozen_at'],'analyst_review_count':len(rows)},ensure_ascii=False))
if __name__=='__main__':main()
