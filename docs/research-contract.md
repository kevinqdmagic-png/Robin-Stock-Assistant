# Robin stock assistant: research contract and holiday progress

## 0.6.0：自选股研究理由与历史

用户要求把此前高弹性及AI产业链研究股加入自选，并点开查看理由。`backend/data/research_stocks.json`是研究观察档案，和可执行每日双标的`recommendations.json`分开。

- 每只股票用准确的六位`code`关联，包含`name`、`sector`、`role`（core/comparison/research）、`default_watch`和非空`history`。
- 每条历史包含唯一`id`、实际研究`date`、本次整理`recorded_at`、`title`、`reason`、`evidence_status`、`fact_note`、`validation[]`、`risk`、`report_ids[]`和`sources[]`。完整报告必须先归档，关联报告正文须包含该股票名称。
- 昨天三只核心（先导智能300450、柯力传感603662、源杰科技688498）保留原研究；鼎通科技688668为补充比较。此前AI连接、光器件、封装、电源七只研究股的原对话摘要另行恢复，注明回溯整理，不能把摘要恢复伪称原始完整报告，也不能补填当时报价或绩效。
- 已发布股票和历史理由不删除、不改写。新的核验、反证、下调关注或结论更正使用新的历史id追加，原理由继续可读。当前角色可更新，更新依据必须在新历史说明。
- 研究任务对已入库股票形成新结论时，追加有报告、日期、条件和来源的历史条目；新研究股可入清单，但默认`default_watch=false`，除非用户要求加入。仅由用户询问、风险对照或没有实际研究支持的名字不得冒称推荐。
- 每次更新档案，同步`app/src/main/assets/research_stocks.json`为同一JSON，供离线备份；CI核验一致性与关联报告，不需要为纯研究数据更新要求用户反复安装APK。
- `/api/research-stocks`提供清单，`/api/stocks/{code}/research`提供个股理由，`/api/research?code=...`按关联报告id查询全文。理由不依赖行情接口；缺失行情不能阻止档案展示。
- APK首轮合并这次用户要求的十只观察股，不覆盖本机原有自选。已提供过的代码单独记在`research_seeded_codes`，用户移除后不会因刷新、重启或新批次重加；可以从过去研究清单主动恢复。
- 自选→股票详情显示原关注理由、研究日期、最近核验、继续验证和下调关注条件，并可展开历史/来源或进入关联全文；在线档案同步，本机缓存和内置备份保留。研究观察池的标签不能被展示为当日两只短线交易指令。

Version: 0.5.0, 2026-10-01. User requested daily APK improvement, independent broader stock research, and the existing volume-price study. Code is on holiday-polish-2026-10; do not say it is deployed until deployment and live checks succeed.

## What this iteration implements

- Four existing bottom tabs remain; home no longer embeds individual minute charts.
- Light neutral surfaces, red for rises and green for falls.
- Market overview: four indices, covered turnover and breadth; partial coverage never labeled whole-market.
- Industry/concept leaders and laggards, leading stock, provider quote timestamps where supplied.
- Exchange-calendar status and no candidate polling outside a known trading session.
- Date/category/paginated research archive, full report text and sources; cached reports remain readable offline after a successful fetch.
- Paginated recommendation history, separately labeled combined/early/tail cohorts, original trigger and invalidation conditions, and on-demand 1/3/5/10/20/30-session price observation.
- A frozen daily breakout proxy with 20-session warm-up, trailing 30-session signal window, next-session-open entry, earliest following-session-open exit, assumed roundtrip costs and opening price-limit constraints.
- Exact historical research that is available is retained. Missing original recommendation prices are not manufactured.

## Archives and publishing

All files live in backend/data and are included in the deployment image. Existing production /data/research.json takes precedence for compatibility; ROBIN_RESEARCH_FILE and ROBIN_RECOMMENDATIONS_FILE override defaults. Inspect production overrides before declaring bundled records visible. Publish complete valid JSON through the existing repository workflow; there is no unauthenticated write API.

research.json has schema_version and items[]. Each record requires a stable id, date (China-market research date), track, title, summary, body and sources. Allowed tracks: market_review, volume_price, dragon_tiger, low_position, quant_research, high_elasticity, app_development. New reports add task_id from tasks.json; legacy reports retain their original content. A source-corrected report gets a new id; never edit/delete the old report.

recommendations.json has items[] and optional legacy_audit. Required original fields:
id, date, published_at (ISO timestamp with timezone), code, name, group (close / 0950 / 1440), model, reason, reference_price, trigger, invalid, sources, provenance. New combined selections also store strategy=combined_limitup_watch, which is immutable. reference_price is a timestamped observed quote, not an assumed fill; conditional entry ranges belong in trigger and actual fills in results[].
Use provenance=contemporaneous only for a recommendation recorded before its future outcome was known. Retrospective examples remain retrospective. Append actual outcomes in results[]; preserve original fields and previous outcomes. Include result as_of, source, horizon, price basis, whether the trigger actually happened, and whether the result is price observation or an executable trade.

Check schemas and frozen history using scripts/validate_archives.py BASE_COMMIT and the research CI. Scheduled ChatGPT output is NOT automatically a backend report: write the JSON and validate CI. Branch data becomes available to the running app only after a successful reviewed deployment that uses those files. While PR #4 is open, scheduled writers use holiday-polish-2026-10; switch to the default branch after merge. Multiple scheduled writers must read the latest branch head and retry conflicts by rebasing, never force-push.

volume_price_samples.json preserves found report excerpts with eligible_for_model_statistics=false until original prices/time/source are recovered. Do not mix the 2026-09-30 holiday-overnight cohort with ordinary overnight observations.

## Exact limits of the first validation tool

This is a single-stock, completed-daily-candle proxy, not a 30-day full-A backtest or historical reproduction of the minute signal model. It detects a close above the prior 20-session high, RVOL20 >=1.5 and CLV >=0.7. These thresholds are frozen research assumptions, not empirically optimized trading rules.

Default total cost is an illustrative 20 basis points, adjustable in the APK. It does not model minimum commission, lot size or precise slippage. Uses forward-adjusted research candles, not raw fills. Conservatively refuses opening limit-up buys and defers opening limit-down exits. Historical ST/IPO/no-limit status is not available; these require further security-master data. Signals are independently observed and may overlap; statistics are not portfolio equity or portfolio drawdown. MFE/MAE exclude the exit day's moves after its opening exit. Daily OHLC cannot reveal intraday high/low sequence.

Recommendation comparison uses unadjusted candles against the stored raw reference, refuses obvious corporate-action inconsistencies, and is labeled price observation. Missing minute bars mean intraday triggers, 9:50/14:40 executions and stop/take-profit ordering are unverified. Pending, failed and unavailable samples stay in the archive.

## Wider independent research

Always start with available full-market scanning. Target 80–150 names spanning at least five sectors, deep-review 20–30 and select up to two; report actual coverage instead of claiming a full scan. User asks/watchlist/holdings must not become an input shortlist by default. Repeated choices need fresh independent comparison and reasons; track 5/10-session repetition. Do not force turnover to look diverse.

Preserve the earlier high-elasticity thesis and its core candidates: 先导智能300450, 柯力传感603662, 源杰科技688498, with 海目星/铖昌科技 as earlier alternatives. Robin's latest instruction is deeper reasoning, not rejection of that research. The new 鼎通科技 comparison is supplementary and does not replace the original shortlist. The one-time continuation must test order-to-revenue/profit/cash conversion, competitive position, valuation scenarios and falsifiers. These remain research candidates, not immediate entries; current prices and valuation must be verified. The old PDF is preserved and fact-check notes appear in a separate report: 柯力's >2000 units include robot force/torque product categories, not exclusively six-axis sensors; 先导's old solid-state repeated-order statement was not independently found in the checked half-year PDF, so do not treat it as confirmed.

## Daily work configured

- APK improvement: Mondays at 09:00 Pacific/Auckland in the current confirmed schedule snapshot.
- High-elasticity deep continuation: ONE TIME on 2026-10-01 around 20:00 Pacific/Auckland; preserve and deepen the prior research.
- Volume-price research/verification: existing 21:00 Pacific/Auckland task now DAILY, including holidays.
- Separate combined after-close selections: daily around 22:30 Pacific/Auckland, after verifying that market review, quant, volume-price, low-position and Dragon Tiger reports for the relevant trading day are actually complete. A scheduled clock time alone is not completion. This condition task rechecks at 23:30, 00:30 and 06:30 Pacific/Auckland when needed; it reports once per trading-day decision and skips completed decisions. Missing or stale reports must be disclosed and must not be represented as an integrated final selection.
- Existing 9:50 and 14:40 selections remain separately labeled experimental cohorts. Close-review candidates supply evidence to the later combined decision.

The combined cohort defines T as the reviewed trading day and T+1 as the intended entry day. Research the possibility of a limit-up move on T+1 or T+2 and premium exit conditions. T+1 purchases cannot be sold until T+2; a T+1 limit-up is unrealized profit, and a limit-up quote does not establish an executable purchase or exit. Publish up to two conditional candidates; weak markets or insufficient evidence can justify fewer or none. Do not invent limit-up probabilities. Recheck auction/opening conditions before treating a trigger as valid.

For each integrated report, show all five research completion dates, supporting and opposing evidence, selection versus alternatives, trigger/range, abandonment and invalidation conditions, and the first legally executable exit plan. On closed-market days maintain the reopening plan and evidence; do not manufacture fresh daily trade recommendations.

Tasks run at their scheduled times; this is not continuous background autonomous training. Each run should produce evidence, append samples, explain failed hypotheses, freeze versions and use forward/out-of-sample checks. Actual tool access must be verified each run.

## Still required

1. Merge/deploy the reviewed branch and check /health, /api/overview, /api/research, /api/recommendations and /api/stocks/CODE/backtest in production.
2. Retrieve and archive original daily recommendations, including timestamps/prices; never reconstruct favorable entries after observing prices.
3. Test APK layout and navigation on a phone/emulator; compilation does not establish visual usability.
4. Validate quotes during real trading hours and timestamp semantics; provider availability differs by network.
5. Acquire historical minute bars, point-in-time sector/security status, adjustment factors and benchmark data for full three-model and market-wide validation.
6. Validate persistence on deployment/restart and effective production data overrides.
7. No stable model win rate is established by the recovered five-example retrospective report.

Official 2026 calendar source: https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml
Provider board field mapping checked against:
https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_board_industry_em.py
https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_board_concept_em.py

## Task center and execution receipts

Tasks are registered in tasks.json with safe local ids, confirmed schedule snapshots, timezone, timing mode and dependencies. Private scheduler identifiers and prompts are not published. Update this snapshot after changing a schedule; the app labels the configuration update time. This is not a live connection to the scheduler's private administration API.

APP reads /api/tasks, /api/task-runs?task=TASK_ID and /api/research?task=TASK_ID. Latest status comes only from published execution receipts; a scheduled time never creates a successful run. Historical reports without a task_id remain linked as historical material and do not establish that a new scheduled run completed. Cached data is labeled offline.

Each actual task iteration appends events to task_runs.json.items. Required fields:
id (unique event id), run_id (stable id shared by events for this iteration), task_id, date (China trading/research date), trigger (scheduled or manual), started_at and recorded_at (ISO timestamps with timezone), status, summary and report_ids[].
Statuses: running, waiting, completed, blocked, failed. Terminal events require completed_at. completed requires a real report whose task_id matches. Add recommendation_ids[] for stock selections and sources[] for execution evidence. Never overwrite prior events; append a new event for a state transition or delivery correction. Do not reconstruct nonexistent historical executions. Explicitly label manual work.

Publish reports, original conditional recommendations and their receipts together in one commit based on the latest head. Validate schemas, report links and append-only history. After merge, publish the tested main commit to the existing Railway service using an explicit commit SHA/Deploy Latest Commit. Native GitHub auto-deploy is unavailable until the Railway GitHub App is installed; ordinary redeploy reuses the old commit. The production verification workflow checks actual endpoints and records the result. Only after successful deployment and verification claim that APP can read the update. Network/CI/deployment failures remain visible; append a blocked/failed receipt if possible.

Combined decisions require same-day completed receipts and their full linked reports from market_review, quant_research, volume_price, low_position and dragon_tiger. Empty scans and no qualified selections still get a report explaining the decision. A waiting receipt does not satisfy a dependency. Check unique trading-day decision ids before reporting again.

Local ids and tracks:
- apk_polish -> app_development (上午打磨股票 APK)
- high_elasticity_once -> high_elasticity (高弹性一次性深度研究)
- market_review -> market_review (A股每日复盘)
- quant_research -> quant_research (A股量化痕迹复盘)
- volume_price -> volume_price (量价研究与每日验证)
- low_position -> low_position (低位启动30天研究)
- dragon_tiger -> dragon_tiger (龙虎榜超短研究)
- combined_pair -> market_review (盘后综合双标)
- early_pair -> market_review (早盘短线双标)
- late_pair -> market_review (尾盘短线双标)

Container build now includes all backend modules and data. CI starts the actual container and reads health/tasks/research/receipts/recommendations, so missing packaged modules cannot be hidden by source-only tests.

APK 0.5.0 adds the expandable task center and task-filtered reports. A tested debug build is provided; handset layout, certificate compatibility with the currently installed APK, and actual installation remain device checks.

## Verified publication, 2026-10-01

PR #4 was merged. 33 tests, container read checks and APK build passed. Commit 4365fc4acba792953c126057b18ffefc7495d4ed was deployed to the existing production service and its public read APIs were verified as version 0.5.0 with all ten tasks. The first execution receipt is explicitly manual; other tasks are not shown as completed without their own receipts. The test APK is available in GitHub release v0.5.0.

Publishing order: validate the research job (including archives and container), then explicitly deploy the tested main SHA, then validate the production job. Do not wait for the production job to pass before starting deployment. Check latest main and deployed SHA to avoid rolling back a concurrent newer publication. Native auto-deploy was inspected and is disabled because the repository lacks a Railway GitHub App installation; connected deployment operations are the current authorized publishing path. No new service, variable or domain was introduced.

## 已核实的APK签名阻碍（2026-10-01）

已发布0.5.0与0.6.0的APK签名证书不同，不能直接覆盖安装0.5.0。自选迁移策略只在可兼容安装且原SharedPreferences仍保留时生效；不能将代码测试称为手机数据已保留。签名证书哈希及验证证据见apk-signing-audit-2026-10-01。上午APK任务应优先建立安全固定签名、查找合法可用原签名私钥及数据迁移方案；没有原私钥不能承诺当前同包名的无损覆盖升级。不要引导先卸载旧版，不把私钥提交公开GitHub仓库、公开Actions缓存或报告。功能、服务发布与手机安装状态分别据实说明。

## 0.6.1：开市恢复与固定签名发布闸门

- 客户端把交易时段切换抽成可测试策略。盘前转9:30、午休转13:00时，同一30秒轮询周期立即请求概览、覆盖行情和动态候选；午休、收盘、周末及已核验节假日不轮询候选。
- 后端交易时段对象带北京时间日期，客户端不再仅用手机本地推断服务端会话日期。覆盖行情增加明确的覆盖口径情绪与上涨占比，不把部分行情冒充全市场。
- 推荐历史可从第一页重新刷新并继续按12条分页，页面显示已加载/总数；原始推荐和结果仍只读、追加。
- GitHub工作流始终保留调试构建供CI验证，但不再自动把临时debug证书包发布为版本下载。只有四项加密签名输入齐全且构建证书SHA-256等于固定仓库变量时，才构建并发布release APK。
- 所需Secrets为`ROBIN_UPLOAD_KEYSTORE_B64`、`ROBIN_UPLOAD_STORE_PASSWORD`、`ROBIN_UPLOAD_KEY_ALIAS`、`ROBIN_UPLOAD_KEY_PASSWORD`；固定证书变量为`ROBIN_SIGNING_CERT_SHA256`。私钥不得进入源码、日志、缓存或研究档案。
- 该闸门只阻止继续制造随机签名版本，不会找回0.5.0私钥。没有原私钥仍不能覆盖已安装0.5.0；不要先卸载。调试APK、固定签名release APK、手机已安装验证继续分别陈述。


## 2026-10-05：其他板块高弹性双股研究

Robin要求把新的其他板块高弹性选股任务及成果写进APP。新增独立一次性任务`high_elasticity_other_once`，track为`high_elasticity`；不替换原`high_elasticity_once`及原研究。

- 范围：A股其余板块，严格排除以电池、AI、医药医疗、航空航天和机器人为核心增长逻辑的公司。最终研究两只长期观察标的，核查成长依据、当前市值、市场空间、订单商业化、利润现金流、竞争壁垒、估值、稀释和反证。
- 50倍/100倍作为未来几年极端情景的规模检验；区分事实与假设，不将目标涨幅写成确定预测。记录基准、乐观、极端假设及后续验证节点。
- 奥克兰时区的一次性启动为2026-10-06 07:30，用户要求09:00前提交。私有定时任务已创建；APP仅保存安全配置快照及真实执行状态。
- 注册回执为manual/waiting，表示任务已登记且研究尚未开始。未来研究使用独立scheduled运行id；只有完整研究完成并有对应报告才能追加completed。
- `include_legacy_reports=false`：本任务仅关联其准确task_id的报告，原高弹性历史报告不展示为本次成果。原十项任务和旧档案保留。
- 完成后先归档完整报告和回执，再在研究股票档案中追加两只的理由、验证、风险与来源；同步离线档案。纯研究与任务数据更新不要求重新安装APK。研究观察股不混入每日双标交易指令。

## 0.7.4：自选行情时间透明与刷新单飞

- 本地秒开缓存必须显示真实年龄；网络失败、服务器旧缓存和部分股票缺失不能用新的请求时间伪装为实时行情。
- 回到前台且距上次请求超过5秒时恢复一次自选刷新；冷缓存自动跟进一次。离开自选页或页面代次改变后取消迟到回调。
- 服务端对同一股票的后台行情刷新采用single-flight，重复请求不启动相同在途抓取，结束时无论成功或失败都释放保护。
- 正式0.7.4继续使用从0.7.0建立的固定证书；固定签名版本之间可覆盖升级。0.5.0/0.6.0测试签名历史不兼容结论保留。
- 首页第四指数保持科创50，四个底部栏目、自选理由、研究历史与离线档案不回退。本次未做真机安装或界面验收，不将构建成功称为手机已经更新。


## 2026-10-08：独立每日打板一股前推实验

新增安全本地task_id limitup_single，track=market_review，候选group=close、strategy/model=limitup_single_v1，include_legacy_reports=false。保存已确认的工作日08:00 Pacific/Auckland配置快照；不发布私有自动化ID或完整提示词。不改变、替换、恢复或暂停其他任务，与原综合双标及早/尾盘组分别追踪。

- 先模拟前推约20—30个实际交易日作为首轮复核节点，不代表获利证明或自动转实盘。最多一只条件候选，无合格对象明确空仓且保存完整理由。弱市/数据不足不能硬凑。
- 核验上海时区D与最新已完成T、公开资料截止与报价交易日；休市不发新候选，长假后样本单列；盘前不能将T盘口当D实时确认。普通主板10%与其他制度分开。
- 冻结v1和每条原始候选；前推阶段先追踪旧候选及未完样本，结果只追加results。保留亏损、未触发、数据缺失、停牌及买卖未成交。规则变动须记原因、日期和新版本并仅向后验证。
- v1研究普通主板整理平台换手首板及其二板/首次分歧回封；排除ST/退市风险、上市初期无上限、低流动性、一字排队、高位连续缩量加速和明显高位爆量滞涨。固定竞价0—5%、09:35—10:30介入窗口、累计换手2—12%、第一次开板后60秒守住 verified_upper×98%及成交均价、两只事前冻结主题同伴均涨至少3%且高标未跌停。全部为未验证假设。个股具体价位及同伴在原推荐rules冻结。
- 真实当日涨停价/除权/证券状态必须由权威当日报价核验；规则计算值单独标明，不假装实时上限。无法核实条件不认定触发；缺排队成交证据不认定买入。没有分钟/逐笔不能从日线补回封时序。未接入Level-2，不承诺持续盯盘/秒级预警。
- 冻结退出：D买入最早D+1实际交易日09:30起首个能证明可成交的报价/成交退出。强/平/弱开统一口径，不能事后挑最高价。跌停无买盘、停牌或卖单未成交保留敞口并追加最早可成交记录；止损阈值不保证成交。T盘后选、T+1买则最早T+2卖。
- 统计按首板、二板、回封子标签、市场/板块阶段及长假区间分别列候选、完成样本与可执行数；回封子标签可能重叠不能求和。封板/炸板分母是有触发与收盘证据的样本；价格观察、按固定退出的理论收益与可执行净收益分开。先保留净收益均值/中位数、盈亏比、尾部和不利波动缺项，不填虚构概率或0%胜率。暂拟20bp成本占位未校准，不用于可执行净收益；费用/数量/最低佣金/滑点及两侧成交证据齐全后才计算。
- 报告须真实披露覆盖股票/标签数及缺项，并与至少三只真实备选比较；原持仓、自选和他组股票不自动入选。龙虎榜按实际披露可得时间；席位标签不是账户身份，雪球仅参考情绪，重大事实查公告/监管原文。
- 完整研究、原始条件候选、真实检查点与研究执行回执同一原子提交；研究completed不冒充成交或生产已同步。按既有归档/历史/容器闸门测试，核对最新head后向现有Railway生产服务发布准确tested commit SHA，读取health/tasks/task-runs/本task报告和候选才称同步。纯研究更新不要求重装APK。

首轮完整规则、固定卡片、147只报价审计与历史缺项见 docs/research/limitup-single-2026-10-08.md 及同日evidence.json；该记录不回填假想历史样本。


## 2026-10-08补充：limitup_single_v2市场情绪与连板结构

Robin追加市场情绪、高度板、空间板和进阶板因素。仅更新现有limitup_single任务的研究内容及APP安全快照，执行时间/启用状态和其他任务保持原值。

- 规则升级limitup_single_v2，从下一轮新候选起生效。2026-10-08龙溪股份600592的limitup_single_v1原始条件、报告、价格、来源与已保存结果全部冻结；按v1继续追踪，新增事实只追加。新候选strategy/model/research_version标v2，task_id/track/group仍为limitup_single/market_review/close。版本分组统计，不重新解释旧样本。
- 固定顺序：先最近三个完成交易日情绪与市场/主线梯队，再空间与分层晋级反馈，后个股角色/至少三只真实备选比较，最后盘口与成交证据。
- 市场情绪列涨停/炸板/跌停、量能、前日连板和断板股次日反馈、主线持续性，给启动/修复/分歧/加速/退潮或无法分类及正反证据；不能用一个指标或指数涨跌替代。
- 高度板列普通主板最高/次高及1/2/3/4/5+梯队，并单列候选主线高度、交易日、六位代码、一字/换手/缩量加速/断板负反馈；覆盖不足标可见范围最高。
- 空间板采用本实验工作定义：打开或尝试突破本轮连板上限的标的。固定辅助参照为T之前20个实际交易日最高连板高度；情绪周期起点/高点有证据才冻结，缺历史标未知。高度与空间角色可重合，去重；N天M板不等于连续M板。
- 进阶板按晋级板理解，分别查1进2、2进3、3进4及更高层。分母从T-1该层逐股名单冻结，保留晋级/断板/停牌/缺失；可得晋级率=晋级/(晋级+已核实断板)，另列原总分母与缺失率。有缺失不称全层晋级率；媒体总体晋级率不套到特定层。10%主板、ST、20%/30%和无上限情形分别处理。
- 候选写当前/计划板数、主线高度及领涨/换手核心/补涨/跟随/待确认角色，以实际证据解释隔夜退出影响。先检查退潮/高标跌停与晋级断层共振、空间突破失败、主线断层无承接、一字/高位加速及关键数据缺失；各新候选的参考股、观察窗口、附加放弃条件必须事前冻结。关键风险无法查清则空仓，不硬选。
- 上述因子均为前推研究假设，不增设未经验证的综合分数或获利保证；情绪阶段、市场/主线高度、空间状态、晋级层级、长假和版本分别列样本与绩效缺项。首轮20—30交易日只作复核节点，不自动转实盘。

完整v2约定与本次manual报告见 docs/research/limitup-single-v2-market-context.md。此规则补充不冒充新增交易候选或已执行交易，不改现有schema、老报告或旧样本。
