# Robin Stock Assistant — three-stage reliability and shadow research milestone
Updated: 2026-10-27 (all displayed application clocks are Asia/Shanghai).

## Phase 1: observable execution & providers

`GET /api/operations/delivery` preserves six separate full-research
receipts and now shows `resident_intraday` independently for 09:50/14:40
using the Railway-mounted persistent store. A no-signal research observation
can count as a completed observation but never as a tradable recommendation.
The 20:40 GitHub full-report audit intentionally excludes those two resident
jobs to prevent false missing-delivery reports.

`GET /api/operations/providers` gives bounded, **process-local** observations
for quote batches, minute charts and daily history. A 502, timeout, incomplete
universe, unknown timestamps or stale quote cannot be labeled fully healthy.
These counters reset on restart and do not establish provider SLA or complete
market coverage; no data-source failure is silently repaired by inventing quotes.

## Phase 2: conservative strategy laboratory

`GET /api/strategy-lab` reads the latest archived forward-learning snapshot
and de-duplicates identical symbol / signal-date pairs across overlapping
research tracks. It exposes T+1/2/5/10 descriptive price outcomes, independent
dates, duplicate removals, and explicit null trading P&L.

`strategy_lab.simulate_daily_open_proxy` is a pure shadow-execution engine:
- requires a contemporary timestamped signal, *historically verified* issuer
  risk/IPO/corporate-action/price-limit metadata and same-session market bars;
- assumes buying at the *following session* open, and never sells on purchase
  day; waits at least one more completed trading session;
- returns no-entry at opening limit up, holds back unverified limit-down exits
  and refuses missing/suspended sessions rather than skipping over them;
- uses an explicit initial capital, 100-share lots, slippage, commission
  minimum, sell tax and holding window;
- calculates **paper** results only. Daily OHLC cannot prove real fills,
  order queue position or executions. It is NOT hooked into buying or selling.

Historical issuer status is not fully provisioned by the current feed, so
most real-world signals must be blocked until an independently verified,
versioned security-master source becomes available.

## Phase 3: controlled learning and promotion

The lab reports a *research evaluation eligibility* check: at least 36
distinct eligible signal-date-symbol T+2 observations over 20 independent
signal dates. This is only a lower bound for further evaluation, not evidence
of a profitable strategy. A real model promotion also needs:
- chronological walk-forward / out-of-time holdout and comparison with a
  frozen baseline;
- actually fill-aware net fees/slippage and tail-risk / max-drawdown metrics;
- non-reused, date- and stock-cluster-aware validation with adverse cohorts;
- human approval and a reversible active strategy version.

Model rules are **never automatically rewritten** in this milestone.
No real-money orders, paid streaming market feed or Android FCM notifications
were connected. Push delivery needs opt-in, device credentials and a secured
push provider; 30-minute background Android polling remains best effort.

## Verification and next work

Required to ship: Python unit tests, archive-frozen checks, container smoke,
Android build if touched, Railway terminal SUCCESS, public API readback.
Open engineering tasks remain at #17—#20 for persistent provider metrics,
full external orchestration recovery, broker-evidenced fill simulation and
push notifications. A successful software deployment is not strategy alpha.
