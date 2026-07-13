import pandas as pd
import numpy as np
import joblib
import xgboost as xgb
import os
import sys

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import VALID_TRADING_HOURS_UTC, NEWS_BLOCKS_UTC, MODEL_PATH, FEATURES_PATH, ASIAN_PAIRS, SNIPER_PAIRS

ASIAN_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "asian_brain.xgb")

class LiveSignalEngine:
    def __init__(self):
        self.sniper_model = None
        self.sniper_features = None
        self.asian_model = None
        
        # Load the Sniper ML model
        try:
            if os.path.exists(MODEL_PATH):
                self.sniper_model = joblib.load(MODEL_PATH)
                self.sniper_features = joblib.load(FEATURES_PATH)
                print("Sniper ML Model loaded successfully.")
            else:
                print(f"Warning: Sniper ML model not found at {MODEL_PATH}")
        except Exception as e:
            print(f"Warning: Could not load Sniper ML model: {e}")
            
        # Load the Asian ML model
        try:
            if os.path.exists(ASIAN_MODEL_PATH):
                self.asian_model = xgb.XGBClassifier()
                self.asian_model.load_model(ASIAN_MODEL_PATH)
                print("Asian ML Model loaded successfully.")
            else:
                print(f"Warning: Asian ML model not found at {ASIAN_MODEL_PATH}")
        except Exception as e:
            print(f"Warning: Could not load Asian ML model: {e}")

    def evaluate(self, latest: dict, prev: dict, pair: str) -> dict:
        result = {
            "signal": 0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "strategy": "",
            "fvg_entry": 0.0,
            "fvg_size": 0.0,
            "rr": 0.0,
            "ml_features": {},
            "ml_prob": 0.0,
            "rejection_reason": "Waiting for Killzone"
        }

        hour = latest['time'].hour
        day_of_week = latest['time'].dayofweek
        minute = latest['time'].minute
        current_close = latest['close']
        c_low = latest['low']
        c_high = latest['high']
        
        # ─── 1. ASIAN SCALPER LOGIC (00:00 - 06:00 UTC) ───
        if 0 <= hour < 6:
            if pair not in ASIAN_PAIRS:
                return result
                
            bb_upper = latest.get('bb_upper')
            bb_lower = latest.get('bb_lower')
            rsi = latest.get('15m_rsi')
            adx = latest.get('15m_adx', 0)
            
            if pd.isna(bb_upper) or pd.isna(rsi):
                result["rejection_reason"] = "Waiting for data"
                return result
                
            # TREND FILTER: Do not trade mean reversion if ADX is showing a strong trend (>30)
            if adx > 30:
                result["rejection_reason"] = "Trend too strong (ADX>30)"
                return result
                
            signal = 0
            sl = 0.0
            
            sl_buffer = 0.030 if "JPY" in pair else 0.0003

            # Reversal Logic
            if c_high >= bb_upper and current_close < bb_upper and rsi > 70:
                signal = -1
                sl = c_high + sl_buffer
            elif c_low <= bb_lower and current_close > bb_lower and rsi < 30:
                signal = 1
                sl = c_low - sl_buffer
                
            if signal != 0:
                risk = abs(current_close - sl)
                min_risk = 0.030 if "JPY" in pair else 0.0003
                if risk >= min_risk:
                    # ML Filter
                    if self.asian_model is not None:
                        features = pd.DataFrame([{
                            'direction': signal,
                            'rsi_14': rsi,
                            'bb_width': latest.get('bb_width'),
                            'atr_14': latest.get('atr_14'),
                            'hour': hour,
                            'minute': minute
                        }])
                        prob_win = self.asian_model.predict_proba(features)[0][1]
                        
                        if prob_win >= 0.55:
                            result['signal'] = signal
                            result['entry'] = current_close
                            result['fvg_entry'] = current_close
                            result['stop_loss'] = sl
                            result['take_profit'] = current_close + (risk * 1.5) if signal == 1 else current_close - (risk * 1.5)
                            result['strategy'] = "ASIAN"
                            result['ml_prob'] = prob_win
                            result['rr'] = 1.5
                            return result

        # ─── 2. V2 SNIPER LOGIC (London/NY Overlap) ───
        if pair not in SNIPER_PAIRS:
            return result
            
        # Killzones
        if day_of_week == 4:
            if hour not in [7, 8]: # London Only filter for Friday
                result["rejection_reason"] = "Outside Friday London Killzone"
                return result
        elif hour not in VALID_TRADING_HOURS_UTC:
            result["rejection_reason"] = "Outside UTC Killzone"
            return result
            
        # Static News Filter
        for block in NEWS_BLOCKS_UTC:
            if hour == block["hour"] and (block["min_start"] <= minute <= block["min_end"]):
                result["rejection_reason"] = "News Blocked"
                return result
                
        # Liquidity Sweep
        asia_high = latest.get('asia_high')
        asia_low = latest.get('asia_low')
        if pd.isna(asia_high) or pd.isna(asia_low):
            result["rejection_reason"] = "Waiting for Asia session data"
            return result
            
        recent_low = latest.get('rolling_60_low', 0)
        recent_high = latest.get('rolling_60_high', 100000)
        
        swept_bullish_liq = recent_low < asia_low
        swept_bearish_liq = recent_high > asia_high
        
        is_bullish_15m = latest.get('15m_bias_bullish', False)
        is_bearish_15m = not is_bullish_15m
        
        # Friday Filter
        weekly_open = latest.get('weekly_open')
        if day_of_week == 4 and not pd.isna(weekly_open):
            if current_close > weekly_open: is_bullish_15m = False
            elif current_close < weekly_open: is_bearish_15m = False
        
        # LONG SETUP
        if is_bullish_15m and swept_bullish_liq:
            result["rejection_reason"] = "Waiting for MSS (Bullish)"
            last_swing_high = prev.get('1m_last_swing_high', 100000)
            if current_close > last_swing_high:
                result["rejection_reason"] = "Waiting for FVG formation (Bullish)"
                if prev.get('1m_fvg_up', False):
                    entry_price = prev['1m_fvg_top']
                    stop_loss = prev['1m_fvg_bottom']
                    sl_pips = entry_price - stop_loss
                    if "JPY" in pair: sl_pips_check = sl_pips * 100
                    else: sl_pips_check = sl_pips * 10000
                    
                    if sl_pips_check > 3.0:
                        take_profit = entry_price + (sl_pips * 4) 
                        rr = (take_profit - entry_price) / (entry_price - stop_loss)
                        
                        if rr >= 2.0:
                            result["signal"] = 1
                            result["stop_loss"] = stop_loss
                            result["take_profit"] = take_profit
                            result["strategy"] = "SNIPER"
                            result["fvg_entry"] = entry_price
                            result["fvg_size"] = prev['1m_fvg_bottom'] - prev['1m_fvg_top']
                            result["rr"] = rr
                            result["ml_features"] = {
                                'fvg_size': result["fvg_size"],
                                'macd_hist': latest.get('15m_macd_hist', 0),
                                'rsi': latest.get('1m_rsi', 50),
                                'hour': hour,
                                'day_of_week': day_of_week,
                                'trend_dist': latest['close'] - latest.get('15m_ema_200', latest['close'])
                            }
                            if self.sniper_model is not None and self.sniper_features is not None:
                                feature_values = [result["ml_features"][f] for f in self.sniper_features]
                                prob = self.sniper_model.predict_proba([feature_values])[0][1]
                                result["ml_prob"] = prob
                                if prob >= 0.50:
                                    return result
                                else:
                                    result['signal'] = 0

        # SHORT SETUP
        if is_bearish_15m and swept_bearish_liq:
            result["rejection_reason"] = "Waiting for MSS (Bearish)"
            last_swing_low = prev.get('1m_last_swing_low', 0)
            if current_close < last_swing_low:
                result["rejection_reason"] = "Waiting for FVG formation (Bearish)"
                if prev.get('1m_fvg_down', False):
                    entry_price = prev['1m_fvg_bottom']
                    stop_loss = prev['1m_fvg_top']
                    sl_pips = stop_loss - entry_price
                    if "JPY" in pair: sl_pips_check = sl_pips * 100
                    else: sl_pips_check = sl_pips * 10000
                    
                    if sl_pips_check > 3.0:
                        take_profit = entry_price - (sl_pips * 4)
                        rr = (entry_price - take_profit) / (stop_loss - entry_price)
                        
                        if rr >= 2.0:
                            result["signal"] = -1
                            result["stop_loss"] = stop_loss
                            result["take_profit"] = take_profit
                            result["strategy"] = "SNIPER"
                            result["fvg_entry"] = entry_price
                            result["fvg_size"] = prev['1m_fvg_bottom'] - prev['1m_fvg_top']
                            result["rr"] = rr
                            result["ml_features"] = {
                                'fvg_size': result["fvg_size"],
                                'macd_hist': latest.get('15m_macd_hist', 0),
                                'rsi': latest.get('1m_rsi', 50),
                                'hour': hour,
                                'day_of_week': day_of_week,
                                'trend_dist': latest.get('15m_ema_200', latest['close']) - latest['close']
                            }
                            if self.sniper_model is not None and self.sniper_features is not None:
                                feature_values = [result["ml_features"][f] for f in self.sniper_features]
                                prob = self.sniper_model.predict_proba([feature_values])[0][1]
                                result["ml_prob"] = prob
                                if prob >= 0.50:
                                    return result
                                else:
                                    result['signal'] = 0
                                    
        # Default return (no valid signal)
        result['signal'] = 0
        return result
