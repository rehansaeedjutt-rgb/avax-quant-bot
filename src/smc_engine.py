"""
SMC Signal Engine — inspect pyvsmc result objects first.
"""
import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')


def load_data(tf='1h'):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}_MERGED.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    for c in ['open','high','low','close','volume']:
        df[c] = df[c].astype(float)
    return df


def inspect_result(res, name):
    """Print all fields of a result object."""
    print(f'\n{"="*70}')
    print(f'{name} RESULT')
    print(f'{"="*70}')
    print(f'Type: {type(res).__name__}')
    for attr in sorted(dir(res)):
        if attr.startswith('_'):
            continue
        try:
            v = getattr(res, attr)
            if callable(v):
                continue
            if isinstance(v, (list, tuple, np.ndarray, pd.Series)):
                arr = np.asarray(v)
                if arr.dtype == bool:
                    print(f'  {attr:25s}: bool array | sum={int(arr.sum()):>5} | len={len(arr)}')
                elif arr.dtype in [np.float64, np.float32, np.int64, np.int32]:
                    print(f'  {attr:25s}: numeric | min={arr.min():.4f} max={arr.max():.4f} len={len(arr)}')
                else:
                    print(f'  {attr:25s}: {arr.dtype} len={len(arr)}')
            elif v is None:
                print(f'  {attr:25s}: None')
            else:
                s = str(v)[:60]
                print(f'  {attr:25s}: {type(v).__name__} = {s}')
        except Exception as e:
            print(f'  {attr:25s}: ERROR {e}')


if __name__ == '__main__':
    print('=' * 70)
    print('LOADING 1h DATA')
    print('=' * 70)
    df = load_data('1h')
    print(f'Candles: {len(df):,}')
    print(f'Range: {df.index[0]} -> {df.index[-1]}')

    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)

    print('\n' + '=' * 70)
    print('RUNNING DETECTORS')
    print('=' * 70)

    # --- FVG ---
    try:
        fvg = pyvsmc.detect_fvg(high=high, low=low, close=close, compute_mitigation=True)
        inspect_result(fvg, 'FVG')
    except Exception as e:
        print(f'FVG ERROR: {e}')

    # --- Swings ---
    try:
        swings = pyvsmc.detect_swings(high=high, low=low)
        inspect_result(swings, 'SWINGS')
    except Exception as e:
        print(f'SWINGS ERROR: {e}')

    # --- Structure ---
    try:
        struct = pyvsmc.detect_structure(high=high, low=low, close=close)
        inspect_result(struct, 'STRUCTURE')
    except Exception as e:
        print(f'STRUCTURE ERROR: {e}')

    # --- Order Blocks ---
    try:
        ob = pyvsmc.detect_order_blocks(open_, high, low, close)
        inspect_result(ob, 'ORDER BLOCKS')
    except Exception as e:
        print(f'OB ERROR: {e}')

    # --- Liquidity ---
    try:
        liq = pyvsmc.detect_liquidity(high=high, low=low, close=close)
        inspect_result(liq, 'LIQUIDITY')
    except Exception as e:
        print(f'LIQUIDITY ERROR: {e}')

    # --- Zones ---
    try:
        zones = pyvsmc.detect_zones(high=high, low=low, close=close)
        inspect_result(zones, 'ZONES')
    except Exception as e:
        print(f'ZONES ERROR: {e}')
