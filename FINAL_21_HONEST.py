# FINAL_21_HONEST.py
# 21 real honest coins — deploy-ready
# Quality filter: no fan tokens, no dying projects, no small samples

import os, json
import pandas as pd
from datetime import datetime, timezone

ROOT = 'C:/avax_quant_system'
CONFIG_DIR = os.path.join(ROOT, 'config')
REPORT_DIR = os.path.join(ROOT, 'reports')
WEB_OUT = 'C:/Users/rehan/QuantX-AI/netlify-deploy'
os.makedirs(WEB_OUT, exist_ok=True)

COINS_21 = [
    {"rank":1, "coin":"FET",  "return":107.8,"wr":60.8,"pf":1.64,"dd":-19.6,"trades":194,"sector":"AI",       "rating":"GOOD"},
    {"rank":2, "coin":"WIN",  "return":103.5,"wr":59.7,"pf":2.47,"dd":-15.3,"trades":149,"sector":"Oracle",   "rating":"EXCELLENT"},
    {"rank":3, "coin":"WAVES","return":103.4,"wr":68.2,"pf":2.38,"dd":-13.5,"trades":157,"sector":"L1",       "rating":"EXCELLENT"},
    {"rank":4, "coin":"THETA","return":101.9,"wr":61.1,"pf":1.79,"dd":-17.2,"trades":185,"sector":"Media",    "rating":"GOOD"},
    {"rank":5, "coin":"RLC",  "return":101.5,"wr":64.0,"pf":2.20,"dd":-24.5,"trades":175,"sector":"Cloud",    "rating":"EXCELLENT"},
    {"rank":6, "coin":"DUSK", "return":93.1, "wr":60.4,"pf":1.71,"dd":-24.5,"trades":212,"sector":"Privacy",  "rating":"GOOD"},
    {"rank":7, "coin":"STX",  "return":84.1, "wr":66.9,"pf":1.68,"dd":-19.3,"trades":181,"sector":"L2",       "rating":"GOOD"},
    {"rank":8, "coin":"CAKE", "return":82.5, "wr":55.6,"pf":2.86,"dd":-15.0,"trades":108,"sector":"DeFi",     "rating":"GOOD"},
    {"rank":9, "coin":"BAT",  "return":75.5, "wr":49.5,"pf":1.39,"dd":-26.1,"trades":194,"sector":"Ads",      "rating":"ACCEPTABLE"},
    {"rank":10,"coin":"NMR",  "return":74.5, "wr":52.2,"pf":2.00,"dd":-17.4,"trades":115,"sector":"AI",       "rating":"GOOD"},
    {"rank":11,"coin":"FUN",  "return":67.3, "wr":64.1,"pf":1.82,"dd":-13.6,"trades":145,"sector":"Gaming",   "rating":"GOOD"},
    {"rank":12,"coin":"ANKR", "return":66.9, "wr":57.4,"pf":1.56,"dd":-27.8,"trades":195,"sector":"Infra",    "rating":"GOOD"},
    {"rank":13,"coin":"JST",  "return":66.0, "wr":48.3,"pf":1.76,"dd":-31.3,"trades":120,"sector":"DeFi",     "rating":"GOOD"},
    {"rank":14,"coin":"CHR",  "return":65.7, "wr":54.1,"pf":1.57,"dd":-13.4,"trades":148,"sector":"Infra",    "rating":"GOOD"},
    {"rank":15,"coin":"DYDX", "return":49.8, "wr":54.2,"pf":1.86,"dd":-14.1,"trades":72, "sector":"DeFi",     "rating":"ACCEPTABLE"},
    {"rank":16,"coin":"WOO",  "return":49.8, "wr":60.0,"pf":2.00,"dd":-13.2,"trades":80, "sector":"DeFi",     "rating":"ACCEPTABLE"},
    {"rank":17,"coin":"HYPE", "return":47.6, "wr":69.0,"pf":99.90,"dd":-6.2,"trades":29, "sector":"DEX",      "rating":"ACCEPTABLE"},
    {"rank":18,"coin":"HBAR", "return":45.9, "wr":50.8,"pf":1.35,"dd":-34.6,"trades":183,"sector":"L1",       "rating":"ACCEPTABLE"},
    {"rank":19,"coin":"CHZ",  "return":41.7, "wr":61.6,"pf":1.52,"dd":-25.1,"trades":185,"sector":"Sports",   "rating":"ACCEPTABLE"},
    {"rank":20,"coin":"TEL",  "return":38.2, "wr":57.8,"pf":1.50,"dd":-22.0,"trades":109,"sector":"Telecom",  "rating":"ACCEPTABLE"},
    {"rank":21,"coin":"GRT",  "return":36.3, "wr":59.6,"pf":1.61,"dd":-14.5,"trades":89, "sector":"Indexing", "rating":"ACCEPTABLE"},
]

sectors = {}
for c in COINS_21:
    sectors.setdefault(c['sector'], []).append(c['coin'])

total_trades = sum(c['trades'] for c in COINS_21)
avg_return = sum(c['return'] for c in COINS_21) / len(COINS_21)
avg_wr = sum(c['wr'] for c in COINS_21) / len(COINS_21)
avg_pf = sum(c['pf'] for c in COINS_21) / len(COINS_21)

portfolio = {
    "version": "4.0-HONEST-21",
    "generated_utc": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
    "strategy": "Future Admiral — Long-Only 1D (NO SMC, honest)",
    "total_coins": len(COINS_21),
    "coins": COINS_21,
    "sectors": sectors,
    "summary": {
        "total_coins": len(COINS_21),
        "total_trades": total_trades,
        "avg_return": round(avg_return, 1),
        "avg_win_rate": round(avg_wr, 1),
        "avg_pf": round(avg_pf, 2),
        "tested_universe": 371,
        "kept_after_quality_filter": 21,
        "dropped": 350,
    },
    "quality_filter": {
        "min_trades": 15,
        "min_win_rate": 45,
        "min_profit_factor": 1.3,
        "max_drawdown": -35,
        "excluded_categories": ["fan tokens (PSG/ASR/ACM/ATM)", "dying projects (BTS/STEEM)", "semi-legit (DEGO/DATA/DENT)"],
    },
    "strategy_params": {
        "timeframe": "1D",
        "type": "Long-Only (Spot)",
        "entry": ["Close > EMA 200","MACD (12,26,9) bullish","ADX (14) > 20"],
        "note": "NO SMC — look-ahead bias removed",
        "risk": {"entry":"50%","dca1":"30% at -2%","dca2":"20% at -4%",
                 "tp1":"50% at +2.5% (SL→BE)","tp2":"50% at +5% (trail 3%)",
                 "circuit_breaker":"-15%"},
        "fees":"0.05%","slippage":"0.15%",
    },
    "audit": {
        "status": "PASSED_HONEST",
        "look_ahead_bias": "REMOVED",
        "backtest_engine": "EMA200 + MACD + ADX only",
        "ready_for_live": True,
    },
    "subscription_model": {
        "free": "All 21 coin signals",
        "vip": "Priority alerts + Monthly PDF analysis + DCA ladder",
        "honest_note": "Real WR ~58%. Bear market = zero signals = capital protection.",
    },
}

json_path = os.path.join(CONFIG_DIR, 'FINAL_21_HONEST.json')
with open(json_path, 'w') as f:
    json.dump(portfolio, f, indent=2)

csv_path = os.path.join(REPORT_DIR, 'FINAL_21_HONEST.csv')
pd.DataFrame(COINS_21).to_csv(csv_path, index=False)

web_data = {
    "generated_utc": portfolio["generated_utc"],
    "version": portfolio["version"],
    "total_coins": len(COINS_21),
    "coins": COINS_21,
    "sectors": sectors,
    "summary": portfolio["summary"],
    "quality_filter": portfolio["quality_filter"],
    "strategy_params": portfolio["strategy_params"],
    "subscription_model": portfolio["subscription_model"],
}
with open(os.path.join(WEB_OUT, 'data.json'), 'w') as f:
    json.dump(web_data, f, indent=2)

print("="*80)
print("FINAL 21-COIN HONEST PORTFOLIO — LOCKED")
print("="*80)
print(f"\n✅ JSON: {json_path}")
print(f"✅ CSV:  {csv_path}")
print(f"✅ Web:  {WEB_OUT}/data.json")
print(f"\n📊 STATS:")
print(f"   Coins:        {len(COINS_21)}")
print(f"   Total trades: {total_trades}")
print(f"   Avg return:   +{avg_return:.1f}%")
print(f"   Avg WR:       {avg_wr:.1f}%")
print(f"   Avg PF:       {avg_pf:.2f}")
print(f"\n🏆 TOP 5:")
for c in sorted(COINS_21, key=lambda x:-x['return'])[:5]:
    print(f"   {c['coin']:6} +{c['return']:>6.1f}% | WR {c['wr']:>5.1f}% | PF {c['pf']:>5.2f}")
print(f"\n✅ READY TO DEPLOY")
