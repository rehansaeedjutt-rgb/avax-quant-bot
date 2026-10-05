import os
import sys
import requests
from datetime import datetime, timezone

# Direct webhook test
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK', '')

# Agar env var nahi set, config file se read karo
if not WEBHOOK_URL:
    import json
    with open('C:/avax_quant_system/config/discord.json', 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)
    WEBHOOK_URL = cfg.get('webhook_url', '')

if not WEBHOOK_URL or 'PASTE' in WEBHOOK_URL:
    print('ERROR: Discord webhook not configured')
    sys.exit(1)

msg = (
    "**AVAX QUANT BOT — SYSTEM TEST**\n"
    "```\n"
    "Test Time    : " + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC') + "\n"
    "Status       : System operational\n"
    "Scanner      : Running every 15 minutes\n"
    "Strategy     : SMC + On-chain + BTC\n"
    "Win Rate     : 83.7% (backtested)\n"
    "```\n"
    "**This is a test message. Live signals will appear when score reaches 0.30+.**"
)

r = requests.post(WEBHOOK_URL, json={'content': msg}, timeout=10)
print(f'Status: {r.status_code}')
if r.status_code in (200, 204):
    print('Test message sent to Discord successfully')
else:
    print(f'Failed: {r.text[:200]}')
