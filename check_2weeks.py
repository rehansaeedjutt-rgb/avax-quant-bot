import os
import json
import requests
from datetime import datetime

# Fetch live state from GitHub
url = "https://raw.githubusercontent.com/rehansaeedjutt-rgb/avax-quant-bot/main/config/live_state.json"
try:
    r = requests.get(url, timeout=10)
    state = r.json()
    print("=" * 50)
    print("CURRENT LIVE STATE")
    print("=" * 50)
    print(f"Active Trade: {state.get('active_trade')}")
    print(f"Last Score: {state.get('last_score', 'N/A')}")
    print(f"Last Signal: {state.get('last_signal_ts', 'N/A')}")
    
    history = state.get('history', [])
    print(f"Total Trades Executed: {len(history)}")
    
    if len(history) > 0:
        print("\nTRADE HISTORY:")
        for t in history[-10:]: # Last 10 trades
            print(f" - Entry: {t.get('entry')}, Exit: {t.get('exit')}, Type: {t.get('type')}, PnL: {t.get('profit_pct')}%")
    else:
        print("\nNo trades executed in this period.")
        print("Reason: Master score never crossed the buy threshold (+0.15).")
        
except Exception as e:
    print(f"Error fetching data: {e}")
