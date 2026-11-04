# Fuyao A-share snapshot: candidate fallback provider (2026-11-04)

Status: **candidate / manual smoke test passed / NOT enabled in production**.

The user tested the third-party service at https://fuyao.aicubes.cn and obtained HTTP 200, JSON `code: 0`, `data.total: 2`, with individual stock prices via `GET /api/a-share/prices/snapshot` using explicit `thscodes`. This verifies only the tested endpoint and entitlement, not unrestricted full-market access, bulk quotas, historical completeness, or official Tonghuashun affiliation. Do not describe this service as an officially licensed Tonghuashun API without independent verification.

## Intended source priority

1. BaoStock remains the primary validated SH/SZ **historical daily OHLCV** provider.
2. Fuyao is a potential *secondary* A-share quote/snapshot provider, subject to additional authorization, quota and data-quality testing. It is NOT a drop-in replacement for historical daily bars.
3. If primary fails, mark the relevant module blocked unless the backup has independently satisfied the same date, exchange coverage, schema, and quality gates. Never silently mix timestamps or providers.

## Verified test request shape

- Endpoint: `GET https://fuyao.aicubes.cn/api/a-share/prices/snapshot`
- Example: `thscodes=600519.SH,000001.SZ`
- Observed response: HTTP 200, `code=0`, `data.total=2`, `data.item` includes `thscode`, `last_price`, `open_price`, `high_price`, `low_price`, `volume`, `turnover`.
- Auth: API key, supplied securely at runtime; NEVER store it in GitHub, source, logs, screenshots, or research reports.
- API key previously shown in a screenshot is compromised; only a newly rotated key may be used.

## Activation gates (not yet satisfied)

- Independently verify service ownership, authorization and terms permitting automated retrieval.
- Check whether empty `thscodes` supports complete SH/SZ pagination; if not, supply an independently verified code universe and test explicit-code batches.
- Verify batch sizes, rate limits, free tier quotas, response timestamps/timezone, holiday and suspended symbols, price/volume units, coverage and duplicate/missing codes.
- Cross-check a dated sample with BaoStock or an exchange source. Snapshot `last_price` is not automatically the official daily close.
- Run shadow collection first; never let an unvalidated fallback generate formal buy signals.
- Only after gates pass: store a **new** API key as a protected Railway/GitHub secret (not in this repository), implement an opt-in adapter, and verify production readback and provenance. Keep BaoStock enabled.

No key or cookie is present in this document. This entry is an integration plan, not a claim that the fallback is live.
