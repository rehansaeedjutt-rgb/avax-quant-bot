import os
import json
import requests
from datetime import datetime, timezone

ROOT = 'C:/avax_quant_system'
CONFIG_PATH = f'{ROOT}/config/discord.json'


def load_webhook():
    if not os.path.exists(CONFIG_PATH):
        print('[DISCORD] Config file not found')
        return None
    with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)
    url = cfg.get('webhook_url', '')
    if not url or 'PASTE' in url:
        print('[DISCORD] Webhook URL not set in config/discord.json')
        return None
    return url


def send(content):
    url = load_webhook()
    if not url:
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
        if r.status_code in (200, 204):
            print('[DISCORD] Sent OK')
            return True
        print(f'[DISCORD] Failed: {r.status_code} {r.text[:200]}')
        return False
    except Exception as e:
        print(f'[DISCORD] Error: {e}')
        return False


def notify_signal(symbol, timeframe, action, price, tp, sl, strategy_name, extra=None):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = [
        f'**{action}** | `{symbol}` | `{timeframe}`',
        f'Strategy: **{strategy_name}**',
        f'Price: `{price:.4f}`',
        f'TP: `{tp:.4f}` ({((tp / price - 1) * 100):.2f}%)',
        f'SL: `{sl:.4f}` ({((sl / price - 1) * 100):.2f}%)',
        f'Time: {ts}',
    ]
    if extra:
        lines.append(f'Extra: {extra}')
    return send('\n'.join(lines))


def notify_backtest_summary(results_dict):
    lines = ['**Backtest Summary**']
    for tf, r in results_dict.items():
        lines.append(
            f'`{tf}` | Ret {r["Return [%]"]:.2f}% | WR {r["Win Rate [%]"]:.2f}% | '
            f'PF {r["Profit Factor"]:.2f} | Trades {r["# Trades"]}'
        )
    return send('\n'.join(lines))


if __name__ == '__main__':
    send('Test message from AVAX quant system')
