import requests
import os
import time
import logging

logger = logging.getLogger(__name__)

def send_discord(msg: str) -> bool:
    """Sends message to Discord with 3 retries if network fails."""
    webhook = os.environ.get('DISCORD_WEBHOOK', '')
    if not webhook or 'PASTE' in webhook:
        logger.warning("[DISCORD] Webhook not set.")
        return False
        
    for attempt in range(3):
        try:
            r = requests.post(webhook, json={'content': msg}, timeout=10)
            if r.status_code in (200, 204):
                return True
            elif r.status_code == 429: # Rate limited
                logger.warning("[DISCORD] Rate limited. Waiting...")
                time.sleep(3)
        except Exception as e:
            logger.error(f"[DISCORD] Error (Attempt {attempt+1}): {e}")
            time.sleep(2)
            
    logger.error("[DISCORD] Failed to deliver message after 3 retries.")
    return False
