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
