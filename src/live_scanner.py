"""
LIVE SIGNAL SCANNER v6.0
Changes from v5:
- Buy threshold: 0.30 -> 0.15
- Near-miss threshold: 0.20 -> 0.10
- Added AVAX/BTC ratio filter (weight 0.15)
- Added BTC dominance filter (weight +/-0.10)
- SMC weight reduced: 0.55 -> 0.45
- BTC weight increased: 0.20 (kept)
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


def fetch_avax_btc_ratio(ex):
    """Fetch AVAX/BTC ratio and check if above 20-EMA."""
    try:
        raw = ex.fetch_ohlcv('AVAX/BTC', TIMEFRAME, limit=100)
        if not raw or len(raw) < 25:
            return 0
        df = pd.DataFrame(raw, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        ema20 = df['c'].astype(float).ewm(span=20, adjust=False).mean()
        current = float(df['c'].iloc[-1])
        ema = float(ema20.iloc[-1])
        ratio_up = 1 if current > ema else 0
        print(f'[RATIO] AVAX/BTC = {current:.8f} | EMA20 = {ema:.8f} | Up = {ratio_up}')
        return ratio_up
    except Exception as e:
        print(f'[RATIO] Error: {e}')
        return 0


def fetch_btc_dominance():
    """Fetch BTC dominance from CoinGecko."""
    try:
        r = requests.get('https://api.coingecko.com/api/v3/global', timeout=10)
        dom = float(r.json()['data']['market_cap_percentage']['btc'])
        print(f'[DOM] BTC dominance = {dom:.2f}%')
        return dom
    except Exception as e:
        print(f'[DOM] Error: {e}')
        return 59.0


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
    btc_s = (btc_up * 2 - 1) * 0.20

    # AVAX/BTC ratio score
    ratio_score = 0.15 if ratio_up else -0.15

    # BTC dominance score
    if btc_dom > 60:
        dom_score = -0.10
    elif btc_dom < 57.8:
        dom_score = +0.10
    else:
        dom_score = 0.0

    master = float(np.clip(
        smc * 0.45 + onchain * 0.20 + btc_s + ratio_score + dom_score,
        -1, 1
    ))

    return {
        'master': master, 'smc': float(smc), 'onchain': float(onchain),
        'btc': float(btc_s), 'ratio': float(ratio_score),
        'dom': float(dom_score), 'fg': fg, 'funding': funding,
        'btc_dom': btc_dom, 'ratio_up': ratio_up
    }


def msg_buy(price, tp, sl, sd, dca2, dca3):
    return (
        f"**AVAX/USDT — LONG ENTRY SIGNAL**\n"
        f"```\n"
        f"Symbol       : AVAX/USDT\n"
        f"Timeframe    : 1 Hour\n"
        f"Signal Type  : BUY (Long)\n"
        f"Confidence   : {sd['master']*100:.1f}%\n"
        f"Time (UTC)   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION REQUIRED: Open LONG position on MEXC or OKX**\n"
        f"```\n"
        f"Entry Price  : ${price:.4f}\n"
        f"Take Profit  : ${tp:.4f}  (+{TP_PCT*100:.2f}%)\n"
        f"Stop Loss    : ${sl:.4f}  (-{SL_PCT*100:.2f}%)\n"
        f"```\n"
        f"**Position Sizing**\n"
        f"```\n"
        f"Initial Entry    : 50% at ${price:.4f}\n"
        f"DCA Level 2      : 30% at ${dca2:.4f} (-2.0%)\n"
        f"DCA Level 3      : 20% at ${dca3:.4f} (-4.0%)\n"
        f"```\n"
        f"**Signal Breakdown**\n"
        f"```\n"
        f"SMC Score      : {sd['smc']:+.3f} (weight 45%)\n"
        f"On-Chain Score : {sd['onchain']:+.3f} (weight 20%)\n"
        f"BTC Trend      : {sd['btc']:+.3f} (weight 20%)\n"
        f"AVAX/BTC Ratio : {sd['ratio']:+.3f} (weight 15%)\n"
        f"BTC Dominance  : {sd['dom']:+.3f} (weight +/-10%)\n"
        f"F&G            : {sd['fg']} | Funding: {sd['funding']:.6f}\n"
        f"BTC.D          : {sd['btc_dom']:.2f}%\n"
        f"```"
    )


def msg_dca(level, price, dca_price, new_avg, new_tp, add_pct):
    return (
        f"**AVAX/USDT — DCA LEVEL {level} TRIGGERED**\n"
        f"```\n"
        f"Current Price  : ${price:.4f}\n"
        f"DCA Trigger    : ${dca_price:.4f}\n"
        f"Time (UTC)     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**ACTION REQUIRED: Add {add_pct} of original capital**\n"
        f"```\n"
        f"New Average    : ${new_avg:.4f}\n"
        f"New Take Profit: ${new_tp:.4f} (+{TP_PCT*100:.2f}%)\n"
        f"```"
    )


def msg_tp(entry, exit_price, profit_pct, hours):
    return (
        f"**AVAX/USDT — TAKE PROFIT EXECUTED**\n"
        f"```\n"
        f"Position       : Closed (PROFIT)\n"
        f"Entry Price    : ${entry:.4f}\n"
        f"Exit Price     : ${exit_price:.4f}\n"
        f"Profit         : +{profit_pct:.2f}%\n"
        f"Holding Time   : {hours:.1f} hours\n"
        f"```\n"
        f"**ACTION: Sell entire position if not already done**"
    )


def msg_sl(entry, exit_price, loss_pct, hours):
    return (
        f"**AVAX/USDT — STOP LOSS EXECUTED**\n"
        f"```\n"
        f"Position       : Closed (LOSS)\n"
        f"Entry Price    : ${entry:.4f}\n"
        f"Exit Price     : ${exit_price:.4f}\n"
        f"Loss           : {loss_pct:.2f}%\n"
        f"Holding Time   : {hours:.1f} hours\n"
        f"```\n"
        f"**ACTION: Execute stop-loss sell at market**\n"
        f"Do NOT re-enter until next signal"
    )


def msg_hourly(price, score, status, active, sd):
    trade_info = "None"
    if active:
        trade_info = f"Entry ${active['entry']:.4f} | P&L {((price/active['entry']-1)*100):+.2f}%"
    return (
        f"**AVAX Scanner — Status Check**\n"
        f"```\n"
        f"Time         : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"Price        : ${price:.4f}\n"
        f"Master Score : {score:+.3f}\n"
        f"Threshold    : +{BUY_TH:.2f}\n"
        f"AVAX/BTC     : {'UP' if sd['ratio_up'] else 'DOWN'}\n"
        f"BTC.D        : {sd['btc_dom']:.2f}%\n"
        f"Status       : {status}\n"
        f"Active Trade : {trade_info}\n"
        f"```"
    )


def msg_near(price, score, distance, sd):
    return (
        f"**AVAX/USDT — WATCHING (Near BUY Threshold)**\n"
        f"```\n"
        f"Current Price  : ${price:.4f}\n"
        f"Master Score   : {score:+.3f}\n"
        f"Threshold      : +{BUY_TH:.2f}\n"
        f"Distance       : {distance:.3f}\n"
        f"AVAX/BTC       : {'UP' if sd['ratio_up'] else 'DOWN'}\n"
        f"Time (UTC)     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        f"```\n"
        f"**Signal may fire soon. Get ready on MEXC/OKX.**"
    )


def msg_daily(price, status, total, wr, score, active, sd):
    trade_info = "None"
    if active:
        trade_info = f"Entry ${active['entry']:.4f} | P&L {((price/active['entry']-1)*100):+.2f}%"
    return (
        f"**AVAX QUANT BOT — DAILY SUMMARY**\n"
        f"```\n"
        f"Date           : {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"Current Price  : ${price:.4f}\n"
        f"Master Score   : {score:+.3f}\n"
        f"Threshold      : +{BUY_TH:.2f}\n"
        f"AVAX/BTC       : {'UP' if sd['ratio_up'] else 'DOWN'}\n"
        f"BTC.D          : {sd['btc_dom']:.2f}%\n"
        f"Signal Status  : {status}\n"
        f"Active Trade   : {trade_info}\n"
        f"```\n"
        f"**Performance**\n"
        f"```\n"
        f"Total Trades   : {total}\n"
        f"Win Rate       : {wr:.1f}%\n"
        f"```"
    )


def run_once():
    state = load_json(STATE_FILE, {
        'active_trade': None, 'history': [], 'last_signal_ts': None,
        'last_heartbeat': None, 'last_hourly': None, 'last_near': None,
        'last_score': None, 'dca_level': 0,
    })

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

    print(f'[PRICE] ${price:.4f}')
    print(f'[BTC] {btc_up} | Ratio: {ratio_up} | Dom: {btc_dom:.2f}%')
    print(f'[F&G] {fg} | Funding: {funding:.6f}')

    sd = compute_score(df, btc_up, fg, funding, ratio_up, btc_dom)
    print(f"[SCORE] master={sd['master']:+.4f} smc={sd['smc']:+.4f} "
          f"onchain={sd['onchain']:+.4f} btc={sd['btc']:+.4f} "
          f"ratio={sd['ratio']:+.4f} dom={sd['dom']:+.4f}")

    # Manage active trade
    if state['active_trade']:
        t = state['active_trade']
        entry = t['entry']
        tp_price = entry * (1 + TP_PCT)
        sl_price = entry * (1 - SL_PCT)
        hours = (now - pd.to_datetime(t['opened_at'], utc=True)).total_seconds() / 3600
        dca_level = state.get('dca_level', 0)
        dca2 = t.get('dca2') or entry * (1 - DCA_LEVEL_2_DROP)
        dca3 = t.get('dca3') or entry * (1 - DCA_LEVEL_3_DROP)

        if dca_level < 2 and low <= dca2:
            new_avg = entry * 0.7 + dca2 * 0.3
            new_tp = new_avg * (1 + TP_PCT)
            send(msg_dca(2, price, dca2, new_avg, new_tp, "30%"))
            state['dca_level'] = 2
            t['dca2_hit_at'] = ts_iso
        elif dca_level < 3 and low <= dca3:
            send(msg_dca(3, price, dca3, dca3, dca3 * (1 + TP_PCT), "20%"))
            state['dca_level'] = 3
        elif high >= tp_price:
            profit_pct = TP_PCT * 100
            send(msg_tp(entry, tp_price, profit_pct, hours))
            state['history'].append({**t, 'exit': tp_price, 'type': 'TP',
                                     'profit_pct': profit_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0
        elif low <= sl_price:
            loss_pct = -SL_PCT * 100
            send(msg_sl(entry, sl_price, loss_pct, hours))
            state['history'].append({**t, 'exit': sl_price, 'type': 'SL',
                                     'profit_pct': loss_pct, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0
        elif hours >= MAX_HOLD_H:
            pl = (price / entry - 1) * 100
            send(f"**AVAX/USDT — TIME EXIT**\n```\nHeld: {hours:.1f}h\nP&L: {pl:+.2f}%\n```")
            state['history'].append({**t, 'exit': price, 'type': 'TIME',
                                     'profit_pct': pl, 'closed_at': ts_iso})
            state['active_trade'] = None
            state['dca_level'] = 0

    # New signal
    elif sd['master'] >= BUY_TH and state.get('last_signal_ts') != ts_iso:
        tp = price * (1 + TP_PCT)
        sl = price * (1 - SL_PCT)
        dca2 = price * (1 - DCA_LEVEL_2_DROP)
        dca3 = price * (1 - DCA_LEVEL_3_DROP)
        send(msg_buy(price, tp, sl, sd, dca2, dca3))
        state['active_trade'] = {
            'entry': price, 'tp': tp, 'sl': sl,
            'dca2': dca2, 'dca3': dca3,
            'opened_at': ts_iso, 'score': sd['master']
        }
        state['last_signal_ts'] = ts_iso
        state['dca_level'] = 0

    # Near-miss
    elif sd['master'] >= NEAR_TH and state.get('last_near') != hour_key:
        send(msg_near(price, sd['master'], BUY_TH - sd['master'], sd))
        state['last_near'] = hour_key

    # Hourly heartbeat
    elif state.get('last_hourly') != hour_key:
        status = 'Active trade' if state['active_trade'] else 'Waiting for signal'
        send(msg_hourly(price, sd['master'], status, state['active_trade'], sd))
        state['last_hourly'] = hour_key

    # Daily summary
    if state.get('last_heartbeat') != today:
        h = state['history']
        wins = sum(1 for x in h if x.get('profit_pct', 0) > 0)
        total = len([x for x in h if x.get('type') in ('TP', 'SL')])
        wr = (wins / total * 100) if total else 0
        status = 'ACTIVE' if state['active_trade'] else 'WAITING'
        send(msg_daily(price, status, total, wr, sd['master'], state['active_trade'], sd))
        state['last_heartbeat'] = today

    state['last_score'] = sd['master']
    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])


if __name__ == '__main__':
    run_once()
