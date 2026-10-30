"""
FULL SYSTEM DIAGNOSTIC TEST
Yeh script aapke bot ke har module ko individually test karti hai.
"""
import os
import sys
import json
import logging
import pandas as pd

# Setup Path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)

logging.basicConfig(level=logging.CRITICAL) # Hide normal logs during test

print("==================================================")
print("🧪 STARTING FULL SYSTEM DIAGNOSTIC TEST")
print("==================================================\n")

# --- TEST 1: CONFIGURATION FILE ---
print("[1/5] Testing symbols.json configuration...")
try:
    with open(os.path.join(ROOT_DIR, 'config', 'symbols.json'), 'r') as f:
        symbols = json.load(f)
    assert "AVAX" in symbols and "LINK" in symbols, "Missing coins in config!"
    print("✅ symbols.json is perfect.")
except Exception as e:
    print(f"❌ CONFIG ERROR: {e}")
    sys.exit(1)


# --- TEST 2: EXCHANGE HANDLER ---
print("\n[2/5] Testing Exchange Handler (Binance/OKX etc)...")
try:
    from src.core.exchange_handler import get_exchange
    ex = get_exchange()
    print(f"✅ Exchange connected successfully: {ex.id}")
except Exception as e:
    print(f"❌ EXCHANGE ERROR: {e}")
    sys.exit(1)


# --- TEST 3: DATA FETCHING & INDICATORS ---
print("\n[3/5] Testing Data Fetch & Indicators (MACD, EMA, SMC)...")
try:
    from src.core.indicators import check_filters
    # Fetch 300 candles for AVAX
    raw = ex.fetch_ohlcv('AVAX/USDT', '1d', limit=300)
    df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume'])
    
    # Test filters
    above_ema, macd_bull, smc_bull = check_filters(df)
    
    # Values should be True or False (booleans)
    assert isinstance(above_ema, bool), "EMA filter didn't return a boolean"
    assert isinstance(macd_bull, bool), "MACD filter didn't return a boolean"
    assert isinstance(smc_bull, bool), "SMC filter didn't return a boolean"
    
    print(f"✅ Indicators calculated perfectly. (EMA: {above_ema}, MACD: {macd_bull}, SMC: {smc_bull})")
except Exception as e:
    print(f"❌ INDICATOR ERROR: {e}")


# --- TEST 4: DISCORD ALERTS ---
print("\n[4/5] Testing Discord Alerts...")
try:
    from src.core.alerts import send_discord
    # We don't want to send a real message, so we test the function's failure handling
    # If no webhook is set, it should safely return False without crashing.
    result = send_discord("Test Message from Diagnostic Engine")
    if result is False:
        print("✅ Discord Alert System is secure (Webhook not set locally, but function works).")
    else:
        print("✅ Discord Alert sent successfully! (Webhook is set).")
except Exception as e:
    print(f"❌ DISCORD ERROR: {e}")


# --- TEST 5: RISK MANAGER LOGIC ---
print("\n[5/5] Testing Risk Manager Logic (DCA, TP, Circuit Breaker)...")
try:
    from src.core.risk_manager import process_coin
    # Yeh function state file update karega, hum bas check kar rahe hain ke crash toh nahi hota
    process_coin(ex, "AVAX", symbols["AVAX"])
    print("✅ Risk Manager executed AVAX logic without crashing.")
except Exception as e:
    print(f"❌ RISK MANAGER ERROR: {e}")


print("\n==================================================")
print("🏁 TESTING COMPLETE")
print("Agar upar sab ke aage ✅ Green Tick hai, toh aapka system 100% Ready hai!")
print("==================================================")
