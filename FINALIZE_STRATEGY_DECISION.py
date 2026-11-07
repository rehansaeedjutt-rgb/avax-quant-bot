# FINALIZE_STRATEGY_DECISION.py
# Document: Main strategy only, secondary rejected
# Update website with final honest numbers

import os, json
from datetime import datetime, timezone

ROOT = 'C:/avax_quant_system'
CONFIG_DIR = os.path.join(ROOT, 'config')
WEB_OUT = 'C:/Users/rehan/QuantX-AI/netlify-deploy'

with open(os.path.join(CONFIG_DIR, 'FINAL_21_HONEST.json')) as f:
    portfolio = json.load(f)

portfolio['strategy_decision'] = {
    "decision": "MAIN STRATEGY ONLY",
    "secondary_rejected": True,
    "rejection_reason": "Secondary mean-reversion strategy underperforms (27.6% vs 71.9%) and over-trades (50.9 vs 22.6 trades/coin/year). 7 coins negative. Not worth complexity.",
    "zero_month_handling": {
        "count": 2,
        "months": ["2022-05", "2022-07"],
        "plan": "Capital protection alert + Monthly market report + 50% discount next month",
    },
    "compounded_results": {
        "main_avg_return_per_coin": 71.9,
        "main_total_trades": 3321,
        "main_trades_per_coin_per_year": 22.6,
        "main_negative_coins": 1,
    },
}

with open(os.path.join(CONFIG_DIR, 'FINAL_21_HONEST.json'), 'w') as f:
    json.dump(portfolio, f, indent=2)

# Website data
web_data = {
    "generated_utc": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
    "version": portfolio["version"],
    "total_coins": portfolio["total_coins"],
    "coins": portfolio["coins"],
    "sectors": portfolio["sectors"],
    "summary": portfolio["summary"],
    "strategy_params": portfolio["strategy_params"],
    "strategy_decision": portfolio["strategy_decision"],
    "subscription_model": portfolio["subscription_model"],
}
with open(os.path.join(WEB_OUT, 'data.json'), 'w') as f:
    json.dump(web_data, f, indent=2)

print("="*70)
print("STRATEGY DECISION — FINALIZED")
print("="*70)
print(f"\n✅ Main strategy: 21 coins, 71.9% avg return")
print(f"❌ Secondary: REJECTED (27.6%, over-trading)")
print(f"✅ Zero months: 2/72 (2.8%) — capital protection plan ready")
print(f"\n✅ Updated: config/FINAL_21_HONEST.json")
print(f"✅ Updated: {WEB_OUT}/data.json")
print(f"\n🚀 READY FOR DEPLOYMENT")
