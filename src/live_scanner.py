"""
LIVE SIGNAL SCANNER v3.0 — Discord only
Clean version without WhatsApp.
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

BUY_TH = 0.30
TP_PCT = 0.015
SL_PCT = 0.030
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
            print('[DISCORD] Sent')
            return True
        return False
    except Exception as e:
        print(f'[DISCORD] Error: {e}')
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


def fetch_onchain():
    fg, funding = 50, 0.0
    try:
        r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        fg = int(r.json()['data'][0]['value'])
    except Exception:
        pass
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/premiumIndex',
                         params={'symbol': 'AVAXUSDT'}, timeout=10)
        funding = float(r.json()['lastFundingRate'])
    except Exception:
        pass
    return fg, funding


def compute_score(df, btc_up, fg, funding):
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
            int(st.trend[i]) * 0.20
            + int(st.bos_bullish[i]) * 0.15 - int(st.bos_bearish[i]) * 0.15
            + int(st.choch_bullish[i]) * 0.25 - int(st.choch_bearish[i]) * 0.25
            + int(ob.bullish_ob[i]) * 0.20 - int(ob.bearish_ob[i]) * 0.20
            + int(fvg.bullish[i] and not fvg.mitigated[i]) * 0.15
            - int(fvg.bearish[i] and not fvg.mitigated[i]) * 0.15
            + int(liq.sweep_low[i]) * 0.10 - int(liq.sweep_high[i]) * 0.10
            + int(zn.discount[i]) * 0.10 - int(zn.premium[i]) * 0.10
        )
    except Exception as e:
        print(f'[SMC] Error: {e}')
        smc = 0.0
    onchain = ((50 - fg) / 50) * 0.20 + np.clip(-funding * 1000, -1, 1) * 0.15
    btc_s = (btc_up * 2 - 1) * 0.15
    master = float(np.clip(smc * 0.55 + onchain * 0.25 + btc_s * 0.20, -1, 1))
    return {'master': master, 'smc': float(smc), 'onchain': float(onchain), 'btc': float(btc_s),
            'fg': fg, 'funding': funding}


def run_once():
    state = load_json(STATE_FILE, {'active_trade': None, 'history': [],
                                    'last_signal_ts': None, 'last_heartbeat': None})

    ex = get_exchange()
    df = fetch_avax(ex)
    btc_up = fetch_btc(ex)
    fg, funding = fetch_onchain()

    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    now = datetime.now(timezone.utc)
    ts_iso = now.isoformat()

    print(f'[PRICE] ${price:.4f} | H ${high:.4f} | L ${low:.4f}')
    print(f'[BTC] {btc_up} | F&G={fg} | Funding={funding:.6f}')

    # Manage active trade
    if state['active_trade']:
        t = state['active_trade']
        entry = t['entry']
        tp_price = entry * (1 + TP_PCT)
        sl_price = entry * (1 - SL_PCT)
        hours = (now - pd.to_datetime(t['opened_at'], utc=True)).total_seconds() / 3600

        if high >= tp_price:
            profit_pct = TP_PCT * 100
            send(
                f"✅ **TAKE PROFIT HIT** | AVAX/USDT\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Entry: `${entry:.4f}` → Exit: `${tp_price:.4f}`\n"
                f"📈 Profit: `+{profit_pct:.2f}%`\n"
                f"⏱ Held: `{hours:.1f}h`"
            )
            state['history'].append({**t, 'exit': tp_price, 'type': 'TP',
                                     'profit_pct': profit_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            print(f'[TRADE] TP HIT +{profit_pct}%')
        elif low <= sl_price:
            loss_pct = -SL_PCT * 100
            send(
                f"🛑 **STOP LOSS HIT** | AVAX/USDT\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Entry: `${entry:.4f}` → Exit: `${sl_price:.4f}`\n"
                f"📉 Loss: `{loss_pct:.2f}%`\n"
                f"⏱ Held: `{hours:.1f}h`"
            )
            state['history'].append({**t, 'exit': sl_price, 'type': 'SL',
                                     'profit_pct': loss_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            print(f'[TRADE] SL HIT {loss_pct}%')
        elif hours >= MAX_HOLD_H:
            pl = (price / entry - 1) * 100
            send(
                f"⏰ **TIME EXIT** | AVAX/USDT\n"
                f"Held: `{hours:.1f}h` | P&L: `{pl:+.2f}%`"
            )
            state['history'].append({**t, 'exit': price, 'type': 'TIME',
                                     'profit_pct': pl, 'closed_at': ts_iso})
            state['active_trade'] = None

    # New signal check
    if not state['active_trade']:
        sd = compute_score(df, btc_up, fg, funding)
        print(f"[SCORE] master={sd['master']:+.4f} smc={sd['smc']:+.4f} onchain={sd['onchain']:+.4f} btc={sd['btc']:+.4f}")

        if sd['master'] >= BUY_TH and state.get('last_signal_ts') != ts_iso:
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            send(
                f"🟢 **BUY SIGNAL** | AVAX/USDT | 1h\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Entry:** `${price:.4f}`\n"
                f"🎯 **Take Profit:** `${tp:.4f}` (+{TP_PCT*100:.1f}%)\n"
                f"🛑 **Stop Loss:** `${sl:.4f}` (-{SL_PCT*100:.1f}%)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 Master Score: `{sd['master']:+.3f}`\n"
                f"🎯 SMC: `{sd['smc']:+.3f}` | On-chain: `{sd['onchain']:+.3f}` | BTC: `{sd['btc']:+.3f}`\n"
                f"😨 F&G: `{fg}` | 💰 Funding: `{funding:.6f}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {now.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            state['active_trade'] = {'entry': price, 'tp': tp, 'sl': sl,
                                     'opened_at': ts_iso, 'score': sd['master']}
            state['last_signal_ts'] = ts_iso
            print(f'[SIGNAL] BUY @ ${price:.4f}')

    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

    # Daily heartbeat
    today = now.strftime('%Y-%m-%d')
    if state.get('last_heartbeat') != today:
        h = state['history']
        wins = sum(1 for x in h if x.get('profit_pct', 0) > 0)
        total = len([x for x in h if x.get('type') in ('TP', 'SL')])
        wr = (wins / total * 100) if total else 0
        status = 'Active trade' if state['active_trade'] else 'Waiting'
        sd = compute_score(df, btc_up, fg, funding)

        send(
            f"📊 **DAILY SUMMARY** | {today}\n"
            f"💰 Price: `${price:.4f}`\n"
            f"🎯 Status: {status}\n"
            f"📈 Trades: {total} | WR: `{wr:.1f}%`\n"
            f"📊 Master score: `{sd['master']:+.3f}`"
        )
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)


if __name__ == '__main__':
    run_once()
