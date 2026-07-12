import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import numpy as np

class LiveDataEngine:
    def __init__(self):
        pass
        
    def fetch_and_prepare_data(self, pair: str, num_candles: int = 1000) -> pd.DataFrame:
        """
        Fetches the last N candles for 15m and 1m timeframes from MT5.
        Computes all SMC, MACD, and RSI indicators, and maps them together.
        Returns the mapped 1m DataFrame.
        """
        # Fetch 15m Data
        rates_15m = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M15, 0, num_candles)
        if rates_15m is None:
            return None
            
        df_15m = pd.DataFrame(rates_15m)
        df_15m['time'] = pd.to_datetime(df_15m['time'], unit='s', utc=True)
        
        # Calculate 15m Indicators
        df_15m['15m_ema_200'] = df_15m['close'].ewm(span=200, adjust=False).mean()
        
        # MACD (12, 26, 9)
        exp1 = df_15m['close'].ewm(span=12, adjust=False).mean()
        exp2 = df_15m['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        df_15m['15m_macd_hist'] = macd - signal
        
        # Determine 15m Directional Bias (True if close > EMA200)
        df_15m['15m_bias_bullish'] = df_15m['close'] > df_15m['15m_ema_200']
        
        # Calculate Asian Session High/Low (00:00 to 06:00 UTC)
        df_15m['hour'] = df_15m['time'].dt.hour
        df_15m['is_asian'] = (df_15m['hour'] >= 0) & (df_15m['hour'] < 6)
        
        asian_highs = df_15m[df_15m['is_asian']].groupby(df_15m['time'].dt.date)['high'].max()
        asian_lows = df_15m[df_15m['is_asian']].groupby(df_15m['time'].dt.date)['low'].min()
        
        df_15m['date'] = df_15m['time'].dt.date
        df_15m = df_15m.merge(asian_highs.rename('asia_high'), left_on='date', right_index=True, how='left')
        df_15m = df_15m.merge(asian_lows.rename('asia_low'), left_on='date', right_index=True, how='left')
        
        # Asian Scalper Features (15m BB, ATR, RSI)
        df_15m['sma_20'] = df_15m['close'].rolling(20).mean()
        df_15m['std_20'] = df_15m['close'].rolling(20).std()
        df_15m['bb_upper'] = df_15m['sma_20'] + (2.0 * df_15m['std_20'])
        df_15m['bb_lower'] = df_15m['sma_20'] - (2.0 * df_15m['std_20'])
        df_15m['bb_width'] = (df_15m['bb_upper'] - df_15m['bb_lower']) / df_15m['sma_20']
        
        delta_15 = df_15m['close'].diff()
        gain_15 = (delta_15.where(delta_15 > 0, 0)).rolling(window=14).mean()
        loss_15 = (-delta_15.where(delta_15 < 0, 0)).rolling(window=14).mean()
        rs_15 = gain_15 / loss_15
        df_15m['15m_rsi'] = 100 - (100 / (1 + rs_15))
        
        # 15m Trend Strength (ADX)
        adx = ta.adx(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        if adx is not None and not adx.empty:
            df_15m['15m_adx'] = adx['ADX_14']
        else:
            df_15m['15m_adx'] = 0.0
        
        df_15m['tr0'] = abs(df_15m['high'] - df_15m['low'])
        df_15m['tr1'] = abs(df_15m['high'] - df_15m['close'].shift())
        df_15m['tr2'] = abs(df_15m['low'] - df_15m['close'].shift())
        df_15m['tr'] = df_15m[['tr0', 'tr1', 'tr2']].max(axis=1)
        df_15m['atr_14'] = df_15m['tr'].rolling(14).mean()
        
        # Fetch Weekly Data for Friday Mean Reversion Filter
        rates_w1 = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_W1, 0, 1)
        if rates_w1 is not None and len(rates_w1) > 0:
            df_15m['weekly_open'] = rates_w1[0]['open']
        else:
            df_15m['weekly_open'] = np.nan
        
        # Fetch 1m Data
        rates_1m = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M1, 0, num_candles)
        if rates_1m is None:
            return None
            
        df_1m = pd.DataFrame(rates_1m)
        df_1m['time'] = pd.to_datetime(df_1m['time'], unit='s', utc=True)
        
        # Calculate 1m RSI (14 period)
        delta = df_1m['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_1m['1m_rsi'] = 100 - (100 / (1 + rs))
        
        # Pre-calculate 60-candle rolling min/max for liquidity sweeps
        df_1m['rolling_60_low'] = df_1m['low'].rolling(60).min()
        df_1m['rolling_60_high'] = df_1m['high'].rolling(60).max()
        
        # Find 1m Swing Highs/Lows (length=3)
        swing_len = 3
        df_1m['1m_swing_high'] = df_1m['high'] == df_1m['high'].rolling(window=swing_len*2+1, center=True).max()
        df_1m['1m_swing_low'] = df_1m['low'] == df_1m['low'].rolling(window=swing_len*2+1, center=True).min()
        
        df_1m['1m_last_swing_high'] = df_1m['high'].where(df_1m['1m_swing_high']).ffill()
        df_1m['1m_last_swing_low'] = df_1m['low'].where(df_1m['1m_swing_low']).ffill()
        
        # Calculate 1m FVG
        df_1m['1m_fvg_up'] = (df_1m['low'] > df_1m['high'].shift(2)) & (df_1m['close'].shift(1) > df_1m['open'].shift(1))
        df_1m['1m_fvg_down'] = (df_1m['high'] < df_1m['low'].shift(2)) & (df_1m['close'].shift(1) < df_1m['open'].shift(1))
        
        df_1m['1m_fvg_top'] = np.where(df_1m['1m_fvg_up'], df_1m['low'], np.where(df_1m['1m_fvg_down'], df_1m['low'].shift(2), np.nan))
        df_1m['1m_fvg_bottom'] = np.where(df_1m['1m_fvg_up'], df_1m['high'].shift(2), np.where(df_1m['1m_fvg_down'], df_1m['high'], np.nan))
        
        # Forward fill the context from 15m to 1m
        df_1m['merge_time'] = df_1m['time'].dt.floor('15min')
        df_15m['merge_time'] = df_15m['time']
        
        cols_to_merge = [
            'merge_time', '15m_ema_200', '15m_macd_hist', '15m_bias_bullish', 
            'asia_high', 'asia_low', 'weekly_open',
            'bb_upper', 'bb_lower', 'bb_width', '15m_rsi', 'atr_14', '15m_adx'
        ]
        df_mapped = pd.merge_asof(
            df_1m.sort_values('time'),
            df_15m[cols_to_merge].sort_values('merge_time'),
            left_on='time',
            right_on='merge_time',
            direction='backward'
        )
        
        return df_mapped
