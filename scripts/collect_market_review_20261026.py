#!/usr/bin/env python3
"""Run the reproducible full-market collector for 2026-10-26."""

import collect_market_review_20261022 as collector


collector.MARKET_DATE = "2026-10-26"

if __name__ == "__main__":
    collector.main()
