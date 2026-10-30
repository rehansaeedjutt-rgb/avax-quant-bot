import os
import sys
import json
import logging
from datetime import datetime

# ==============================================================================
# FIX: Dynamic Path Resolution (Works on Windows & Linux/GitHub)
# ==============================================================================
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# Ab hum src.core ko import kar sakte hain
from src.core.exchange_handler import get_exchange
from src.core.risk_manager import process_coin

# Setup Professional Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

SYMBOLS_FILE = os.path.join(ROOT_DIR, 'config', 'symbols.json')

def main():
    logger.info("========================================")
    logger.info("🚀 STARTING MULTI-COIN TRADING ENGINE 🚀")
    logger.info("========================================")
    
    try:
        with open(SYMBOLS_FILE, 'r') as f:
            symbols = json.load(f)
    except Exception as e:
        logger.critical(f"Could not load symbols.json: {e}")
        return

    try:
        ex = get_exchange()
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")
        return

    for name, cfg in symbols.items():
        try:
            logger.info(f"--- Processing {name} ---")
            process_coin(ex, name, cfg)
        except Exception as e:
            logger.error(f"[{name}] Error during processing: {e}")
            continue
            
    logger.info("========================================")
    logger.info("✅ RUN COMPLETE")
    logger.info("========================================")

if __name__ == '__main__':
    main()
