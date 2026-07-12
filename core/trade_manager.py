import MetaTrader5 as mt5
import logging
import time

class TradeManager:
    def __init__(self, risk_percent: float = 1.0):
        self.risk_percent = risk_percent
        self.logger = logging.getLogger("LiveBotV2")
        
    def _check_symbol(self, symbol: str) -> bool:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"{symbol} not found, can not call order_check()")
            return False
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                self.logger.error(f"symbol_select({symbol}) failed")
                return False
        return True

    def calculate_lot_size(self, symbol: str, entry_price: float, sl_price: float, risk_amount: float) -> float:
        """Calculate position size in lots based on the risk amount."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return 0.01
            
        tick_size = symbol_info.trade_tick_size
        tick_value = symbol_info.trade_tick_value
        
        if tick_size == 0 or tick_value == 0:
            return 0.01
            
        # Absolute distance in price
        price_dist = abs(entry_price - sl_price)
        
        # How many ticks is that?
        ticks = price_dist / tick_size
        
        # Risk per 1 standard lot
        risk_per_lot = ticks * tick_value
        
        if risk_per_lot == 0:
            return 0.01
            
        raw_volume = risk_amount / risk_per_lot
        return self._normalize_volume(symbol, raw_volume)

    def _normalize_volume(self, symbol: str, raw_volume: float) -> float:
        symbol_info = mt5.symbol_info(symbol)
        min_vol = symbol_info.volume_min
        max_vol = symbol_info.volume_max
        step_vol = symbol_info.volume_step
        
        vol = round(raw_volume / step_vol) * step_vol
        if vol < min_vol: vol = min_vol
        if vol > max_vol: vol = max_vol
        
        return float(round(vol, 2))

    def _get_filling_mode(self, symbol_info):
        """Dynamically find the allowed filling mode for the broker."""
        # mt5.SYMBOL_FILLING_FOK = 1, mt5.SYMBOL_FILLING_IOC = 2
        filling_mode = symbol_info.filling_mode
        if filling_mode & mt5.SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & mt5.SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def place_limit_order(self, symbol: str, direction: int, entry_price: float, sl: float, tp: float, balance: float, override_risk_percent: float = None, strategy_name: str = "ML Limit") -> bool:
        """
        Places a Limit Order in MT5 (Buy Limit or Sell Limit).
        direction: 1 for Long, -1 for Short
        """
        if not self._check_symbol(symbol): return False
        symbol_info = mt5.symbol_info(symbol)
        
        # --- FIX: DYNAMIC BROKER MINIMUM STOP LEVEL ---
        min_stop_points = symbol_info.trade_stops_level
        point = symbol_info.point
        min_stop_price_dist = (min_stop_points + 2) * point # Add 2 points buffer
        
        current_sl_dist = abs(entry_price - sl)
        if current_sl_dist < min_stop_price_dist:
            self.logger.warning(f"[{symbol}] SL too tight ({current_sl_dist:.5f}). Widening to broker minimum ({min_stop_price_dist:.5f})")
            original_rr = abs(tp - entry_price) / current_sl_dist if current_sl_dist > 0 else 1.5
            
            if direction == 1:
                sl = entry_price - min_stop_price_dist
                tp = entry_price + (min_stop_price_dist * original_rr)
            else:
                sl = entry_price + min_stop_price_dist
                tp = entry_price - (min_stop_price_dist * original_rr)
        # ----------------------------------------------
        
        risk_pct = override_risk_percent if override_risk_percent is not None else self.risk_percent
        risk_amount = balance * (risk_pct / 100.0)
        
        volume = self.calculate_lot_size(symbol, entry_price, sl, risk_amount)
        
        digits = symbol_info.digits
        
        entry_price = round(entry_price, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        
        action = mt5.TRADE_ACTION_PENDING
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == 1 else mt5.ORDER_TYPE_SELL_LIMIT
        filling = self._get_filling_mode(symbol_info)
        
        request = {
            "action": action,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "magic": 999111,
            "comment": strategy_name,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        
        # Exponential Backoff Retry Loop
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"[{symbol}] Limit Order Placed: {volume} lots @ {entry_price}")
                return True
                
            self.logger.warning(f"[{symbol}] OrderSend failed (Attempt {attempt+1}/{max_retries}): retcode={result.retcode}")
            
            # If it's a requote or connection issue, retry. Otherwise, break immediately.
            if result.retcode in [mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_CONNECTION]:
                time.sleep(0.25 * (attempt + 1)) # Wait 250ms, 500ms, 750ms
            else:
                break
                
        self.logger.error(f"[{symbol}] OrderSend permanently failed after {max_retries} attempts.")
        return False

    def close_position(self, ticket: int, symbol: str, volume: float) -> bool:
        """Close a specific open position."""
        position = mt5.positions_get(ticket=ticket)
        if not position: return False
        p = position[0]
        
        order_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if p.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        
        symbol_info = mt5.symbol_info(symbol)
        filling = self._get_filling_mode(symbol_info)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "magic": 999111,
            "comment": "Close Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        
        # Exponential Backoff Retry Loop
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"[{symbol}] Trade Closed: {volume} lots")
                return True
                
            self.logger.warning(f"[{symbol}] Close failed (Attempt {attempt+1}/{max_retries}): retcode={result.retcode}")
            if result.retcode in [mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_CONNECTION]:
                time.sleep(0.25 * (attempt + 1))
                # Update price for requote
                price = mt5.symbol_info_tick(symbol).bid if p.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
                request["price"] = price
            else:
                break
                
        self.logger.error(f"[{symbol}] Close permanently failed after {max_retries} attempts.")
        return False

    def modify_sl_tp(self, ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Modify an active position's SL or TP."""
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": round(new_sl, digits),
            "tp": round(new_tp, digits),
            "magic": 999111
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return True
                
            self.logger.warning(f"[{symbol}] SL/TP Modify failed (Attempt {attempt+1}/{max_retries}): retcode={result.retcode}")
            if result.retcode in [mt5.TRADE_RETCODE_CONNECTION, mt5.TRADE_RETCODE_REQUOTE]:
                time.sleep(0.25 * (attempt + 1))
            else:
                break
                
        self.logger.error(f"[{symbol}] SL/TP Modify permanently failed.")
        return False

    def cancel_all_pending_orders(self, symbol: str):
        """Cancel all pending limit orders for this symbol."""
        orders = mt5.orders_get(symbol=symbol)
        if not orders: return
        
        for order in orders:
            if order.magic == 999111:
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": order.ticket
                }
                mt5.order_send(request)
