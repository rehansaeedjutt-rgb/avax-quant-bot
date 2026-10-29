import json

config = {
  "AVAX": {
    "symbol": "AVAX/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.05,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_avax.json", "trades_file": "live_trades_avax.json"
  },
  "LINK": {
    "symbol": "LINK/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.06,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_link.json", "trades_file": "live_trades_link.json"
  },
  "SOL": {
    "symbol": "SOL/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.05,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_sol.json", "trades_file": "live_trades_sol.json"
  },
  "ADA": {
    "symbol": "ADA/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.05,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_ada.json", "trades_file": "live_trades_ada.json"
  },
  "SUI": {
    "symbol": "SUI/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.05,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_sui.json", "trades_file": "live_trades_sui.json"
  },
  "DOT": {
    "symbol": "DOT/USDT", "timeframe": "1d", "tp1_pct": 0.025, "tp2_pct": 0.05,
    "dca1_drop": 0.02, "dca2_drop": 0.04, "macro_sl_pct": 0.15, "max_hold_hours": 336,
    "state_file": "live_state_dot.json", "trades_file": "live_trades_dot.json"
  }
}

with open("C:/avax_quant_system/config/symbols.json", "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    
print("✅ symbols.json created successfully!")
