# 11月6日学习复核补做｜分开比较上涨比例与收益

研究交易日T=2026-11-06；实际补做完成2026-11-07T06:42:29+08:00。观察计划D=2026-11-09，若D买入最早2026-11-10卖出。本轮为人工补做，保留所有原报告、原盘中冻结和失败样本，不倒填当时荐股。日线未复权；RVOL5/10/20分母不含T；五分钟只解释K线之间的顺序，不能证明60秒承接、排队成交或净收益。

本轮独立学习分析完成，不表示上游六项研究完成。使用forward-learning-2026-11-06真实快照；31条原记录，22条可观察、9条回顾性不合格，按证券+实际价格基准日去重17事件/8日期，重复同证券仍相关。

|周期|证券基准日N|独立基准日期|均值%|中位数%|正价格比例%|MAE<=-5%比例|
|---|---|---|---|---|---|---|
|T+1|17|8|-0.804|-1.362|47.060|41.180|
|T+2|17|8|-1.633|0.627|52.940|58.820|
|T+5|17|8|-7.055|-8.545|29.410|88.240|
|T+10|17|8|-10.286|-7.219|17.650|94.120|

涨得更经常和赚得更多分别研究。原低位结构4只/1日期，T+5正比例75%但均值-0.958%，平均正变动1.402%、唯一负变动-8.040%；一次大亏可吞掉多次小涨。T+10正比例25%、均值-1.623%。这只支持小样本内对照，不证明长期负或正期望。当前总样本T+5/T+10更差，不能把持有更久当解套方案。

两个时段分别读取原生产intraday-performance及dual_objective_research；按时段、版本、基准日、T+1/T+2/T+5/T+10分组，不把10月29日旧版本和11月6日新版本混为同组。以下是全部已返回分组，不挑有利时段：

|时段|组别/版本|周期|N/独立日期|均值%|正价格比例%|
|---|---|---|---|---|---|
|early|low_chase/intraday_low_chase_shadow_v2|T+1|2/1|-6.517|0.000|
|early|low_chase/intraday_low_chase_shadow_v2|T+2|1/1|-2.514|0.000|
|early|low_chase/intraday_low_chase_shadow_v2|T+5|1/1|0.279|100.000|
|early|low_chase/legacy_unversioned|T+1|19/10|-2.604|31.580|
|early|low_chase/legacy_unversioned|T+2|19/10|-2.430|31.580|
|early|low_chase/legacy_unversioned|T+5|14/8|-2.285|35.710|
|early|low_chase/legacy_unversioned|T+10|4/2|-18.715|25.000|
|early|momentum_control/intraday_momentum_quote_control_v1|T+1|3/2|-1.492|33.330|
|early|momentum_control/intraday_momentum_quote_control_v1|T+2|2/2|-3.654|0.000|
|late|low_chase/intraday_low_chase_shadow_v2|T+1|2/1|-1.641|0.000|
|late|low_chase/intraday_low_chase_shadow_v2|T+2|1/1|-3.324|0.000|
|late|low_chase/intraday_low_chase_shadow_v2|T+5|1/1|-0.554|0.000|
|late|low_chase/legacy_unversioned|T+1|19/10|-0.128|36.840|
|late|low_chase/legacy_unversioned|T+2|19/10|-1.943|42.110|
|late|low_chase/legacy_unversioned|T+5|14/8|-4.805|28.570|
|late|low_chase/legacy_unversioned|T+10|5/4|-8.125|40.000|
|late|momentum_control/intraday_momentum_quote_control_v1|T+1|2/1|-6.399|0.000|

11月6日周五冻结的T+1要11月9日收盘才成熟，不能周末提前算收益。早尾盘原各2只留存，不补造买单。

下一轮预注册假设：H1低位适度放量+收盘站回关键均线，与高量低CLV分别比较；H2突破后缩量回踩与直接追高分别比较；H3逐时板块同步能否减少假突破。冻结版本、保留亏损/未触发/不可成交样本，以平均/中位、平均盈亏、尾部MAE和样本日期数共同评估。36证券日/20独立日期下限未达到，不宣称统计优势。真实交易胜率、扣成本净收益和盘口可执行性留空。本轮没有自动训练或修改选股权重。