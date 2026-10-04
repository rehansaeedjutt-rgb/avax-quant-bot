"""
LOCKED STRATEGY v1.0
Final parameters:
- Buy threshold: 0.30
- TP: 1.5% | SL: 3.0%
- Position size: 20%
- Max hold: 100 hours

Backtest (OOS):
- WR: 83.7% | SL: 16.3% | PF: 2.22 | DD: -1.46%
- Return: 8.28% per year
"""
import os
import json

ROOT = 'C:/avax_quant_system'
CONFIG_DIR = os.path.join(ROOT, 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)

locked = {
    'version': '1.0',
    'locked_at': '2026-10-04',
    'strategy': 'SMC + On-chain + BTC Master Signal',
    'timeframe': '1h',
    'params': {
        'buy_threshold': 0.30,
        'tp_pct': 0.015,
        'sl_pct': 0.030,
        'position_size': 0.20,
        'max_hold_hours': 100,
    },
    'backtest_oos': {
        'return_pct': 8.28,
        'win_rate': 83.7,
        'sl_rate': 16.3,
        'profit_factor': 2.22,
        'max_dd': -1.46,
        'trades_per_year': 60,
    },
    'signal_sources': [
        'SMC: FVG + Order Blocks + BOS + CHOCH + Liquidity + Zones',
        'On-chain: Fear & Greed + Funding rates',
        'BTC: EMA50 trend filter',
    ],
    'notes': 'Chosen for HIGH WIN RATE (83.7%) and LOW SL RATE (16.3%). Best for user requirements: low SL hits, profitable long-term.',
}

path = f'{CONFIG_DIR}/locked_strategy_v1.json'
with open(path, 'w') as f:
    json.dump(locked, f, indent=2)

print('=' * 70)
print('STRATEGY LOCKED')
print('=' * 70)
print(f'Saved: {path}')
print()
print(json.dumps(locked, indent=2))
