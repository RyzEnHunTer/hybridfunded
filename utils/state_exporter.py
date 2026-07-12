import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("StateExporter")
BASE_DIR = Path(__file__).parent.parent

def export_state(account_login: int, balance: float, equity: float, 
                 total_profit: float, daily_trades: int, max_daily_trades: int,
                 active_trades: list, history: list, 
                 phase_type: str = "LIVE", profit_target_pct: float = 10.0,
                 max_daily_dd: float = 5.0, max_global_dd: float = 10.0,
                 daily_start_balance: float = 0.0, peak_balance: float = 0.0,
                 news_calendar: list = None, bot_status: str = "ONLINE", active_firm: str = "Unknown Firm"):
    """
    Dumps the bot's current state to a JSON file for the dashboard to read.
    """
    if news_calendar is None:
        news_calendar = []
        
    state_file = BASE_DIR / f"bot_state_{account_login}.json"
    
    # Calculate win rate from history
    wins = len([t for t in history if t.get('pnl', 0) > 0])
    total = len(history)
    win_rate = (wins / total * 100) if total > 0 else 0
    
    # Map new architecture to old frontend expectations
    # 1. Map active trades
    managed_positions = {}
    for i, t in enumerate(active_trades):
        managed_positions[str(i)] = {
            "pair": t.get("pair", ""),
            "direction": t.get("direction", 1),
            "entry_price": t.get("entry_price", 0.0),
            "original_lots": t.get("volume", 0.0),
            "breakeven_locked": False,
            "pending_reason": None,
            "strategy": t.get("strategy", "Unknown")
        }

    # 2. Map history
    journal = []
    for t in history:
        journal.append({
            "pair": t.get("pair", ""),
            "pnl": t.get("pnl", 0.0),
            "exit_time": t.get("close_time", datetime.now(timezone.utc).isoformat()),
            "reason": t.get("reason", "SL/TP/Manual"),
            "strategy": t.get("strategy", "Unknown")
        })

    data = {
        "config": {
            "phase": phase_type,
            "account_login": account_login,
            "starting_balance": balance,
            "profit_target_pct": profit_target_pct,
            "max_daily_trades": max_daily_trades,
            "max_daily_dd": max_daily_dd,
            "max_global_dd": max_global_dd,
            "daily_start_balance": balance if daily_start_balance == 0.0 else daily_start_balance,
            "peak_balance": balance if peak_balance == 0.0 else peak_balance,
            "active_firm": active_firm
        },
        "daily_start_balance": daily_start_balance,
        "peak_balance": peak_balance,
        "bot_status": bot_status,
        "equity": equity,
        "daily_trades_count": daily_trades,
        "trade_journal": journal,
        "managed_positions": managed_positions,
        "news_calendar": news_calendar
    }
    
    try:
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to export state: {e}")
