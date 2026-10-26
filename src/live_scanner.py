"""
LIVE SIGNAL SCANNER v6.2
Updated: Better Risk/Reward
- TP1: 1.5% (Close 50%, move SL to Breakeven)
- TP2: 3.0% (Close remaining 50%)
- SL: 2.0% (Initial stop loss)
- Threshold: 0.15
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
import pyvsmc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')
STATE_FILE = os.path.join(CONFIG_DIR, 'live_state.json')
TRADES_FILE = os.path.join(CONFIG_DIR, 'live_trades.json')

# ==================== UPDATED PARAMETERS ====================
BUY_TH = 0.15
NEAR_TH = 0.10
TP1_PCT = 0.015          # Partial Take Profit
TP2_PCT = 0.030          # Final Take Profit
SL_PCT = 0.020           # Stop Loss
DCA_1_DROP = 0.010       # DCA Level 1 (-1.0%)
DCA_2_DROP = 0.015       # DCA Level 2 (-1.5%)
MAX_HOLD_H = 100

SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1h'
LIMIT = 500

EXCHANGE_CHAIN = [
    ('okx', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    ('kucoin', {'enableRateLimit': True}),
    ('bitget', {'enableRateLimit': True}),
    ('mexc', {'enableRateLimit': True}),
]


def get_exchange():
    for ex_id, cfg in EXCHANGE_CHAIN:
        try:
            ex = getattr(ccxt, ex_id)(cfg)
            ex.load_markets()
            ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=5)
            print(f'[EXCHANGE] Using: {ex_id}')
            return ex
        except Exception as e:
            print(f'[EXCHANGE] {ex_id}: {str(e)[:80]}')
            continue
    raise RuntimeError('No exchange')


def get_webhook():
    url = os.environ.get('DISCORD_WEBHOOK', '')
    return url if url and 'PASTE' not in url else None


def send(content):
    url = get_webhook()
    if not url:
        print('[DISCORD] Not set')
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
        if r.status_code in (200, 204):
            return True
        return False
    except Exception:
        return False


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def fetch_avax(ex):
    raw = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    return df.set_index('ts').sort_index()


def fetch_btc(ex):
    raw = ex.fetch_ohlcv('BTC/USDT', TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    ema50 = df['close'].astype(float).ewm(span=50, adjust=False).mean()
    return int(float(df['close'].iloc[-1]) > float(ema50.iloc[-1]))


def fetch_avax_btc_ratio(ex):
    try:
        avax_raw = ex.fetch_ohlcv('AVAX/USDT', TIMEFRAME, limit=100)
        btc_raw = ex.fetch_ohlcv('BTC/USDT', TIMEFRAME, limit=100)
        if not avax_raw or not btc_raw:
            return 0
        avax_df = pd.DataFrame(avax_raw, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        btc_df = pd.DataFrame(btc_raw, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        avax_df['ts'] = pd.to_datetime(avax_df['ts'], unit='ms')
        btc_df['ts'] = pd.to_datetime(btc_df['ts'], unit='ms')
        merged = avax_df[['ts', 'c']].merge(btc_df[['ts', 'c']], on='ts', suffixes=('_avax', '_btc'))
        merged['ratio'] = merged['c_avax'].astype(float) / merged['c_btc'].astype(float)
        ema20 = merged['ratio'].ewm(span=20, adjust=False).mean()
        current = float(merged['ratio'].iloc[-1])
        ema = float(ema20.iloc[-1])
        return 1 if current > ema else 0
    except Exception:
        return 0


def fetch_btc_dominance():
    try:
        r = requests.get('https://api.coingecko.com/api/v3/global', timeout=10)
        return float(r.json()['data']['market_cap_percentage']['btc'])
    except Exception:
        return 59.0


def fetch_onchain():
    fg, funding = 50, 0.0
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        fg = int(r.json()['data'][0]['value'])
    except Exception:
        pass
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/premiumIndex', params={'symbol': 'AVAXUSDT'}, timeout=10)
        funding = float(r.json()['lastFundingRate'])
    except Exception:
        pass
    return fg, funding


def compute_score(df, btc_up, fg, funding, ratio_up, btc_dom):
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    try:
        fvg = pyvsmc.detect_fvg(high=high, low=low, close=close)
        st = pyvsmc.detect_structure(high=high, low=low, close=close)
        ob = pyvsmc.detect_order_blocks(open_, high, low, close)
        liq = pyvsmc.detect_liquidity(high=high, low=low, close=close)
        zn = pyvsmc.detect_zones(high=high, low=low, close=close)
        i = -1
        smc = (
            int(st.trend[i]) * 0.20 + int(st.bos_bullish[i]) * 0.15 - int(st.bos_bearish[i]) * 0.15
            + int(st.choch_bullish[i]) * 0.25 - int(st.choch_bearish[i]) * 0.25
            + int(ob.bullish_ob[i]) * 0.20 - int(ob.bearish_ob[i]) * 0.20
            + int(fvg.bullish[i] and not fvg.mitigated[i]) * 0.15
            - int(fvg.bearish[i] and not fvg.mitigated[i]) * 0.15
            + int(liq.sweep_low[i]) * 0.10 - int(liq.sweep_high[i]) * 0.10
            + int(zn.discount[i]) * 0.10 - int(zn.premium[i]) * 0.10
        )
    except Exception:
        smc = 0.0

    onchain = ((50 - fg) / 50) * 0.20 + np.clip(-funding * 1000, -1, 1) * 0.15
    btc_s = (btc_up * 2 - 1) * 0.20
    ratio_score = 0.15 if ratio_up else -0.15

    if btc_dom > 60: dom_score = -0.10
    elif btc_dom < 57.8: dom_score = +0.10
    else: dom_score = 0.0

    master = float(np.clip(smc * 0.45 + onchain * 0.20 + btc_s + ratio_score + dom_score, -1, 1))
    return {'master': master, 'smc': float(smc), 'onchain': float(onchain), 'btc': float(btc_s),
            'ratio': float(ratio_score), 'dom': float(dom_score), 'fg': fg, 'funding': funding,
            'btc_dom': btc_dom, 'ratio_up': ratio_up}


def msg_buy(price, sd, tp1, tp2, sl, dca1, dca2):
    return (
        f"**AVAX/USDT — LONG ENTRY SIGNAL**\n"
        f"```\n"
        f"Signal Type  : BUY (Long)\n"
        f"Confidence   : {sd['master']*100:.1f}%\n"
        f"Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION REQUIRED: Open LONG position on MEXC or OKX**\n"
        f"```\n"
        f"Entry Price  : ${price:.4f}\n"
        f"Stop Loss    : ${sl:.4f} (-2.0%)\n"
        f"Take Profit 1: ${tp1:.4f} (+1.5%) -> Close 50% & Move SL to Entry\n"
        f"Take Profit 2: ${tp2:.4f} (+3.0%) -> Close Remaining\n"
        f"```\n"
        f"**DCA Levels (Optional)**\n"
        f"```\n"
        f"DCA 1        : ${dca1:.4f} (-1.0%)\n"
        f"DCA 2        : ${dca2:.4f} (-1.5%)\n"
        f"```\n"
        f"**Signal Breakdown**\n"
        f"```\n"
        f"SMC: {sd['smc']:+.3f} | Ratio: {sd['ratio']:+.3f} | BTC: {sd['btc']:+.3f}\n"
        f"F&G: {sd['fg']} | Funding: {sd['funding']:.6f} | BTC.D: {sd['btc_dom']:.2f}%\n"
        f"```"
    )

def msg_tp1(entry, tp1, hours):
    return (
        f"**AVAX/USDT — PARTIAL TP HIT (50%)**\n"
        f"```\n"
        f"Entry: ${entry:.4f} -> TP1: ${tp1:.4f} (+1.5%)\n"
        f"Held: {hours:.1f} hours\n"
        f"```\n"
        f"**ACTION: Close 50% of your position now.**\n"
        f"**Move your Stop Loss to Breakeven (${entry:.4f}).**\n"
        f"Let the remaining 50% run towards TP2."
    )

def msg_tp2(entry, tp2, hours):
    return (
        f"**AVAX/USDT — FINAL TP HIT**\n"
        f"```\n"
        f"Entry: ${entry:.4f} -> TP2: ${tp2:.4f} (+3.0%)\n"
        f"Held: {hours:.1f} hours\n"
        f"```\n"
        f"**ACTION: Close remaining 50% of your position.**\n"
        f"Trade fully complete."
    )

def msg_sl(entry, sl, hours, is_be):
    label = "BREAKEVEN SL HIT" if is_be else "STOP LOSS HIT"
    pnl = "0.0%" if is_be else "-2.0%"
    return (
        f"**AVAX/USDT — {label}**\n"
        f"```\n"
        f"Entry: ${entry:.4f} -> SL: ${sl:.4f} ({pnl})\n"
        f"Held: {hours:.1f} hours\n"
        f"```\n"
        f"**ACTION: Close position at market.**\n"
        f"Capital protected."
    )


def run_once():
    state = load_json(STATE_FILE, {'active_trade': None, 'history': [], 'last_signal_ts': None,
                                    'last_heartbeat': None, 'last_hourly': None, 'last_near': None,
                                    'last_score': None})

    ex = get_exchange()
    df = fetch_avax(ex)
    btc_up = fetch_btc(ex)
    ratio_up = fetch_avax_btc_ratio(ex)
    btc_dom = fetch_btc_dominance()
    fg, funding = fetch_onchain()

    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    now = datetime.now(timezone.utc)
    ts_iso = now.isoformat()
    hour_key = now.strftime('%Y-%m-%d-%H')
    today = now.strftime('%Y-%m-%d')

    sd = compute_score(df, btc_up, fg, funding, ratio_up, btc_dom)
    print(f"[SCORE] master={sd['master']:+.4f} | Price=${price:.4f}")

    if state['active_trade']:
        t = state['active_trade']
        entry = t['entry']
        hours = (now - pd.to_datetime(t['opened_at'], utc=True)).total_seconds() / 3600
        
        # Recalculate targets in case DCA happened
        tp1 = t['avg'] * (1 + TP1_PCT)
        tp2 = t['avg'] * (1 + TP2_PCT)
        is_be = t.get('tp1_hit', False)
        
        # 1. Check DCA (Only if TP1 not hit)
        if not is_be:
            if not t.get('dca1_hit', False) and low <= entry * (1 - DCA_1_DROP):
                t['dca1_hit'] = True
                t['avg'] = (entry + (entry * (1 - DCA_1_DROP))) / 2 # 50/50 average
                send(f"**AVAX — DCA 1 TRIGGERED**\n```\nPrice: ${price:.4f}\nNew Avg: ${t['avg']:.4f}\n```\n**ACTION: Add 25% more capital.**")
            elif t.get('dca1_hit', False) and not t.get('dca2_hit', False) and low <= entry * (1 - DCA_2_DROP):
                t['dca2_hit'] = True
                t['avg'] = (t['avg'] * 2 + (entry * (1 - DCA_2_DROP))) / 3
                send(f"**AVAX — DCA 2 TRIGGERED**\n```\nPrice: ${price:.4f}\nNew Avg: ${t['avg']:.4f}\n```\n**ACTION: Add 25% more capital.**")

        # 2. Check TP1 (Partial)
        if not is_be and high >= tp1:
            t['tp1_hit'] = True
            t['sl'] = t['avg'] # Move SL to Breakeven
            send(msg_tp1(entry, tp1, hours))
            
        # 3. Check TP2 (Final)
        elif high >= tp2:
            send(msg_tp2(entry, tp2, hours))
            state['history'].append({**t, 'exit': tp2, 'type': 'TP2', 'profit_pct': 3.0, 'closed_at': ts_iso})
            state['active_trade'] = None

        # 4. Check SL (Initial or Breakeven)
        elif low <= t['sl']:
            send(msg_sl(entry, t['sl'], hours, is_be))
            pnl = 0.0 if is_be else -2.0
            state['history'].append({**t, 'exit': t['sl'], 'type': 'SL', 'profit_pct': pnl, 'closed_at': ts_iso})
            state['active_trade'] = None

        # 5. Time Exit
        elif hours >= MAX_HOLD_H:
            pl = (price / t['avg'] - 1) * 100
            send(f"**AVAX — TIME EXIT**\n```\nHeld: {hours:.1f}h\nP&L: {pl:+.2f}%\n```")
            state['history'].append({**t, 'exit': price, 'type': 'TIME', 'profit_pct': pl, 'closed_at': ts_iso})
            state['active_trade'] = None

    elif sd['master'] >= BUY_TH and state.get('last_signal_ts') != ts_iso:
        tp1 = price * (1 + TP1_PCT)
        tp2 = price * (1 + TP2_PCT)
        sl = price * (1 - SL_PCT)
        dca1 = price * (1 - DCA_1_DROP)
        dca2 = price * (1 - DCA_2_DROP)
        
        send(msg_buy(price, sd, tp1, tp2, sl, dca1, dca2))
        
        state['active_trade'] = {
            'entry': price, 'avg': price, 'tp1': tp1, 'tp2': tp2, 'sl': sl,
            'tp1_hit': False, 'dca1_hit': False, 'dca2_hit': False,
            'opened_at': ts_iso, 'score': sd['master']
        }
        state['last_signal_ts'] = ts_iso

    # Hourly heartbeat / Near-miss (same as before)
    elif sd['master'] >= NEAR_TH and state.get('last_near') != hour_key:
        send(f"**AVAX WATCHING** | Score: {sd['master']:+.3f} | Price: ${price:.4f}")
        state['last_near'] = hour_key
    elif state.get('last_hourly') != hour_key:
        status = 'Active trade' if state['active_trade'] else 'Waiting'
        send(f"**AVAX Status** | Score: {sd['master']:+.3f} | Price: ${price:.4f} | {status}")
        state['last_hourly'] = hour_key

    if state.get('last_heartbeat') != today:
        h = state['history']
        wins = sum(1 for x in h if x.get('profit_pct', 0) > 0)
        total = len([x for x in h if x.get('type') in ('TP1', 'TP2', 'SL')])
        wr = (wins / total * 100) if total else 0
        status = 'ACTIVE' if state['active_trade'] else 'WAITING'
        send(f"**DAILY SUMMARY | {today}**\n```\nPrice: ${price:.4f}\nScore: {sd['master']:+.3f}\nTrades: {total} | WR: {wr:.1f}%\n```")
        state['last_heartbeat'] = today

    state['last_score'] = sd['master']
    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

if __name__ == '__main__':
    run_once()
