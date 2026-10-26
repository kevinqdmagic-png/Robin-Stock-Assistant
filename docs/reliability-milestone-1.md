# Reliability milestone 1 — delivery observability (2026-10-27)

This iteration adds a **read-only** operations endpoint, `GET /api/operations/delivery`.
It reports the latest completed A-share session in Beijing time, with independent
publication statuses for market review, volume-price, low-position, Dragon-Tiger,
combined pair and limit-up research. The 09:50 / 14:40 resident Railway\nobservation runs have a separate primary evidence store and must not be judged\nusing the GitHub research-report receipts alone.

## Contract

- `completed`: a genuine completed receipt links to a same-date same-track published report.
  Full research also needs `analysis_completed=true`; a scheduler trigger, fallback
  observation, partial document, blocked receipt or HTTP 200 response does **not** qualify.
- `missing`: no dated receipt after the Beijing 20:40 audit deadline.
- `failed`, `blocked`, `partial`, `waiting`, `running`: published but not proven complete.
- `unverified`: an apparent completion is missing sufficient evidence.
- `pending`: the day has not reached the audit deadline. Do not claim a failure yet.
- `calendar_unverified`: cannot safely determine a completed session; stop.
- `trading_strategy_validated=false` always. Delivery is not profitability or trade execution.

The scheduled deadline audit now checks Dragon-Tiger independently; previous
absence of the module could result in missed Dragon-Tiger research going unflagged.
The audit does not create trading recommendations or pretend missed research ran.

## Release checks

Run `python -m unittest discover -s backend/tests -v`, the archive validator,
and the complete research CI. After the main-branch deployment settles, confirm
`/health`, `/api/operations/delivery`, and prior archive API checks.
A Railway `SUCCESS` alone does not prove all research jobs executed.

## Limitations and next milestones

This does **not** consolidate the separate intraday resident evidence store,\nimplement automatic retries for the external full-research
orchestrator, change trade selection, fix upstream 502s, enable FCM notifications,
or transform observational price changes into executable trading P&L.

Next P0 milestone: independent retry and escalation on missing same-day research,
with provider-quality metrics and full completion receipts. Next P1 milestone:
independent, fill-aware T+1 simulation and strategy laboratory.
