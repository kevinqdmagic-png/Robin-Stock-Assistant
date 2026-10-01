"""Explicit research scenarios, NOT earnings forecasts or trading targets.

Run from the repository root. Amounts are CNY 100 million (亿元).
The input quote snapshot is immutable; no network or later prices are used.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/research/high-elasticity-2026-10-01-scenarios.json"
QUOTES = ROOT / "docs/research/high-elasticity-2026-10-01-evidence.json"

# Each tuple: core revenue, core normalized net margin, incremental new
# business revenue, new business normalized net margin, terminal P/E,
# normalized operating-cash-flow / net-profit ratio, annual cash capex.
# New-business revenue is excluded from core revenue to avoid double counting.
ASSUMPTIONS = {
    "300450": [(180, .08, 0, .08, 15, .70, 4),
               (240, .11, 15, .14, 25, .90, 6),
               (300, .12, 40, .18, 35, 1.00, 8)],
    "603662": [(22, .13, 1, .10, 20, .65, .8),
               (28, .15, 4, .18, 30, .85, 1.2),
               (34, .16, 10, .22, 45, 1.00, 1.8)],
    "688498": [(45, .25, 0, 0, 25, .65, 10),
               (90, .35, 0, 0, 40, .80, 15),
               (160, .40, 0, 0, 55, .90, 25)],
    "688559": [(70, .02, 0, 0, 15, .50, 3),
               (120, .06, 0, 0, 25, .80, 4),
               (170, .09, 0, 0, 35, 1.00, 6)],
    "001270": [(8, .22, 0, 0, 20, .60, .3),
               (15, .30, 0, 0, 30, .80, .6),
               (25, .35, 0, 0, 40, .95, 1)],
    "688668": [(30, .14, 0, 0, 20, .70, 1.5),
               (45, .18, 0, 0, 30, .85, 2.5),
               (70, .20, 0, 0, 40, 1.00, 4)],
}


def build():
    evidence = json.loads(QUOTES.read_text(encoding="utf-8"))
    result = {
        "as_of": "2026-10-01", "quote_date": "2026-09-30",
        "amount_unit": "CNY_100_million", "horizon_years": 4,
        "terminal_operating_year": 2030, "discount_rate": .12,
        "interpretation": "Conditional tests only; no probabilities, forecasts or buy/sell targets. Terminal P/E equity value, not enterprise value or a full DCF; no net-cash addition or interim dividends.",
        "items": [],
    }
    for quote in evidence["quotes"]:
        code = quote["code"]
        current = quote["a_price_times_total_shares_yi"]
        rows = []
        for label, a in zip(["cautious", "base", "optimistic"], ASSUMPTIONS[code]):
            core, cm, new, nm, pe, cash_ratio, capex = a
            profit = core * cm + new * nm
            terminal = profit * pe
            discounted = terminal / 1.12 ** 4
            rows.append({
                "case": label, "core_revenue": core,
                "core_normalized_net_margin": cm,
                "incremental_new_revenue": new,
                "incremental_new_net_margin": nm,
                "total_revenue": core + new,
                "normalized_net_profit": round(profit, 6),
                "terminal_pe": pe, "terminal_equity_value": round(terminal, 6),
                "discounted_terminal_equity_value": round(discounted, 6),
                "price_implied_normalized_profit": round(current * 1.12 ** 4 / pe, 6),
                "ocf_to_profit_assumption": cash_ratio,
                "annual_cash_capex_assumption": capex,
                "cash_after_capex_proxy": round(profit * cash_ratio - capex, 6),
                "discount_sensitivity": {str(r): round(terminal / (1 + r) ** 4, 6) for r in [.10, .12, .15]},
            })
        base = rows[1]
        result["items"].append({
            "code": code, "name": quote["name"],
            "current_a_price_implied_equity_value": current,
            "cases": rows,
            "base_implied_revenue_at_assumed_margin": round(base["price_implied_normalized_profit"] / (base["normalized_net_profit"] / base["total_revenue"]), 6),
            "base_discounted_value_per_existing_share": round(base["discounted_terminal_equity_value"] * 1e8 / quote["total_shares"], 6),
            "illustrative_20pct_new_shares_value_per_existing_share": round(base["discounted_terminal_equity_value"] * 1e8 / (quote["total_shares"] * 1.2), 6),
        })
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    model = build()
    for item in model["items"]:
        print(item["name"], "current", round(item["current_a_price_implied_equity_value"], 2),
              "discounted cases", [round(c["discounted_terminal_equity_value"], 2) for c in item["cases"]],
              "base required profit", round(item["cases"][1]["price_implied_normalized_profit"], 2))
