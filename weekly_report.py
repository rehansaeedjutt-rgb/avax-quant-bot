import os
import json
from datetime import datetime, timezone
from collections import defaultdict

ROOT = 'C:/avax_quant_system'
STATE = os.path.join(ROOT, 'config', 'grid_state.json')
TRADES = os.path.join(ROOT, 'config', 'grid_trades.json')


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


state = load(STATE, {})
trades = load(TRADES, [])

print('=' * 70)
print('     AVAX GRID BOT — 1 WEEK REPORT')
print('=' * 70)
print()

# ---- Current state ----
print('CURRENT STATE')
print('-' * 70)
print(f"  Cash:            ${state.get('cash', 0):.2f}")
print(f"  Anchor:          ${state.get('anchor', 0):.4f}")
print(f"  Open positions:  {len(state.get('positions', []))}")
print(f"  Total closed:    {len(trades)}")
print(f"  Last run:        {state.get('last_run', 'N/A')}")
print()

# ---- Open positions ----
positions = state.get('positions', [])
if positions:
    print('OPEN POSITIONS (currently held)')
    print('-' * 70)
    print(f"  {'Buy Price':>12} {'Units':>10} {'Cost':>10} {'Buy Time':>24}")
    total_cost = 0
    for p in positions:
        cost = p['buy_price'] * p['units']
        total_cost += cost
        print(f"  ${p['buy_price']:>11.4f} {p['units']:>10.4f} ${cost:>9.2f} {p['buy_time'][:19]:>24}")
    print(f"  {'TOTAL':>12} {'':>10} ${total_cost:>9.2f}")
    print()

# ---- Closed trades analysis ----
if not trades:
    print('CLOSED TRADES: 0 (koi trade close nahi hui)')
    print()
    print('Yeh normal hai agar:')
    print('  - Anchor har hafte upar shift hota raha')
    print('  - Price $10.80 tak nahi giri')
    print('  - Ya jo positions open hui, woh abhi tak target pe nahi pahunchi')
else:
    sells = [t for t in trades if t.get('type') == 'SELL']
    forces = [t for t in trades if t.get('type') == 'FORCE_EXIT']

    print('CLOSED TRADES')
    print('-' * 70)
    print(f"  Total closes:    {len(trades)}")
    print(f"    SELL (profit): {len(sells)}")
    print(f"    FORCE EXIT:    {len(forces)}")
    print()

    if sells:
        wins = [s for s in sells if s['profit'] > 0]
        losses = [s for s in sells if s['profit'] <= 0]
        total_profit = sum(s['profit'] for s in sells)
        avg_profit = total_profit / len(sells)
        wr = len(wins) / len(sells) * 100

        hold_hours = [s.get('held_hours', 0) for s in sells]
        avg_hold = sum(hold_hours) / len(hold_hours)

        print('  SELL DETAILS:')
        print(f"    Wins:          {len(wins)}")
        print(f"    Losses:        {len(losses)}")
        print(f"    Win Rate:      {wr:.2f}%")
        print(f"    Total profit:  ${total_profit:.4f}")
        print(f"    Avg profit:    ${avg_profit:.4f}")
        print(f"    Avg hold time: {avg_hold:.1f} hours ({avg_hold/24:.1f} days)")
        print()

        # Trade by trade
        print('  ALL SELLS (chronological):')
        print(f"    {'#':>3} {'Buy':>10} {'Sell':>10} {'Profit':>10} {'Held':>8}")
        for i, s in enumerate(sells, 1):
            print(f"    {i:>3} ${s['buy_price']:>9.4f} ${s['sell_price']:>9.4f} "
                  f"${s['profit']:>9.4f} {s.get('held_hours', 0):>6.1f}h")

    if forces:
        print()
        print('  FORCE EXITS (breakeven):')
        for i, f in enumerate(forces, 1):
            print(f"    {i}. Buy ${f['buy_price']:.4f} → ${f['sell_price']:.4f} "
                  f"(held {f.get('held_hours', 0):.1f}h)")

# ---- Daily summary ----
if trades:
    print()
    print('DAILY BREAKDOWN')
    print('-' * 70)
    by_date = defaultdict(lambda: {'sells': 0, 'profit': 0.0})
    for s in trades:
        if s.get('type') == 'SELL':
            date = s['sell_time'][:10]
            by_date[date]['sells'] += 1
            by_date[date]['profit'] += s['profit']

    for date in sorted(by_date.keys()):
        d = by_date[date]
        print(f"  {date}: {d['sells']:>3} sells | profit ${d['profit']:>8.4f}")

# ---- Analysis ----
print()
print('=' * 70)
print('ANALYSIS')
print('=' * 70)

if not trades and not positions:
    print('  Koi activity nahi hui is hafte. Possible reasons:')
    print('  1. Price ne 1% dip nahi kiya (uptrend week)')
    print('  2. Bot band tha (Actions disabled)')
    print('  3. Bug tha')
    print()
    print('  Recommendation: Actions logs check karein.')

elif not trades and positions:
    print(f'  {len(positions)} position(s) open hain, koi close nahi hui.')
    print('  Matlab: Kuch buys hui, lekin sell target abhi hit nahi hua.')
    print()
    print('  Recommendation: Wait karein. Ya spacing kam karein.')

elif trades:
    print(f'  {len(trades)} closes huin.')
    if sells:
        wr = len([s for s in sells if s['profit'] > 0]) / len(sells) * 100
        print(f'  Win Rate: {wr:.1f}%')
        print(f'  Total profit: ${sum(s["profit"] for s in sells):.4f}')
        print()
        print(f'  Backtest mein expected tha:')
        print(f'    WR: 97.1%')
        print(f'    Trades/month: 85.88')
        print(f'    Monthly profit: ~$6-8 per $1000')

print()
print('=' * 70)
