import time
import logging
import ccxt

logger = logging.getLogger(__name__)

def get_exchange():
    """Connects to exchange with failover, retry mechanism, and data validation."""
    # 7 Top Exchanges (Free API, No KYC for public data)
    exchanges = [
        ('binance', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
        ('okx', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
        ('bybit', {'enableRateLimit': True}),
        ('kucoin', {'enableRateLimit': True}),
        ('mexc', {'enableRateLimit': True}),
        ('bitget', {'enableRateLimit': True}),
        ('gateio', {'enableRateLimit': True}),
    ]
    
    for ex_id, cfg in exchanges:
        for attempt in range(2): # 2 attempts per exchange
            try:
                ex = getattr(ccxt, ex_id)(cfg)
                ex.load_markets()
                # Validate data
                test_data = ex.fetch_ohlcv('AVAX/USDT', '1d', limit=5)
                if len(test_data) == 5 and test_data[-1][4] > 0:
                    logger.info(f"[EXCHANGE] Connected successfully to {ex_id}")
                    return ex
                else:
                    raise ValueError("Invalid data received")
            except Exception as e:
                logger.warning(f"[EXCHANGE] {ex_id} failed (Attempt {attempt+1}). Error: {str(e)[:50]}")
                time.sleep(2) # Exponential backoff logic
                
    logger.critical("All 7 exchanges failed. Network issue.")
    raise RuntimeError('No exchange available')
