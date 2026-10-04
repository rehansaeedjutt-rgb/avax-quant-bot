"""
LIVE SIGNAL SCANNER v4.0 — Professional Discord Messages
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

# Locked strategy parameters
BUY_TH = 0.30
TP_PCT = 0.015
SL_PCT = 0.030
DCA_LEVEL_2_DROP = 0.02
DCA_LEVEL_3_DROP = 0.04
DCA_LEVEL_2_ADD = 0.30
DCA_LEVEL_3_ADD = 0.20
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
    return {'master': master, 'smc': float(smc), 'onchain': float(onchain),
            'btc': float(btc_s), 'fg': fg, 'funding': funding}


def professional_buy_message(price, tp, sl, sd, dca2, dca3):
    """Professional BUY signal with clear instructions."""
    return (
        f"**AVAX/USDT — LONG ENTRY SIGNAL**\n"
        f"```\n"
        f"Symbol       : AVAX/USDT\n"
        f"Timeframe    : 1 Hour\n"
        f"Signal Type  : BUY (Long)\n"
        f"Confidence   : {sd['master']*100:.1f}% (threshold: 30.0%)\n"
        f"Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION REQUIRED: Open LONG position on MEXC or OKX**\n"
        f"```\n"
        f"Entry Price  : ${price:.4f}\n"
        f"Take Profit  : ${tp:.4f}  (+{TP_PCT*100:.2f}%)\n"
        f"Stop Loss    : ${sl:.4f}  (-{SL_PCT*100:.2f}%)\n"
        f"```\n"
        f"**Recommended Position Sizing**\n"
        f"```\n"
        f"Total Capital    : 100%\n"
        f"Initial Entry    : 50% of capital at ${price:.4f}\n"
        f"DCA Level 2      : 30% if price drops to ${dca2:.4f} (-2.0%)\n"
        f"DCA Level 3      : 20% if price drops to ${dca3:.4f} (-4.0%)\n"
        f"```\n"
        f"**Signal Breakdown**\n"
        f"```\n"
        f"SMC Score      : {sd['smc']:+.3f} (weight 55%)\n"
        f"On-Chain Score : {sd['onchain']:+.3f} (weight 25%)\n"
        f"BTC Trend      : {sd['btc']:+.3f} (weight 20%)\n"
        f"Fear & Greed   : {sd['fg']}\n"
        f"Funding Rate   : {sd['funding']:.6f}\n"
        f"```\n"
        f"**Next Steps**\n"
        f"1. Place limit buy at `${price:.4f}` on MEXC/OKX\n"
        f"2. Set take-profit sell order at `${tp:.4f}`\n"
        f"3. Set stop-loss sell order at `${sl:.4f}`\n"
        f"4. Set DCA alerts at `${dca2:.4f}` and `${dca3:.4f}`\n"
        f"5. Wait for TP or SL notification"
    )


def professional_dca_message(level, price, dca_price, new_avg, new_tp, add_pct):
    """DCA level hit message."""
    return (
        f"**AVAX/USDT — DCA LEVEL {level} TRIGGERED**\n"
        f"```\n"
        f"Current Price  : ${price:.4f}\n"
        f"DCA Trigger    : ${dca_price:.4f}\n"
        f"Time (UTC)     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION REQUIRED: Add more capital to existing LONG**\n"
        f"```\n"
        f"Add Amount     : {add_pct}% of original capital\n"
        f"New Average    : ${new_avg:.4f}\n"
        f"New Take Profit: ${new_tp:.4f}  (+{TP_PCT*100:.2f}%)\n"
        f"```\n"
        f"**Instructions**\n"
        f"1. Buy additional AVAX worth {add_pct}% of your capital\n"
        f"2. Update your take-profit order to `${new_tp:.4f}`\n"
        f"3. Keep stop-loss at original level\n"
        f"4. Hold and wait for TP notification"
    )


def professional_tp_message(entry, exit_price, profit_pct, hours):
    """Professional TP hit message."""
    return (
        f"**AVAX/USDT — TAKE PROFIT EXECUTED**\n"
        f"```\n"
        f"Symbol         : AVAX/USDT\n"
        f"Position       : Closed (PROFIT)\n"
        f"Entry Price    : ${entry:.4f}\n"
        f"Exit Price     : ${exit_price:.4f}\n"
        f"Profit         : +{profit_pct:.2f}%\n"
        f"Holding Time   : {hours:.1f} hours\n"
        f"Time (UTC)     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION: Sell entire position at market if not already done**\n"
        f"```\n"
        f"Status         : Profit secured\n"
        f"Next Action    : Wait for next BUY signal\n"
        f"```"
    )


def professional_sl_message(entry, exit_price, loss_pct, hours):
    """Professional SL hit message."""
    return (
        f"**AVAX/USDT — STOP LOSS EXECUTED**\n"
        f"```\n"
        f"Symbol         : AVAX/USDT\n"
        f"Position       : Closed (LOSS)\n"
        f"Entry Price    : ${entry:.4f}\n"
        f"Exit Price     : ${exit_price:.4f}\n"
        f"Loss           : {loss_pct:.2f}%\n"
        f"Holding Time   : {hours:.1f} hours\n"
        f"Time (UTC)     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION: Execute stop-loss sell at market**\n"
        f"```\n"
        f"Status         : Capital preserved\n"
        f"Next Action    : Wait for next BUY signal\n"
        f"Do NOT re-enter until next signal\n"
        f"```"
    )


def professional_daily_message(price, status, total, wr, score, active_trade):
    """Professional daily summary."""
    trade_info = "None"
    if active_trade:
        trade_info = f"Entry ${active_trade['entry']:.4f} | P&L {((price/active_trade['entry']-1)*100):+.2f}%"

    return (
        f"**AVAX QUANT BOT — DAILY SUMMARY**\n"
        f"```\n"
        f"Date           : {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"Current Price  : ${price:.4f}\n"
        f"Master Score   : {score:+.3f}\n"
        f"Signal Status  : {status}\n"
        f"Active Trade   : {trade_info}\n"
        f"```\n"
        f"**Performance Metrics**\n"
        f"```\n"
        f"Total Trades   : {total}\n"
        f"Win Rate       : {wr:.1f}%\n"
        f"```"
    )


def run_once():
    state = load_json(STATE_FILE, {'active_trade': None, 'history': [],
                                    'last_signal_ts': None, 'last_heartbeat': None,
                                    'dca_level': 0})

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

    # ---- Manage active trade ----
    if state['active_trade']:
        t = state['active_trade']
        entry = t['entry']
        tp_price = entry * (1 + TP_PCT)
        sl_price = entry * (1 - SL_PCT)
        hours = (now - pd.to_datetime(t['opened_at'], utc=True)).total_seconds() / 3600

        # Check DCA levels
        dca_level = state.get('dca_level', 0)
        dca2 = t.get('dca2') or entry * (1 - DCA_LEVEL_2_DROP)
        dca3 = t.get('dca3') or entry * (1 - DCA_LEVEL_3_DROP)

        if dca_level < 2 and low <= dca2:
            # Trigger DCA level 2
            new_avg = entry * 0.7 + dca2 * 0.3  # weighted avg (50/30)
            new_tp = new_avg * (1 + TP_PCT)
            send(professional_dca_message(2, price, dca2, new_avg, new_tp, "30%"))
            state['dca_level'] = 2
            t['dca2_hit_at'] = ts_iso
            print(f'[DCA] Level 2 triggered at ${dca2:.4f}')

        elif dca_level < 3 and low <= dca3:
            # Trigger DCA level 3
            send(professional_dca_message(3, price, dca3, dca3, dca3 * (1 + TP_PCT), "20%"))
            state['dca_level'] = 3
            print(f'[DCA] Level 3 triggered at ${dca3:.4f}')

        # Check TP
        elif high >= tp_price:
            profit_pct = TP_PCT * 100
            send(professional_tp_message(entry, tp_price, profit_pct, hours))
            state['history'].append({**t, 'exit': tp_price, 'type': 'TP',
                                     'profit_pct': profit_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0
            print(f'[TRADE] TP HIT +{profit_pct}%')

        # Check SL
        elif low <= sl_price:
            loss_pct = -SL_PCT * 100
            send(professional_sl_message(entry, sl_price, loss_pct, hours))
            state['history'].append({**t, 'exit': sl_price, 'type': 'SL',
                                     'profit_pct': loss_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0
            print(f'[TRADE] SL HIT {loss_pct}%')

        # Check max hold
        elif hours >= MAX_HOLD_H:
            pl = (price / entry - 1) * 100
            send(
                f"**AVAX/USDT — TIME EXIT**\n"
                f"```\n"
                f"Held           : {hours:.1f} hours (max {MAX_HOLD_H}h)\n"
                f"Entry          : ${entry:.4f}\n"
                f"Current        : ${price:.4f}\n"
                f"P&L            : {pl:+.2f}%\n"
                f"```\n"
                f"**ACTION: Close position at market**"
            )
            state['history'].append({**t, 'exit': price, 'type': 'TIME',
                                     'profit_pct': pl, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0

    # ---- New signal ----
    if not state['active_trade']:
        sd = compute_score(df, btc_up, fg, funding)
        print(f"[SCORE] master={sd['master']:+.4f}")

        if sd['master'] >= BUY_TH and state.get('last_signal_ts') != ts_iso:
            tp = price * (1 + TP_PCT)
            sl = price * (1 - SL_PCT)
            dca2 = price * (1 - DCA_LEVEL_2_DROP)
            dca3 = price * (1 - DCA_LEVEL_3_DROP)

            send(professional_buy_message(price, tp, sl, sd, dca2, dca3))

            state['active_trade'] = {
                'entry': price, 'tp': tp, 'sl': sl,
                'dca2': dca2, 'dca3': dca3,
                'opened_at': ts_iso, 'score': sd['master']
            }
            state['last_signal_ts'] = ts_iso
            state['dca_level'] = 0
            print(f'[SIGNAL] BUY @ ${price:.4f}')

    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

    # ---- Daily summary ----
    today = now.strftime('%Y-%m-%d')
    if state.get('last_heartbeat') != today:
        h = state['history']
        wins = sum(1 for x in h if x.get('profit_pct', 0) > 0)
        total = len([x for x in h if x.get('type') in ('TP', 'SL')])
        wr = (wins / total * 100) if total else 0
        status = 'ACTIVE — Trade in progress' if state['active_trade'] else 'WAITING — No signal'
        sd = compute_score(df, btc_up, fg, funding)

        send(professional_daily_message(price, status, total, wr, sd['master'], state['active_trade']))
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)


if __name__ == '__main__':
    run_once()
