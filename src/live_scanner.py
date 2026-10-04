"""
LIVE SIGNAL SCANNER v1.0
Uses locked strategy (0.30 buy, TP 1.5%, SL 3%).
Runs every hour on GitHub Actions.
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

# ============ LOCKED PARAMS ============
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
            print(f'[EXCHANGE] {ex_id} failed: {str(e)[:80]}')
            continue
    raise RuntimeError('No exchange available')


def get_webhook():
    url = os.environ.get('DISCORD_WEBHOOK', '')
    return url if url and 'PASTE' not in url else None


def send(content):
    url = get_webhook()
    if not url:
        print('[DISCORD] Webhook not set')
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
        if r.status_code in (200, 204):
            print('[DISCORD] Sent OK')
            return True
        print(f'[DISCORD] Failed: {r.status_code}')
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
    df = df.set_index('ts').sort_index()
    return df


def fetch_btc(ex):
    raw = ex.fetch_ohlcv('BTC/USDT', TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    ema50 = df['close'].ewm(span=50, adjust=False).mean()
    btc_up = int(df['close'].iloc[-1] > ema50.iloc[-1])
    return btc_up


def fetch_onchain():
    """Fetch live Fear & Greed + Funding."""
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


def compute_master_score(df, btc_up, fg, funding):
    """Compute master score for last candle."""
    # Need enough data for SMC
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)

    # SMC on last candle
    try:
        fvg = pyvsmc.detect_fvg(high=high, low=low, close=close)
        st = pyvsmc.detect_structure(high=high, low=low, close=close)
        ob = pyvsmc.detect_order_blocks(open_, high, low, close)
        liq = pyvsmc.detect_liquidity(high=high, low=low, close=close)
        zn = pyvsmc.detect_zones(high=high, low=low, close=close)

        i = -1
        trend = int(st.trend[i])
        bos_bull = int(st.bos_bullish[i])
        bos_bear = int(st.bos_bearish[i])
        choch_bull = int(st.choch_bullish[i])
        choch_bear = int(st.choch_bearish[i])
        ob_bull = int(ob.bullish_ob[i])
        ob_bear = int(ob.bearish_ob[i])
        fvg_bull = int(fvg.bullish[i] and not fvg.mitigated[i])
        fvg_bear = int(fvg.bearish[i] and not fvg.mitigated[i])
        sweep_low = int(liq.sweep_low[i])
        sweep_high = int(liq.sweep_high[i])
        discount = int(zn.discount[i])
        premium = int(zn.premium[i])

        smc_score = (
            trend * 0.20
            + bos_bull * 0.15 - bos_bear * 0.15
            + choch_bull * 0.25 - choch_bear * 0.25
            + ob_bull * 0.20 - ob_bear * 0.20
            + fvg_bull * 0.15 - fvg_bear * 0.15
            + sweep_low * 0.10 - sweep_high * 0.10
            + discount * 0.10 - premium * 0.10
        )
    except Exception as e:
        print(f'[SMC] Error: {e}')
        smc_score = 0.0
        trend = 0

    # On-chain score
    fg_score = ((50 - fg) / 50) * 0.20
    funding_score = np.clip(-funding * 1000, -1, 1) * 0.15
    onchain_score = fg_score + funding_score

    # BTC score
    btc_score = (btc_up * 2 - 1) * 0.15

    master = np.clip(smc_score * 0.55 + onchain_score * 0.25 + btc_score * 0.20, -1, 1)

    return {
        'master': float(master),
        'smc': float(smc_score),
        'onchain': float(onchain_score),
        'btc': float(btc_score),
        'trend': trend,
        'fg': fg,
        'funding': funding,
    }


def format_buy_signal(price, tp, sl, score_data):
    return (
        f"🟢 **BUY SIGNAL** | AVAX/USDT | 1h\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Entry:** `${price:.4f}`\n"
        f"🎯 **Take Profit:** `${tp:.4f}` (+{TP_PCT*100:.1f}%)\n"
        f"🛑 **Stop Loss:** `${sl:.4f}` (-{SL_PCT*100:.1f}%)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Master Score: `{score_data['master']:+.3f}`\n"
        f"🎯 SMC: `{score_data['smc']:+.3f}` | On-chain: `{score_data['onchain']:+.3f}` | BTC: `{score_data['btc']:+.3f}`\n"
        f"😨 F&G: `{score_data['fg']}` | 💰 Funding: `{score_data['funding']:.6f}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )


def format_tp_hit(entry, exit_price, profit_pct, hours):
    return (
        f"✅ **TAKE PROFIT HIT** | AVAX/USDT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Entry: `${entry:.4f}` → Exit: `${exit_price:.4f}`\n"
        f"📈 Profit: `+{profit_pct:.2f}%`\n"
        f"⏱ Held: `{hours:.1f}h`"
    )


def format_sl_hit(entry, exit_price, loss_pct, hours):
    return (
        f"🛑 **STOP LOSS HIT** | AVAX/USDT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Entry: `${entry:.4f}` → Exit: `${exit_price:.4f}`\n"
        f"📉 Loss: `{loss_pct:.2f}%`\n"
        f"⏱ Held: `{hours:.1f}h`"
    )


def run_once():
    state = load_json(STATE_FILE, {
        'active_trade': None, 'history': [], 'last_signal_ts': None,
        'last_heartbeat': None,
    })

    ex = get_exchange()
    df = fetch_avax(ex)
    btc_up = fetch_btc(ex)
    fg, funding = fetch_onchain()

    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    now = datetime.now(timezone.utc)
    ts_iso = now.isoformat()

    print(f"[PRICE] ${price:.4f} | H ${high:.4f} | L ${low:.4f}")
    print(f"[BTC] Up={btc_up} | F&G={fg} | Funding={funding:.6f}")

    # ---- Manage active trade ----
    if state['active_trade']:
        t = state['active_trade']
        entry = t['entry']
        tp_price = entry * (1 + TP_PCT)
        sl_price = entry * (1 - SL_PCT)
        hours = (now - pd.to_datetime(t['opened_at'], utc=True)).total_seconds() / 3600

        if high >= tp_price:
            profit = TP_PCT * 100
            send(format_tp_hit(entry, tp_price, profit, hours))
            state['history'].append({**t, 'exit': tp_price, 'type': 'TP',
                                     'profit_pct': profit, 'closed_at': ts_iso})
            state['active_trade'] = None
            print(f'[TRADE] TP HIT +{profit}%')
        elif low <= sl_price:
            loss = -SL_PCT * 100
            send(format_sl_hit(entry, sl_price, loss, hours))
            state['history'].append({**t, 'exit': sl_price, 'type': 'SL',
                                     'profit_pct': loss, 'closed_at': ts_iso})
            state['active_trade'] = None
            print(f'[TRADE] SL HIT {loss}%')
        elif hours >= MAX_HOLD_H:
            # Time exit
            send(f"⏰ **TIME EXIT** | AVAX | Held {hours:.1f}h | P&L at close: {((price/entry-1)*100):+.2f}%")
            state['history'].append({**t, 'exit': price, 'type': 'TIME',
                                     'profit_pct': (price/entry-1)*100, 'closed_at': ts_iso})
            state['active_trade'] = None

    # ---- Check new signal ----
    if not state['active_trade']:
        score_data = compute_master_score(df, btc_up, fg, funding)
        print(f"[SCORE] master={score_data['master']:+.4f} smc={score_data['smc']:+.4f} "
              f"onchain={score_data['onchain']:+.4f} btc={score_data['btc']:+.4f}")

        if score_data['master'] >= BUY_TH and state.get('last_signal_ts') != ts_iso:
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            send(format_buy_signal(price, tp, sl, score_data))
            state['active_trade'] = {
                'entry': price, 'tp': tp, 'sl': sl,
                'opened_at': ts_iso, 'score': score_data['master'],
            }
            state['last_signal_ts'] = ts_iso
            print(f'[SIGNAL] BUY @ ${price:.4f}')

    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

    # ---- Daily heartbeat ----
    today = now.strftime('%Y-%m-%d')
    if state.get('last_heartbeat') != today:
        history = state['history']
        wins = sum(1 for h in history if h.get('profit_pct', 0) > 0)
        total = len([h for h in history if h.get('type') in ('TP', 'SL')])
        wr = (wins / total * 100) if total else 0
        status = 'Active trade' if state['active_trade'] else 'Waiting'

        send(
            f"📊 **DAILY SUMMARY** | {today}\n"
            f"💰 Price: `${price:.4f}`\n"
            f"🎯 Status: {status}\n"
            f"📈 Trades: {total} | WR: `{wr:.1f}%`\n"
            f"📊 Master score: `{compute_master_score(df, btc_up, fg, funding)['master']:+.3f}`"
        )
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)


if __name__ == '__main__':
    run_once()
