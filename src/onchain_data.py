"""
On-chain data fetcher for AVAX.
100% FREE — no API keys required.
"""
import os
import json
import requests
from datetime import datetime, timezone

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data', 'onchain')
os.makedirs(DATA_DIR, exist_ok=True)
TIMEOUT = 20


def fetch_fear_greed(limit=2000):
    url = f'https://api.alternative.me/fng/?limit={limit}&format=json'
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()['data']


def fetch_funding_rates(symbol='AVAXUSDT', limit=1000):
    url = 'https://fapi.binance.com/fapi/v1/fundingRate'
    r = requests.get(url, params={'symbol': symbol, 'limit': limit}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_long_short_ratio(symbol='AVAXUSDT', period='1h', limit=500):
    url = 'https://fapi.binance.com/futures/data/topLongShortAccountRatio'
    r = requests.get(url, params={'symbol': symbol, 'period': period, 'limit': limit}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_open_interest(symbol='AVAXUSDT', period='1h', limit=500):
    url = 'https://fapi.binance.com/futures/data/openInterestHist'
    r = requests.get(url, params={'symbol': symbol, 'period': period, 'limit': limit}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_avalanche_tvl():
    url = 'https://api.llama.fi/v2/historicalChainTvl/Avalanche'
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_avax_market_chart(days=730):
    url = 'https://api.coingecko.com/api/v3/coins/avalanche-2/market_chart'
    r = requests.get(url, params={'vs_currency': 'usd', 'days': days, 'interval': 'daily'}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def save(name, data):
    path = f'{DATA_DIR}/{name}.json'
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'  Saved: {path} ({len(data)} records)')


if __name__ == '__main__':
    print('=' * 70)
    print('ON-CHAIN DATA FETCHER — 100% FREE')
    print('=' * 70)

    try:
        print('\n[1/6] Fear & Greed Index...')
        save('fear_greed', fetch_fear_greed())
    except Exception as e:
        print(f'  Error: {e}')

    try:
        print('\n[2/6] Funding Rates...')
        save('funding_rates', fetch_funding_rates())
    except Exception as e:
        print(f'  Error: {e}')

    try:
        print('\n[3/6] Long/Short Ratio...')
        save('long_short_ratio', fetch_long_short_ratio())
    except Exception as e:
        print(f'  Error: {e}')

    try:
        print('\n[4/6] Open Interest...')
        save('open_interest', fetch_open_interest())
    except Exception as e:
        print(f'  Error: {e}')

    try:
        print('\n[5/6] Avalanche TVL...')
        save('avalanche_tvl', fetch_avalanche_tvl())
    except Exception as e:
        print(f'  Error: {e}')

    try:
        print('\n[6/6] AVAX Market Chart...')
        save('avax_market', fetch_avax_market_chart())
    except Exception as e:
        print(f'  Error: {e}')

    print('\n' + '=' * 70)
    print(f'All data saved in: {DATA_DIR}')
    print('=' * 70)
