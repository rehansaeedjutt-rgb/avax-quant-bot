import json
import sys
sys.path.insert(0, 'C:/avax_quant_system')
from discord_bot.notify import send

with open('C:/avax_quant_system/config/locked_strategy.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = ['**AVAX Quant - Locked Strategy**', '```']
for tf, r in data.items():
    lines.append(
        f"{tf:4s} | Ret {r['Return [%]']:6.2f}% | "
        f"WR {r['Win Rate [%]']:6.2f}% | "
        f"PF {r['Profit Factor']:5.2f} | "
        f"DD {r['Max Drawdown [%]']:6.2f}% | "
        f"Trades {r['# Trades']}"
    )
lines.append('```')
lines.append('*Strategy frozen. Moving to live monitoring.*')

ok = send('\n'.join(lines))
print('Sent' if ok else 'Failed to send')
