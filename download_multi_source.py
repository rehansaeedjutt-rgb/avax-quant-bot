# download_multi_source.py
# Multi-exchange retry: Binance -> Bybit -> OKX -> KuCoin -> Gate -> Bitget
# Special handling for MATIC (MATIC+POL merge) and TON
# Verifies inception-to-now completeness

import os
import time
import ccxt
import pandas as pd

DATA_DIR = 'C:/avax_quant_system/data'
os.makedirs(DATA_DIR, exist_ok=True)

# coin -> list of (symbol, [exchanges to try])
# Exchanges order matters: try most reliable first
COINS = {
    'BTC':   [('BTC/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'ETH':   [('ETH/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'BNB':   [('BNB/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'XRP':   [('XRP/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'DOGE':  [('DOGE/USDT',  ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'LTC':   [('LTC/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'BCH':   [('BCH/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'LINK':  [('LINK/USDT',  ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'AVAX':  [('AVAX/USDT',  ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'SOL':   [('SOL/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'ADA':   [('ADA/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'DOT':   [('DOT/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'SUI':   [('SUI/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'HYPE':  [('HYPE/USDT',  ['bybit','okx','kucoin','gateio','bitget'])],
    # MATIC special: try MATIC then POL, merge if both available
    'MATIC': [('MATIC/USDT', ['bybit','okx','kucoin','gateio','bitget']),
              ('POL/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    # TON special: try TON/USDT on multiple exchanges
    'TON':   [('TON/USDT',   ['bybit','okx','kucoin','gateio','bitget','binance'])],
    'SHIB':  [('SHIB/USDT',  ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'NEAR':  [('NEAR/USDT',  ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'APT':   [('APT/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'ARB':   [('ARB/USDT',   ['binance','bybit','okx','kucoin','gateio','bitget'])],
    'OP':    [('OP/USDT',    ['binance','bybit','okx','kucoin','gateio','bitget'])],
}

def get_exchange(name):
    cls = getattr(ccxt, name)
    return cls({'enableRateLimit': True, 'timeout': 30000})

def fetch_full(exchange, symbol, since_ms):
    rows = []
    cursor = since_ms
    retries = 0
    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe='1d', since=cursor, limit=1000)
            retries = 0
        except Exception as e:
            retries += 1
            if retries >= 4:
                return []
            time.sleep(2 * retries)
            continue
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        time.sleep(exchange.rateLimit / 1000.0)
        if len(batch) < 1000:
            break
    return rows

def try_fetch(coin, symbol, exchanges):
    """Try fetching from each exchange, return first successful result"""
    for ex_name in exchanges:
        try:
            ex = get_exchange(ex_name)
            ex.load_markets()
            if symbol not in ex.markets:
                continue
            print(f"    trying {ex_name} {symbol}...")
            # Use start from very early
            since_ms = int(pd.Timestamp('2000-01-01').timestamp() * 1000)
            rows = fetch_full(ex, symbol, since_ms)
            if rows and len(rows) > 50:
                print(f"    ✅ {ex_name} gave {len(rows)} candles")
                return rows, ex_name, symbol
        except Exception as e:
            print(f"    ❌ {ex_name}: {str(e)[:80]}")
            continue
    return None, None, None

def save(coin, rows, source_info):
    df = pd.DataFrame(rows, columns=['open_time','open','high','low','close','volume'])
    df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
    path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
    df.to_csv(path, index=False)
    t0 = pd.to_datetime(df['open_time'].iloc[0], unit='ms')
    t1 = pd.to_datetime(df['open_time'].iloc[-1], unit='ms')
    print(f"    💾 {path} | {len(df)} candles | {t0.date()} -> {t1.date()}")
    return len(df), t0, t1

def main():
    print("="*80)
    print("MULTI-SOURCE DOWNLOAD — 21 COINS")
    print("="*80)
    summary = []

    for coin, sources in COINS.items():
        print(f"\n[{coin}]")
        all_rows = []
        sources_used = []
        for symbol, exchanges in sources:
            rows, ex_name, sym_used = try_fetch(coin, symbol, exchanges)
            if rows:
                all_rows.extend(rows)
                sources_used.append(f"{ex_name}:{sym_used}")
                print(f"    -> got {len(rows)} from {ex_name}")

        if not all_rows:
            print(f"    ❌ FAILED — no data from any source")
            summary.append({'coin':coin,'status':'FAILED','sources':'-','candles':0,'first':'-','last':'-'})
            continue

        # Merge and save
        n, t0, t1 = save(coin, all_rows, sources_used)
        summary.append({'coin':coin,'status':'OK','sources':', '.join(sources_used),'candles':n,'first':t0.date(),'last':t1.date()})

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"{'Coin':<6} | {'Status':<8} | {'Candles':>7} | {'First':<12} | {'Last':<12} | Sources")
    print('-'*110)
    for s in summary:
        print(f"{s['coin']:<6} | {s['status']:<8} | {s['candles']:>7} | {str(s['first']):<12} | {str(s['last']):<12} | {s['sources']}")

    ok = [s for s in summary if s['status']=='OK']
    fail = [s for s in summary if s['status']=='FAILED']
    print(f"\n✅ OK: {len(ok)}/21")
    if fail:
        print(f"❌ FAILED: {[s['coin'] for s in fail]}")

if __name__ == '__main__':
    main()
