import os
import json
import requests
from datetime import datetime

CONFIG_DIR = 'C:/avax_quant_system/config'
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK', '')

def get_monthly_stats():
    coins = ['avax', 'link', 'sol', 'ada', 'sui', 'dot']
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit_pct = 0.0
    coin_breakdown = []

    for coin in coins:
        file_path = os.path.join(CONFIG_DIR, f'live_trades_{coin}.json')
        if not os.path.exists(file_path):
            continue
            
        with open(file_path, 'r') as f:
            history = json.load(f)
            
        # Filter trades for current month
        monthly_trades = [t for t in history if t.get('closed_at', '').startswith(current_month)]
        
        if not monthly_trades:
            continue
            
        wins = sum(1 for t in monthly_trades if t.get('profit_pct', 0) > 0)
        losses = len(monthly_trades) - wins
        profit = sum(t.get('profit_pct', 0) for t in monthly_trades)
        
        total_trades += len(monthly_trades)
        total_wins += wins
        total_losses += losses
        total_profit_pct += profit
        
        coin_breakdown.append({
            'name': coin.upper(),
            'trades': len(monthly_trades),
            'wins': wins,
            'profit': round(profit, 2)
        })

    return {
        'month': now.strftime('%B %Y'),
        'total_trades': total_trades,
        'total_wins': total_wins,
        'total_losses': total_losses,
        'total_profit': round(total_profit_pct, 2),
        'win_rate': round((total_wins / total_trades * 100), 1) if total_trades > 0 else 0,
        'breakdown': coin_breakdown
    }

def send_monthly_report():
    if not WEBHOOK_URL or 'PASTE' in WEBHOOK_URL:
        print("Webhook not set.")
        return
        
    stats = get_monthly_stats()
    
    if stats['total_trades'] == 0:
        print("No trades this month. Skipping report.")
        return

    # Create a beautiful Discord Embed
    embed = {
        "title": f"📊 MONTHLY PERFORMANCE REPORT — {stats['month']}",
        "color": 3447003, # Blue color
        "fields": [
            {
                "name": "Total Trades",
                "value": f"**{stats['total_trades']}**",
                "inline": True
            },
            {
                "name": "Win Rate",
                "value": f"**{stats['win_rate']}%** ({stats['total_wins']}W / {stats['total_losses']}L)",
                "inline": True
            },
            {
                "name": "Total Profit",
                "value": f"**+{stats['total_profit']}%**",
                "inline": True
            }
        ],
        "footer": {
            "text": "Institutional Quant Bot | Risk Managed"
        }
    }
    
    # Add coin breakdown
    breakdown_text = ""
    for c in stats['breakdown']:
        breakdown_text += f"**{c['name']}**: {c['trades']} trades | {c['wins']}W | **{c['profit']}%** profit\n"
        
    if breakdown_text:
        embed["fields"].append({
            "name": "📈 Coin Breakdown",
            "value": breakdown_text,
            "inline": False
        })

    payload = {"embeds": [embed]}
    
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code in (200, 204):
            print("✅ Monthly report sent successfully!")
        else:
            print(f"Failed: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    send_monthly_report()
