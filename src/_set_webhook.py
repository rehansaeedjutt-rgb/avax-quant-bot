import json
cfg = {
    "webhook_url": "YOUR_URL_HERE",
    "channel_name": "avax-signals",
    "notify_on": ["signal", "tp_hit", "sl_hit", "daily_summary"]
}
with open("C:/avax_quant_system/config/discord.json", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
print("Config written")
