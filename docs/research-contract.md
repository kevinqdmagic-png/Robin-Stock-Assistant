# Robin stock assistant: research contract and holiday progress

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

- APK improvement: mornings around 09:00 Pacific/Auckland, daily flexible window.
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

All ten current tasks are registered in tasks.json with safe local ids, confirmed schedule snapshots, timezone, timing mode and dependencies. Private scheduler identifiers and prompts are not published. Update this snapshot after changing a schedule; the app labels the configuration update time. This is not a live connection to the scheduler's private administration API.

APP reads /api/tasks, /api/task-runs?task=TASK_ID and /api/research?task=TASK_ID. Latest status comes only from published execution receipts; a scheduled time never creates a successful run. Historical reports without a task_id remain linked as historical material and do not establish that a new scheduled run completed. Cached data is labeled offline.

Each actual task iteration appends events to task_runs.json.items. Required fields:
id (unique event id), run_id (stable id shared by events for this iteration), task_id, date (China trading/research date), trigger (scheduled or manual), started_at and recorded_at (ISO timestamps with timezone), status, summary and report_ids[].
Statuses: running, waiting, completed, blocked, failed. Terminal events require completed_at. completed requires a real report whose task_id matches. Add recommendation_ids[] for stock selections and sources[] for execution evidence. Never overwrite prior events; append a new event for a state transition or delivery correction. Do not reconstruct nonexistent historical executions. Explicitly label manual work.

Publish reports, original conditional recommendations and their receipts together in one commit based on the latest head. Validate schemas, report links and append-only history. After merge, the connected Railway service deploys from main; the production verification workflow checks the actual endpoints and records their result. Only after successful deployment and verification claim that APP can read the update. Network/CI/deployment failures remain visible; append a blocked/failed receipt if possible.

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
