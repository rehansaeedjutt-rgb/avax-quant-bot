"""
MASTER SIGNAL ENGINE v3 — correct JSON parsing.
Data sources confirmed:
- Fear & Greed: timestamp (seconds), value
- Funding: fundingTime (ms), fundingRate
"""
import os
import json
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
ONCHAIN_DIR = os.path.join(DATA_DIR, 'onchain')


def load_ohlcv(tf='1h'):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}_MERGED.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    for c in ['open','high','low','close','volume']:
        df[c] = df[c].astype(float)
    return df


def load_btc():
    try:
        df = pd.read_csv(f'{DATA_DIR}/BTC_USDT_1h.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['btc_up'] = (df['close'] > df['ema50']).astype(int)
        return df[['btc_up']]
    except Exception as e:
        print(f'BTC load failed: {e}')
        return None


def parse_fear_greed():
    path = f'{ONCHAIN_DIR}/fear_greed.json'
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    rows = []
    for d in data:
        ts = int(d['timestamp'])
        if ts < 1e12:
            ts *= 1000
        rows.append({
            'date': pd.to_datetime(ts, unit='ms'),
            'fg': float(d['value']),
        })
    df = pd.DataFrame(rows).set_index('date').sort_index()
    df = df[~df.index.duplicated(keep='last')]
    print(f'  F&G: {len(df)} rows | {df.index[0]} -> {df.index[-1]}')
    return df


def parse_funding():
    path = f'{ONCHAIN_DIR}/funding_rates.json'
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    rows = []
    for d in data:
        ts = int(d['fundingTime'])
        rows.append({
            'date': pd.to_datetime(ts, unit='ms'),
            'funding': float(d['fundingRate']),
        })
    df = pd.DataFrame(rows).set_index('date').sort_index()
    df = df[~df.index.duplicated(keep='last')]
    print(f'  Funding: {len(df)} rows | {df.index[0]} -> {df.index[-1]}')
    return df


def compute_smc(df):
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)

    print('  FVG...')
    fvg = pyvsmc.detect_fvg(high=high, low=low, close=close)
    print('  Structure...')
    st = pyvsmc.detect_structure(high=high, low=low, close=close)
    print('  Order Blocks...')
    ob = pyvsmc.detect_order_blocks(open_, high, low, close)
    print('  Liquidity...')
    liq = pyvsmc.detect_liquidity(high=high, low=low, close=close)
    print('  Zones...')
    zn = pyvsmc.detect_zones(high=high, low=low, close=close)

    smc = pd.DataFrame(index=df.index)
    smc['fvg_bull'] = fvg.bullish & ~fvg.mitigated
    smc['fvg_bear'] = fvg.bearish & ~fvg.mitigated
    smc['bos_bull'] = st.bos_bullish
    smc['bos_bear'] = st.bos_bearish
    smc['choch_bull'] = st.choch_bullish
    smc['choch_bear'] = st.choch_bearish
    smc['trend'] = st.trend
    smc['ob_bull'] = ob.bullish_ob
    smc['ob_bear'] = ob.bearish_ob
    smc['sweep_low'] = liq.sweep_low
    smc['sweep_high'] = liq.sweep_high
    smc['discount'] = zn.discount
    smc['premium'] = zn.premium
    return smc


def smc_score(smc):
    s = np.zeros(len(smc))
    s += smc['trend'].to_numpy() * 0.20
    s += smc['bos_bull'].to_numpy() * 0.15
    s -= smc['bos_bear'].to_numpy() * 0.15
    s += smc['choch_bull'].to_numpy() * 0.25
    s -= smc['choch_bear'].to_numpy() * 0.25
    s += smc['ob_bull'].to_numpy() * 0.20
    s -= smc['ob_bear'].to_numpy() * 0.20
    s += smc['fvg_bull'].to_numpy() * 0.15
    s -= smc['fvg_bear'].to_numpy() * 0.15
    s += smc['sweep_low'].to_numpy() * 0.10
    s -= smc['sweep_high'].to_numpy() * 0.10
    s += smc['discount'].to_numpy() * 0.10
    s -= smc['premium'].to_numpy() * 0.10
    return np.clip(s, -1, 1)


def build_master():
    print('=' * 70)
    print('MASTER SIGNAL ENGINE v3')
    print('=' * 70)

    df = load_ohlcv('1h')
    print(f'\nAVAX 1h: {len(df):,} candles')

    btc = load_btc()
    print(f'BTC: {len(btc) if btc is not None else 0:,} candles')

    print('\nLoading on-chain...')
    fg = parse_fear_greed()
    funding = parse_funding()

    print('\nComputing SMC...')
    smc = compute_smc(df)
    s_smc = smc_score(smc)
    print(f'  SMC: mean={s_smc.mean():.4f} std={s_smc.std():.4f}')

    # On-chain combined
    s_oc = pd.Series(0.0, index=df.index)
    if fg is not None:
        fg_aligned = fg['fg'].reindex(df.index, method='ffill').fillna(50)
        s_oc += ((50 - fg_aligned) / 50).clip(-1, 1) * 0.20
        print(f'  F&G aligned: {fg_aligned.notna().sum()} candles')
    if funding is not None:
        fr_aligned = funding['funding'].reindex(df.index, method='ffill').fillna(0)
        s_oc += (-fr_aligned * 1000).clip(-1, 1) * 0.15
        print(f'  Funding aligned: {fr_aligned.notna().sum()} candles')

    # BTC
    s_btc = pd.Series(0.0, index=df.index)
    if btc is not None:
        bu = btc['btc_up'].reindex(df.index, method='ffill').fillna(0)
        s_btc = (bu * 2 - 1) * 0.15

    master = s_smc * 0.55 + s_oc.to_numpy() * 0.25 + s_btc.to_numpy() * 0.20
    master = np.clip(master, -1, 1)

    out = pd.DataFrame({
        'time': df.index,
        'close': df['close'].values,
        'smc': s_smc,
        'onchain': s_oc.values,
        'btc': s_btc.values,
        'master': master,
    })
    out.to_csv(f'{DATA_DIR}/avax_master_score.csv', index=False)

    print('\n' + '=' * 70)
    print('MASTER SCORE STATS')
    print('=' * 70)
    print(f'Mean:  {master.mean():.4f}')
    print(f'Std:   {master.std():.4f}')
    print(f'Min:   {master.min():.4f}')
    print(f'Max:   {master.max():.4f}')
    print(f'\nSignal Counts:')
    print(f'  Strong BUY (>= +0.5): {(master >= 0.5).sum():>6}')
    print(f'  BUY        (>= +0.3): {(master >= 0.3).sum():>6}')
    print(f'  Weak BUY   (>= +0.1): {(master >= 0.1).sum():>6}')
    print(f'  SELL       (<= -0.3): {(master <= -0.3).sum():>6}')
    print(f'  Strong SELL(<= -0.5): {(master <= -0.5).sum():>6}')
    print(f'\nSaved: {DATA_DIR}/avax_master_score.csv')


if __name__ == '__main__':
    build_master()
