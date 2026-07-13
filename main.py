import MetaTrader5 as mt5
import pandas as pd
import time
import os
import sys
from datetime import datetime, timezone, timedelta
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import print as rprint

# Local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config.settings import (
    ACTIVE_FIRM, 
    ACCOUNT_PHASE,
    SNIPER_PAIRS, 
    ASIAN_PAIRS, 
    SNIPER_RISK_PERCENT, 
    WEEKEND_HOLDING_ALLOWED,
    MAX_CONCURRENT_TRADES, 
    MAX_DAILY_TRADES, 
    MAX_TRADES_PER_PAIR,
    PROFIT_TARGET_PCT,
    MAX_DAILY_DRAWDOWN_PERCENT,
    MAX_GLOBAL_DRAWDOWN_PERCENT,
    RECORDINGS_DIR,
    VALID_TRADING_HOURS_UTC
)

from core.data_engine import LiveDataEngine
from core.signal_engine import LiveSignalEngine
from core.trade_manager import TradeManager
from core.news_engine import NewsEngine

from utils.account_manager import AccountManager
from utils.notifier import NotificationCenter
from utils.state_exporter import export_state

from web.server import start_dashboard_server
import logging

# Setup File Logging
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(BASE_DIR, "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
    
log_file = os.path.join(log_dir, "live_bot_v2.log")
error_log_file = os.path.join(log_dir, "live_bot_v2_errors.log")

# General Logger (INFO and above)
info_handler = logging.FileHandler(log_file, encoding='utf-8')
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))

# Error-Only Logger (ERROR and above)
error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter("%(asctime)s - [ERROR] - %(message)s"))

logger = logging.getLogger("LiveBotV2")
logger.setLevel(logging.INFO)

# Prevent duplicate handlers if script is reloaded
if not logger.handlers:
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)

def wait_for_next_minute(sess_str: str = ""):
    """
    Sleep until the next 1-minute candle close.
    Aligns execution to the top of every minute.
    """
    now = datetime.now(timezone.utc)
    wait_seconds = 60 - now.second + 2 # Add 2 seconds buffer to ensure the candle is fully closed on MT5 servers
    
    # Hide cursor and start animated countdown
    sys.stdout.write("\033[?25l")
    try:
        while wait_seconds > 0:
            # Smooth spinner animation
            spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spin_char = spinner[wait_seconds % len(spinner)]
            
            # Use ANSI escape codes to overwrite the same line in terminal
            status_text = f"[{sess_str}] " if sess_str else "[LIVE] "
            sys.stdout.write(f"\r  {spin_char} {status_text}Scanning market... Waiting {wait_seconds:02d}s for next 1m candle close... ")
            sys.stdout.flush()
            time.sleep(1)
            wait_seconds -= 1
    except KeyboardInterrupt:
        sys.stdout.write("\033[?25h\r" + " " * 80 + "\r")
        sys.stdout.flush()
        raise
    finally:
        # Show cursor again and clear line
        sys.stdout.write("\033[?25h\r" + " " * 80 + "\r")
        sys.stdout.flush()

def init_mt5():
    if not mt5.initialize():
        print("MT5 Initialization failed. Make sure MT5 terminal is open.")
        return False
    return True

def safe_account_info():
    """
    Safely retrieves account info. If MT5 loses connection to the broker,
    this will loop and attempt to reconnect every 5 seconds until successful,
    preventing the bot from crashing with an AttributeError.
    """
    while True:
        acc = mt5.account_info()
        if acc is not None:
            return acc
            
        logger.error("MT5 Connection Lost! Attempting to reconnect...")
        print("\n🚨 [WARNING] MT5 Connection Lost! Attempting to reconnect to broker...")
        time.sleep(5)
        mt5.initialize()

def auto_detect_symbols(base_pairs):
    """
    Find the actual broker symbol (e.g., 'EURUSD.pro') for each base pair.
    """
    all_symbols = mt5.symbols_get()
    if not all_symbols: return {p: p for p in base_pairs}
    
    symbol_names = [s.name for s in all_symbols]
    symbol_map = {}
    
    for base_pair in base_pairs:
        matches = [s for s in symbol_names if s.upper().startswith(base_pair)]
        if not matches:
            symbol_map[base_pair] = base_pair
            continue
            
        exact = [s for s in matches if s.upper() == base_pair]
        best_match = exact[0] if exact else sorted(matches, key=len)[0]
        
        mt5.symbol_select(best_match, True)
        symbol_map[base_pair] = best_match
        
    print("\n--- 🔍 Broker Symbol Auto-Detection ---")
    for base, mapped in symbol_map.items():
        if base != mapped:
            print(f"  ✅ {base} -> {mapped}")
        else:
            print(f"  ✅ {base} (Exact Match)")
    print("---------------------------------------\n")
        
    return symbol_map

def record_data(symbol: str, candle: dict):
    """
    Continuous Learning Module:
    Appends the latest 1-minute candle (and its calculated ML features) to a permanent CSV file.
    This builds the dataset needed to retrain the ML model on weekends.
    """
    if not os.path.exists(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR)
        
    file_path = os.path.join(RECORDINGS_DIR, f"live_1m_{symbol}.csv")
    
    # Select only the features we need to store for retraining
    features_to_store = {
        'time': candle.get('time'),
        'open': candle.get('open'),
        'high': candle.get('high'),
        'low': candle.get('low'),
        'close': candle.get('close'),
        '15m_ema_200': candle.get('15m_ema_200'),
        '15m_macd_hist': candle.get('15m_macd_hist'),
        '1m_rsi': candle.get('1m_rsi'),
        '1m_fvg_size': candle.get('1m_fvg_bottom', 0) - candle.get('1m_fvg_top', 0),
        '15m_rsi': candle.get('15m_rsi'),
        'bb_width': candle.get('bb_width'),
        'atr_14': candle.get('atr_14'),
        '15m_adx': candle.get('15m_adx')
    }
    
    df_new = pd.DataFrame([features_to_store])
    
    if not os.path.exists(file_path):
        df_new.to_csv(file_path, index=False)
    else:
        df_new.to_csv(file_path, mode='a', header=False, index=False)

def print_banner():
    """Print startup banner."""
    console = Console()
    banner = """[bold cyan]
    ██╗  ██╗██╗   ██╗███╗   ██╗████████╗███████╗██████╗ 
    ██║  ██║██║   ██║████╗  ██║╚══██╔══╝██╔════╝██╔══██╗
    ███████║██║   ██║██╔██╗ ██║   ██║   █████╗  ██████╔╝
    ██╔══██║██║   ██║██║╚██╗██║   ██║   ██╔══╝  ██╔══██╗
    ██║  ██║╚██████╔╝██║ ╚████║   ██║   ███████╗██║  ██║
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝[/]
    [bold yellow]          ML SMC PROP FIRM BOT v2.0[/]
    """
    console.print(Panel(banner, border_style="cyan", expand=False))

def get_daily_trade_counts(mapped_pairs):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Get deals from today until tomorrow
    deals = mt5.history_deals_get(today, datetime.now(timezone.utc) + timedelta(days=1))
    if not deals:
        return 0, {pair: 0 for pair in mapped_pairs}
        
    # We only count Entry Deals (deal.entry == 0) for our bot's magic number 999111
    entries = [d for d in deals if d.entry == 0 and d.magic == 999111]
    
    total = len(entries)
    pair_counts = {pair: 0 for pair in mapped_pairs}
    for d in entries:
        if d.symbol in pair_counts:
            pair_counts[d.symbol] += 1
            
    return total, pair_counts

def get_active_trade_count():
    positions = mt5.positions_get()
    orders = mt5.orders_get()
    count = 0
    if positions:
        count += len([p for p in positions if p.magic == 999111])
    if orders:
        count += len([o for o in orders if o.magic == 999111])
    return count
    
def get_active_pair_trades(symbol):
    positions = mt5.positions_get(symbol=symbol)
    orders = mt5.orders_get(symbol=symbol)
    count = 0
    if positions:
        count += len([p for p in positions if p.magic == 999111])
    if orders:
        count += len([o for o in orders if o.magic == 999111])
    return count

def get_active_trades_for_dashboard():
    positions = mt5.positions_get()
    active = []
    if positions:
        for p in positions:
            if p.magic == 999111:
                active.append({
                    "pair": p.symbol,
                    "direction": 1 if p.type == mt5.ORDER_TYPE_BUY else -1,
                    "entry_price": p.price_open,
                    "volume": p.volume,
                    "strategy": p.comment if p.comment else "Unknown"
                })
    return active

def get_history_for_dashboard():
    start_time = datetime.now(timezone.utc) - timedelta(days=30)
    deals = mt5.history_deals_get(start_time, datetime.now(timezone.utc) + timedelta(days=1))
    history = []
    if deals:
        for d in deals:
            if d.magic == 999111 and d.entry == 1: # Entry == 1 is OUT (closing a trade)
                history.append({
                    "pair": d.symbol,
                    "pnl": d.profit,
                    "close_time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                    "reason": "SL/TP/Close",
                    "strategy": d.comment if d.comment else "Unknown"
                })
    return history

import csv

def log_live_trade(ticket, symbol, pnl, close_price):
    try:
        deals = mt5.history_deals_get(position=ticket)
        entry_price = deals[0].price if deals and len(deals) > 0 else 0.0
        volume = deals[0].volume if deals and len(deals) > 0 else 0.0
        
        log_file = os.path.join(BASE_DIR, "data", "live_trade_history.csv")
        file_exists = os.path.isfile(log_file)
        
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Ticket', 'Time_UTC', 'Pair', 'Volume', 'Entry_Price', 'Close_Price', 'PnL'])
            writer.writerow([
                ticket,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                volume,
                entry_price,
                close_price,
                pnl
            ])
    except Exception as e:
        logger.error(f"Failed to log trade to CSV: {e}")

def main():
    print_banner()
    console = Console()
    console.print("\n[dim]Initializing Machine Learning SMC Live Bot (V2)...[/]")
    if not init_mt5():
        return
        
    ALL_PAIRS = list(set(SNIPER_PAIRS + ASIAN_PAIRS))
    SYMBOL_MAP = auto_detect_symbols(ALL_PAIRS)
    MAPPED_TRADING_PAIRS = [SYMBOL_MAP.get(p, p) for p in ALL_PAIRS]
    
    # ── INIT ENGINES ──────────────────────────────────────────────────────────
    data_engine = LiveDataEngine()
    signal_engine = LiveSignalEngine()
    trade_manager = TradeManager()
    news_engine = NewsEngine()
    
    account_info = safe_account_info()
    if account_info is None:
        print("Failed to get account info. Exiting.")
        mt5.shutdown()
        return
        
    start_balance = account_info.balance
    
    # Try to recover daily_start_balance and peak_balance from last session
    import glob
    state_files = glob.glob(str(os.path.join(BASE_DIR, "bot_state_*.json")))
    daily_start_balance = start_balance
    peak_balance = start_balance
    if state_files:
        try:
            import json as _json
            latest_state = max(state_files, key=os.path.getmtime)
            with open(latest_state, "r") as f:
                old_state = _json.load(f)
            
            saved_dsb = old_state.get("daily_start_balance")
            if saved_dsb and saved_dsb > 0:
                daily_start_balance = saved_dsb
                
            saved_peak = old_state.get("peak_balance")
            if saved_peak and saved_peak > start_balance:
                peak_balance = saved_peak
        except Exception:
            pass
            
    current_day = datetime.now(timezone.utc).date()
    
    # Init V1 Account Manager & Notifier
    acct_mgr = AccountManager()
    active_rules = acct_mgr.get_or_create_account(account_info.login, start_balance)
    notification_rules = acct_mgr.get_or_create_notifications()
    
    # Load dynamic config rules 
    from config.settings import ACTIVE_FIRM, ACCOUNT_PHASE, PROFIT_TARGET_PCT, MAX_DAILY_DRAWDOWN_PERCENT, MAX_GLOBAL_DRAWDOWN_PERCENT
    
    if ACTIVE_FIRM == "CUSTOM_RULES":
        # Load from V1 accounts.json
        max_daily_dd = active_rules.get('max_daily_dd', 5.0)
        max_total_dd = active_rules.get('max_total_dd', 10.0)
        # Legacy fallback for old state files using decimals
        if max_daily_dd < 1.0: max_daily_dd *= 100
        if max_total_dd < 1.0: max_total_dd *= 100
        ACCOUNT_PHASE = active_rules.get('phase_type', "LIVE")
    else:
        # Load from V2 prop firm presets
        max_daily_dd = MAX_DAILY_DRAWDOWN_PERCENT
        max_total_dd = MAX_GLOBAL_DRAWDOWN_PERCENT
        # Inject into old dict structure so downstream components don't break
        active_rules['phase_type'] = ACCOUNT_PHASE
        active_rules['profit_target_pct'] = PROFIT_TARGET_PCT if PROFIT_TARGET_PCT is not None else 0.0
    
    # 1. ACCOUNT TABLE
    account_table = Table(show_header=False, box=None, padding=(0, 2))
    account_table.add_column("Key", style="cyan", justify="right")
    account_table.add_column("Value", style="bold white")
    account_table.add_row("Account", str(account_info.login))
    account_table.add_row("Server", str(account_info.server))
    account_table.add_row("Balance", f"${start_balance:,.2f}")
    
    # 2. RISK TABLE
    risk_table = Table(show_header=False, box=None, padding=(0, 2))
    risk_table.add_column("Key", style="magenta", justify="right")
    risk_table.add_column("Value", style="bold white")
    risk_table.add_row("Sniper Risk", f"{SNIPER_RISK_PERCENT}%")
    risk_table.add_row("Asian Risk", "Dynamic (0.5% - 1.0%)")
    risk_table.add_row("Max Daily DD", f"{max_daily_dd}%")
    risk_table.add_row("Max Global DD", f"{max_total_dd}%")
    risk_table.add_row("Phase Type", active_rules.get('phase_type', 'N/A'))
    
    # 3. ML TABLE
    ml_table = Table(show_header=False, box=None, padding=(0, 2))
    ml_table.add_column("Key", style="green", justify="right")
    ml_table.add_column("Value", style="bold white")
    ml_status = "[bold green]LOADED (x2)[/]" if signal_engine.sniper_model is not None and signal_engine.asian_model is not None else "[bold red]MISSING[/]"
    ml_table.add_row("ML Status", ml_status)
    ml_table.add_row("Strategy", "Sniper (Day) + Scalper (Night)")
    ml_table.add_row("Pairs", str(len(ALL_PAIRS)))
    
    from rich.columns import Columns
    metrics_columns = Columns([
        Panel(account_table, title="[bold blue]Account Info[/]", border_style="blue"),
        Panel(risk_table, title="[bold magenta]Risk Settings[/]", border_style="magenta"),
        Panel(ml_table, title="[bold green]ML & Strategy[/]", border_style="green")
    ])
    
    console.print()
    console.print(Panel(
        metrics_columns,
        title="[bold yellow]🚀 HUNTER ML BOT | V2 🚀[/]",
        subtitle="[dim]Ready for deployment...[/]",
        border_style="yellow",
        expand=False
    ))
    
    # MAIN MENU
    menu_text = Text()
    menu_text.append("\n  [1] ", style="bold green")
    menu_text.append("START TRADING  — Bot will begin scanning for setups\n")
    menu_text.append("  [2] ", style="bold yellow")
    menu_text.append("DRY RUN        — Bot runs but does NOT place real trades\n")
    menu_text.append("  [3] ", style="bold red")
    menu_text.append("EXIT           — Shutdown and disconnect\n")
    menu_text.append("  [4] ", style="bold cyan")
    menu_text.append("NOTIFICATIONS  — Change Telegram/Discord settings\n")
    menu_text.append("  [5] ", style="bold magenta")
    menu_text.append("ACCOUNT RULES  — Change Prop Firm Target and Drawdowns\n")
    
    console.print(Panel(menu_text, title="[bold white]MAIN MENU[/]", border_style="white", expand=False))
    
    dry_run = False
    while True:
        choice = input("  Enter your choice (1/2/3/4/5): ").strip()
        if choice == "1":
            print("\n  >>> LIVE TRADING MODE ACTIVATED <<<")
            break
        elif choice == "2":
            dry_run = True
            print("\n  >>> DRY RUN MODE — No real trades will be placed <<<")
            break
        elif choice == "3":
            print("\n  Shutting down...")
            mt5.shutdown()
            return
        elif choice == "4":
            notification_rules = acct_mgr.get_or_create_notifications(force_prompt=True)
            print("\n  Notification settings updated. Ready when you are!")
        elif choice == "5":
            try:
                import json
                presets_file = os.path.join(os.path.dirname(__file__), "config", "prop_firm_presets.json")
                with open(presets_file, "r") as f:
                    presets = json.load(f)
                
                firms = list(presets.keys())
                print("\n  --- AVAILABLE PROP FIRMS ---")
                for i, firm in enumerate(firms):
                    print(f"  [{i+1}] {firm}")
                print(f"  [{len(firms)+1}] Custom Rules (Manual Entry)")
                
                f_idx = input("  Select firm number: ").strip()
                
                if int(f_idx) == len(firms) + 1:
                    selected_firm = "CUSTOM_RULES"
                    selected_phase = "LIVE"
                    print("\n  >>> Enter your custom risk parameters below:")
                    # Trigger the old V1 prompt
                    acct_mgr.get_or_create_account(account_info.login, start_balance, force_prompt=True)
                else:
                    selected_firm = firms[int(f_idx)-1]
                    print("\n  --- ACCOUNT PHASE ---")
                    print("  [1] EVALUATION - PHASE 1")
                    print("  [2] EVALUATION - PHASE 2")
                    print("  [3] LIVE FUNDED")
                    p_idx = input("  Select phase number: ").strip()
                    if p_idx == "1": selected_phase = "PHASE_1"
                    elif p_idx == "2": selected_phase = "PHASE_2"
                    else: selected_phase = "LIVE"
                
                # Save to persistent state file
                state_file = os.path.join(os.path.dirname(__file__), "config", "active_firm_state.json")
                with open(state_file, "w") as f:
                    json.dump({"ACTIVE_FIRM": selected_firm, "ACCOUNT_PHASE": selected_phase}, f)
                    
                print(f"\n  ✅ Successfully set Prop Firm rules to {selected_firm} ({selected_phase})")
                print("  Please restart the bot to lock in the new configuration.")
                mt5.shutdown()
                sys.exit(0)
            except Exception as e:
                print(f"\n  ❌ Failed to set prop firm presets: {e}")
        else:
            print("  Invalid choice. Please enter 1, 2, 3, 4, or 5.")
            
    print("\n---------------------------------------------------")
    
    # ── START DASHBOARD SERVER ───────────────────────────────────────────────
    _, public_url = start_dashboard_server()
    if public_url:
        print(f"Web Dashboard available at: {public_url}")
    else:
        print("Web Dashboard available locally at: http://localhost:5055")
        
    # ── STARTUP NOTIFICATION ──────────────────────────────────────────────────
    mode_str = "DRY RUN MODE" if dry_run else "LIVE TRADING MODE"
    msg = (f"🟢 <b>Hunter ML Bot V2 Started</b>\n\n"
           f"<b>Mode:</b> {mode_str}\n"
           f"<b>Account:</b> {account_info.login}\n"
           f"<b>Balance:</b> ${start_balance:,.2f}\n")
    if public_url:
        msg += f"<b>Dashboard:</b> <a href='{public_url}'>{public_url}</a>\n"
        
    NotificationCenter.notify(msg)
    
    # ── EXPORT INITIAL STATE ──────────────────────────────────────────────────
    bot_status = "ACTIVE (London/NY)"
    _now = datetime.now(timezone.utc)
    if _now.weekday() == 5 or _now.weekday() == 6:
        bot_status = "SLEEPING (Weekend)"
        
    export_state(
        account_login=account_info.login,
        balance=start_balance,
        equity=start_balance,
        total_profit=0.0,
        daily_trades=get_daily_trade_counts(MAPPED_TRADING_PAIRS)[0],
        max_daily_trades=MAX_DAILY_TRADES,
        active_trades=get_active_trades_for_dashboard(),
        history=get_history_for_dashboard(),
        phase_type=ACCOUNT_PHASE,
        profit_target_pct=PROFIT_TARGET_PCT if PROFIT_TARGET_PCT is not None else 0.0,
        max_daily_dd=max_daily_dd,
        max_global_dd=max_total_dd,
        daily_start_balance=daily_start_balance,
        peak_balance=peak_balance,
        news_calendar=news_engine.get_dashboard_schedule(),
        bot_status=bot_status,
        active_firm=ACTIVE_FIRM
    )
    
    # State tracking
    last_processed_candle_time = {pair: None for pair in MAPPED_TRADING_PAIRS}
    active_signals = {pair: None for pair in MAPPED_TRADING_PAIRS}
    tracked_orders = set()
    tracked_positions = set()
    tracked_partials = set()
    
    trading_halted_today = False
    
    try:
        while True:
            # 1. Check Drawdown & Reset Daily
            now_utc = datetime.now(timezone.utc)
            if now_utc.date() != current_day:
                current_day = now_utc.date()
                acc = safe_account_info()
                daily_start_balance = acc.balance
                trading_halted_today = False
                print(f"\n--- NEW DAY: {current_day} | Starting Balance: ${daily_start_balance:,.2f} ---")
                
            acc = safe_account_info()
            current_balance = acc.balance
            
            if current_balance > peak_balance:
                peak_balance = current_balance
                
            daily_dd = (current_balance - daily_start_balance) / daily_start_balance * 100
            global_dd = (current_balance - peak_balance) / peak_balance * 100
            
            if global_dd <= -max_total_dd:
                print(f"CRITICAL: Global Drawdown ({global_dd:.2f}%) exceeded {max_total_dd}%. HALTING BOT.")
                NotificationCenter.notify(f"🚨 <b>CRITICAL ALARM</b>\nGlobal Drawdown ({global_dd:.2f}%) breached limit. Bot halted.")
                break
                
            if daily_dd <= -max_daily_dd and not trading_halted_today:
                print(f"WARNING: Daily Drawdown ({daily_dd:.2f}%) exceeded {max_daily_dd}%. Halting trading for today.")
                NotificationCenter.notify(f"⚠️ <b>WARNING</b>\nDaily Drawdown ({daily_dd:.2f}%) breached limit. Trading halted for today.")
                trading_halted_today = True
                
            if trading_halted_today:
                export_state(
                    account_login=account_info.login, balance=start_balance, equity=current_balance, total_profit=0.0,
                    daily_trades=0, max_daily_trades=MAX_DAILY_TRADES, active_trades=[], history=[], 
                    phase_type=ACCOUNT_PHASE, profit_target_pct=PROFIT_TARGET_PCT if PROFIT_TARGET_PCT is not None else 0.0,
                    max_daily_dd=max_daily_dd, max_global_dd=max_total_dd,
                    daily_start_balance=daily_start_balance, peak_balance=peak_balance,
                    news_calendar=news_engine.get_dashboard_schedule(),
                    bot_status="HALTED (Daily Limit)", active_firm=ACTIVE_FIRM
                )
                time.sleep(60)
                continue
                
            # 1.5 Friday Auto-Liquidation & Weekend Sleep
            is_friday_close = (now_utc.weekday() == 4 and now_utc.hour >= 21)
            is_saturday = (now_utc.weekday() == 5)
            is_sunday_sleep = (now_utc.weekday() == 6 and not (now_utc.hour == 23 and now_utc.minute >= 55))
            
            if is_friday_close:
                if not dry_run:
                    mt5_positions = mt5.positions_get()
                    if mt5_positions:
                        print("\n🚨 FRIDAY 21:00 UTC! Liquidating all open positions...")
                        NotificationCenter.notify("🚨 <b>WEEKEND AUTO-LIQUIDATION</b>\nFriday 21:00 UTC reached. Closing all open trades to prevent weekend gap risk.")
                        for p in mt5_positions:
                            if p.magic != 999111:
                                continue
                            trade_manager.close_position(p.ticket, p.symbol, p.volume)
                            trade_manager.cancel_all_pending_orders(p.symbol)
                
                sys.stdout.write("\r  [SLEEP] Market closed. Waking up 5 mins before Monday...             ")
                sys.stdout.flush()
                time.sleep(60)
                continue
                
            if is_saturday or is_sunday_sleep:
                sys.stdout.write("\r  [SLEEP] Market closed for Weekend. Waking up 5 mins before Monday... ")
                sys.stdout.flush()
                export_state(
                    account_login=account_info.login, balance=start_balance, equity=current_balance, total_profit=0.0,
                    daily_trades=0, max_daily_trades=MAX_DAILY_TRADES, active_trades=[], history=[], 
                    phase_type=ACCOUNT_PHASE, profit_target_pct=PROFIT_TARGET_PCT if PROFIT_TARGET_PCT is not None else 0.0,
                    max_daily_dd=max_daily_dd, max_global_dd=max_total_dd,
                    daily_start_balance=daily_start_balance, peak_balance=peak_balance,
                    news_calendar=news_engine.get_dashboard_schedule(),
                    bot_status="SLEEPING (Weekend)", active_firm=ACTIVE_FIRM
                )
                time.sleep(60)
                continue
                
            # 2. Check Global Prop Firm Limits
            total_daily_trades, pair_daily_trades = get_daily_trade_counts(MAPPED_TRADING_PAIRS)
            active_trades = get_active_trade_count()
            
            if total_daily_trades >= MAX_DAILY_TRADES:
                print(f"🛑 MAX DAILY TRADES REACHED ({MAX_DAILY_TRADES}). Bot is sleeping until midnight.")
                time.sleep(60)
                continue
                
            if active_trades >= MAX_CONCURRENT_TRADES:
                print(f"⏸️ MAX CONCURRENT TRADES OPEN ({MAX_CONCURRENT_TRADES}). Waiting for a trade to close before scanning...")
                time.sleep(60)
                continue
                
            # 2.5 Advanced Notification Polling
            if not dry_run:
                current_positions = mt5.positions_get()
                current_position_tickets = {p.ticket: p for p in current_positions if p.magic == 999111} if current_positions else {}
                
                # Check for Opened Positions
                for ticket, p in current_position_tickets.items():
                    if ticket not in tracked_positions:
                        tracked_positions.add(ticket)
                        dir_str = "LONG" if p.type == mt5.ORDER_TYPE_BUY else "SHORT"
                        brain_name = "Sniper V2 Brain" if "SNIPER" in (p.comment or "").upper() else "Asian Scalper Brain"
                        msg = f"🟢 <b>TRADE OPENED: {p.symbol}</b>\nBrain: {brain_name}\nType: {dir_str}\nEntry: {p.price_open}\nVolume: {p.volume}"
                        NotificationCenter.notify(msg)
                        
                # Check for Closed Positions
                for ticket in list(tracked_positions):
                    if ticket not in current_position_tickets:
                        tracked_positions.remove(ticket)
                        deals = mt5.history_deals_get(datetime.now(timezone.utc) - timedelta(minutes=15), datetime.now(timezone.utc) + timedelta(minutes=1))
                        if deals:
                            for d in deals:
                                if d.position_id == ticket and d.entry == 1: # Deal out (close)
                                    pnl = d.profit
                                    icon = "✅" if pnl > 0 else "🛑"
                                    res = "WIN" if pnl > 0 else "LOSS"
                                    msg = f"{icon} <b>TRADE CLOSED ({res}): {d.symbol}</b>\nFinal PnL: ${pnl:.2f}"
                                    NotificationCenter.notify(msg)
                                    log_live_trade(ticket, d.symbol, pnl, d.price)
                                    break
                                    
                # 2.7 Active Position Monitoring (BE & Partials)
                for ticket, p in current_position_tickets.items():
                    if ticket not in tracked_partials and p.sl != 0.0:
                        risk_dist = abs(p.price_open - p.sl)
                        current_profit_dist = abs(p.price_current - p.price_open)
                        
                        is_in_profit = (p.type == mt5.ORDER_TYPE_BUY and p.price_current > p.price_open) or \
                                       (p.type == mt5.ORDER_TYPE_SELL and p.price_current < p.price_open)
                                       
                        if is_in_profit and risk_dist > 0 and current_profit_dist >= (risk_dist * 2.0):
                            tracked_partials.add(ticket)
                            
                            new_sl = p.price_open
                            trade_manager.modify_sl_tp(ticket, p.symbol, new_sl, p.tp)
                            
                            volume_to_close = p.volume / 2.0
                            trade_manager.close_position(ticket, p.symbol, volume_to_close)
                            
                            NotificationCenter.notify(
                                f"🛡️ <b>RISK FREE & PARTIALS SECURED: {p.symbol}</b>\n"
                                f"Hit 1:2 RR! SL moved to Breakeven.\n"
                                f"Closed 50% of volume ({volume_to_close:.2f})."
                            )
                            
            # 3. Main Processing Loop
            curr_hr = now_utc.hour
            
            if curr_hr in VALID_TRADING_HOURS_UTC:
                sess_str = "ACTIVE (London/NY)"
            elif 0 <= curr_hr < 6:
                sess_str = "ACTIVE (Asian Session)"
            else:
                # Find the next valid hour (checking both Asian and Sniper hours)
                all_active_hours = sorted(VALID_TRADING_HOURS_UTC + list(range(6)))
                future_hours = [h for h in all_active_hours if h > curr_hr]
                if future_hours:
                    hours_until = future_hours[0] - curr_hr
                else:
                    hours_until = (24 - curr_hr) + all_active_hours[0]
                sess_str = f"SLEEPING (Opens in {hours_until}h)"
                
            for pair in MAPPED_TRADING_PAIRS:
                if pair_daily_trades.get(pair, 0) >= MAX_TRADES_PER_PAIR:
                    logger.info(f"[{pair}] 🛑 Max trades per pair reached ({MAX_TRADES_PER_PAIR}). Skipping.")
                    continue
                    
                if get_active_pair_trades(pair) > 0:
                    logger.info(f"[{pair}] ⏸️ Trade already active. Skipping.")
                    continue
                    
                # 🔴 NEWS EMBARGO CHECK
                if news_engine.is_news_embargo_active(pair):
                    logger.info(f"[{pair}] 📰 NEWS EMBARGO ACTIVE! Skipping scan to avoid volatility.")
                    sys.stdout.write(f"\r  [NEWS EMBARGO] High-Impact news active for {pair}. Skipping...          ")
                    sys.stdout.flush()
                    continue
                    
                try:
                    df = data_engine.fetch_and_prepare_data(pair)
                    if df is None or len(df) < 2:
                        logger.info(f"[{pair}] ⚠️ Not enough data. Skipping.")
                        continue
                        
                    records = df.to_dict(orient='records')
                    latest_closed_candle = records[-2]
                    prev_closed_candle = records[-3]
                    
                    candle_time = latest_closed_candle['time']
                    
                    if last_processed_candle_time[pair] != candle_time:
                        last_processed_candle_time[pair] = candle_time
                        
                        # Log scanning status (No terminal print to prevent spam)
                        trend = "Bullish" if latest_closed_candle.get('15m_bias_bullish', False) else "Bearish"
                        scan_msg = f"Scanning {pair}... (15m Trend: {trend})"
                        logger.info(scan_msg)
                        
                        record_data(pair, latest_closed_candle)
                        
                        result = signal_engine.evaluate(latest_closed_candle, prev_closed_candle, pair)
                        
                        if result["signal"] != 0:
                            direction_str = 'LONG' if result['signal'] == 1 else 'SHORT'
                            signal_msg = f"VALID SIGNAL FOUND: {pair} | Type: {direction_str} | ML Win Prob: {result['ml_prob']*100:.1f}% | Entry: {result['fvg_entry']}"
                            
                            print(f"\n  [{pair}] ⚡ {signal_msg}")
                            logger.info(signal_msg)
                            
                            if not dry_run:
                                # Apply Dynamic Risk for Asian Scalper
                                risk_override = None
                                if result['strategy'] == "ASIAN":
                                    prob = result['ml_prob']
                                    if prob >= 0.70:
                                        risk_override = 1.0
                                    elif prob >= 0.60:
                                        risk_override = 0.75
                                    else:
                                        risk_override = 0.50
                                        
                                    # Equity Protection: Scale down risk if we already have floating exposure
                                    current_active_trades = get_active_trade_count()
                                    if current_active_trades > 0:
                                        risk_override = risk_override / (current_active_trades + 1)
                                        logger.info(f"[{pair}] Equity Protection: Reduced Asian risk to {risk_override:.2f}% because {current_active_trades} trades are already running.")
                                
                                trade_manager.place_limit_order(
                                    symbol=pair,
                                    direction=result["signal"],
                                    entry_price=result['fvg_entry'] if result['strategy'] == 'SNIPER' else result.get('entry', result['fvg_entry']), 
                                    sl=result['stop_loss'],
                                    tp=result['take_profit'],
                                    balance=current_balance,
                                    override_risk_percent=risk_override,
                                    strategy_name=result['strategy']
                                )
                            else:
                                print(f"  [DRY RUN] Would place {direction_str} Limit at {result['fvg_entry']}")
                                
                            brain_name = "Sniper V2 Brain" if result['strategy'] == 'SNIPER' else "Asian Scalper Brain"
                            NotificationCenter.notify(
                                f"⚡ <b>New Setup Found: {pair}</b>\n"
                                f"Brain: {brain_name}\n"
                                f"Type: {direction_str} Limit\n"
                                f"Entry: {result['fvg_entry']}\n"
                                f"SL: {result['stop_loss']} | TP: {result['take_profit']}\n"
                                f"AI Prob: {result['ml_prob']*100:.1f}%\n"
                                f"Mode: {'DRY RUN' if dry_run else 'LIVE'}"
                            )
                            
                            active_signals[pair] = {
                                "time_created": now_utc,
                                "signal": result
                            }
                            
                        if active_signals[pair]:
                            time_since_creation = (now_utc - active_signals[pair]['time_created']).total_seconds()
                            if time_since_creation > (15 * 60):
                                cancel_msg = f"Limit order expired (15 mins). Cancelling {pair}..."
                                print(f"  [{pair}] ⏳ {cancel_msg}")
                                logger.info(cancel_msg)
                                if not dry_run:
                                    trade_manager.cancel_all_pending_orders(pair)
                                active_signals[pair] = None
                                
                except Exception as e:
                    err_msg = f"ERROR during scan on {pair}: {e}"
                    print(f"  [{pair}] ❌ {err_msg}")
                    logger.error(err_msg, exc_info=True)
                            
            # Update Dashboard state every minute
            export_state(
                account_login=account_info.login,
                balance=current_balance,
                equity=acc.equity,
                total_profit=current_balance - start_balance,
                daily_trades=total_daily_trades,
                max_daily_trades=MAX_DAILY_TRADES,
                active_trades=get_active_trades_for_dashboard(),
                history=get_history_for_dashboard(), 
                phase_type=ACCOUNT_PHASE,
                profit_target_pct=PROFIT_TARGET_PCT if PROFIT_TARGET_PCT is not None else 0.0,
                max_daily_dd=max_daily_dd,
                max_global_dd=max_total_dd,
                daily_start_balance=daily_start_balance,
                peak_balance=peak_balance,
                news_calendar=news_engine.get_dashboard_schedule(),
                bot_status=sess_str,
                active_firm=ACTIVE_FIRM
            )
                            
            # Wait for next 1-minute candle with animation
            wait_for_next_minute(sess_str)
            
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
