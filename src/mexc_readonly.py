import os
import sys
import json
import ccxt

ROOT = 'C:/avax_quant_system'
CONFIG = f'{ROOT}/config/mexc.json'


def load_cfg():
    if not os.path.exists(CONFIG):
        return None
    with open(CONFIG, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def connect_readonly():
    cfg = load_cfg()
    if not cfg or 'api_key' not in cfg or cfg['api_key'].startswith('PASTE'):
        print('[MEXC] Config missing or not filled in. Skipping read-only connect.')
        print('[MEXC] Edit config/mexc.json with your real key and secret.')
        return None
    ex = ccxt.mexc({
        'apiKey': cfg['api_key'],
        'secret': cfg['secret'],
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
    })
    print('[MEXC] Connected (read-only)')
    return ex


def show_balance(ex):
    try:
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {})
        print(f'[MEXC] USDT free: {usdt.get("free", 0)} | used: {usdt.get("used", 0)} | total: {usdt.get("total", 0)}')
        avax = bal.get('AVAX', {})
        if avax:
            print(f'[MEXC] AVAX free: {avax.get("free", 0)} | total: {avax.get("total", 0)}')
    except Exception as e:
        print(f'[MEXC] Balance fetch error: {e}')


def show_market(ex):
    try:
        t = ex.fetch_ticker('AVAX/USDT')
        print(f'[MEXC] AVAX/USDT last: {t.get("last")} | bid: {t.get("bid")} | ask: {t.get("ask")}')
    except Exception as e:
        print(f'[MEXC] Ticker error: {e}')


if __name__ == '__main__':
    ex = connect_readonly()
    if ex:
        show_balance(ex)
        show_market(ex)
    else:
        print('\nSetup steps:')
        print('1. Login to MEXC')
        print('2. Go to API Management')
        print('3. Create API key with ONLY "Read" permission (no trade, no withdraw)')
        print('4. Copy key and secret into config/mexc.json')
