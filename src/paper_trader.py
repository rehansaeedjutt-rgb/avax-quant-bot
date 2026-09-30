import os
import sys
import json
from datetime import datetime, timezone

import ccxt
import pandas as pd

sys.path.insert(0, 'C:/avax_quant_system')
from discord_bot.notify import send

ROOT = 'C:/avax_quant_system'
STATE_FILE = f'{ROOT}/config/paper_state.json'
TRADES_FILE = f'{ROOT}/config/paper_trades.json'
SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1h'

TP_PCT = 0.007
SL_PCT = 0.025
START_BALANCE = 1000.0
RISK_PER_TRADE = 0.02


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def fetch_price():
    ex = ccxt.binance({'enableRateLimit': True})
    t = ex.fetch_ticker(SYMBOL)
    return float(t['last'])


def open_paper_trade(entry_price, balance):
    sl_price = entry_price * (1 - SL_PCT)
    tp_price = entry_price * (1 + TP_PCT)
    risk_amount = balance * RISK_PER_TRADE
    risk_per_unit = entry_price - sl_price
    size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
    return {
        'entry': entry_price,
        'tp': tp_price,
        'sl': sl_price,
        'size': round(size, 4),
        'opened_at': datetime.now(timezone.utc).isoformat(),
    }


def close_trade(trade, exit_price, reason, state):
    pnl = (exit_price - trade['entry']) * trade['size']
    state['balance'] += pnl
    state['history'].append({
        **trade,
        'exit': exit_price,
        'reason': reason,
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'pnl': round(pnl, 4),
    })
    return pnl


def check_open_trade(state, price):
    t = state.get('open_trade')
    if not t:
        return
    if price >= t['tp']:
        pnl = close_trade(t, t['tp'], 'TP', state)
        send(f"**PAPER TP HIT** | AVAX entry `{t['entry']:.4f}` -> `{t['tp']:.4f}` | "
             f"P&L `+${pnl:.2f}` | Balance `${state['balance']:.2f}`")
        state['open_trade'] = None
    elif price <= t['sl']:
        pnl = close_trade(t, t['sl'], 'SL', state)
        send(f"**PAPER SL HIT** | AVAX entry `{t['entry']:.4f}` -> `{t['sl']:.4f}` | "
             f"P&L `${pnl:.2f}` | Balance `${state['balance']:.2f}`")
        state['open_trade'] = None


def try_open_trade(state, signal_fired, price):
    if state.get('open_trade'):
        return
    if not signal_fired:
        return
    trade = open_paper_trade(price, state['balance'])
    state['open_trade'] = trade
    send(f"**PAPER BUY** | AVAX entry `{trade['entry']:.4f}` | "
         f"TP `{trade['tp']:.4f}` | SL `{trade['sl']:.4f}` | "
         f"Size `{trade['size']}` | Balance `${state['balance']:.2f}`")


def summary(state):
    hist = state.get('history', [])
    wins = sum(1 for h in hist if h['pnl'] > 0)
    losses = sum(1 for h in hist if h['pnl'] <= 0)
    total = wins + losses
    wr = (wins / total * 100) if total else 0.0
    return (
        f"**Paper Trading Summary**\n"
        f"Balance: `${state['balance']:.2f}` (start `${START_BALANCE}`)\n"
        f"Trades: {total} | Wins: {wins} | Losses: {losses} | WR: `{wr:.2f}%`\n"
        f"Open: `{state.get('open_trade')}`"
    )


def update(signal_fired=False):
    state = load_json(STATE_FILE, {'balance': START_BALANCE, 'open_trade': None, 'history': []})
    price = fetch_price()
    print(f'[PAPER] price={price:.4f} | balance=${state["balance"]:.2f} | signal={signal_fired}')
    check_open_trade(state, price)
    try_open_trade(state, signal_fired, price)
    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state.get('history', []))
    return state


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'summary':
        state = load_json(STATE_FILE, {'balance': START_BALANCE, 'open_trade': None, 'history': []})
        msg = summary(state)
        print(msg)
        send(msg)
    else:
        fired = len(sys.argv) > 1 and sys.argv[1] == 'signal'
        update(signal_fired=fired)
