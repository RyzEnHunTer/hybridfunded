# live_config_v2.py
# Configuration settings for the Live Bot Version 2 (Machine Learning SMC)

# 1. Trading Pairs
SNIPER_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDNZD",
    "AUDCAD",
    "EURGBP",
    "GBPJPY",
    "EURJPY"
]

ASIAN_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDCAD",
    "EURGBP"
]

# 2. Risk Management Parameters
SNIPER_RISK_PERCENT = 1.0     

# Prop Firm Config Loader
import os
import json

ACTIVE_FIRM = "FTMO_STANDARD_2STEP"
ACCOUNT_PHASE = "LIVE" # "CHALLENGE" or "LIVE"

ACTIVE_STATE_FILE = os.path.join(os.path.dirname(__file__), "active_firm_state.json")
try:
    if os.path.exists(ACTIVE_STATE_FILE):
        with open(ACTIVE_STATE_FILE, "r") as f:
            state_data = json.load(f)
            ACTIVE_FIRM = state_data.get("ACTIVE_FIRM", ACTIVE_FIRM)
            ACCOUNT_PHASE = state_data.get("ACCOUNT_PHASE", ACCOUNT_PHASE)
except Exception:
    pass

MAX_DAILY_DRAWDOWN_PERCENT = 4.0 
MAX_GLOBAL_DRAWDOWN_PERCENT = 8.0 
PROFIT_TARGET_PCT = None
NEWS_TRADING_ALLOWED = True
WEEKEND_HOLDING_ALLOWED = True
NEWS_PROFIT_CAP_PCT = None
CONSISTENCY_RULE_PCT = None

PRESETS_FILE = os.path.join(os.path.dirname(__file__), "prop_firm_presets.json")
try:
    with open(PRESETS_FILE, "r", encoding="utf-8") as f:
        _presets = json.load(f)
        if ACTIVE_FIRM in _presets:
            _firm_rules = _presets[ACTIVE_FIRM].get(ACCOUNT_PHASE, {})
            if _firm_rules.get("daily_dd_pct"): MAX_DAILY_DRAWDOWN_PERCENT = _firm_rules["daily_dd_pct"]
            if _firm_rules.get("max_dd_pct"): MAX_GLOBAL_DRAWDOWN_PERCENT = _firm_rules["max_dd_pct"]
            
            PROFIT_TARGET_PCT = _firm_rules.get("profit_target_pct")
            NEWS_TRADING_ALLOWED = _firm_rules.get("news_trading_allowed", True)
            WEEKEND_HOLDING_ALLOWED = _firm_rules.get("weekend_holding_allowed", True)
            NEWS_PROFIT_CAP_PCT = _firm_rules.get("news_profit_cap_pct")
            CONSISTENCY_RULE_PCT = _firm_rules.get("consistency_rule_pct")
except Exception as e:
    print(f"Warning: Failed to load prop firm presets: {e}") 

# Strict Prop Firm Equity Protection Limits
MAX_CONCURRENT_TRADES = 3
MAX_DAILY_TRADES = 4
MAX_TRADES_PER_PAIR = 1

# 3. Time Constraints (UTC)
# The bot only trades during London and New York overlaps
VALID_TRADING_HOURS_UTC = [7, 8, 11, 12, 13] 

# 4. News Filters (UTC)
# Block trading 15 mins before and after 8:30 AM EST (12:30 UTC) and 10:00 AM EST (14:00 UTC)
NEWS_BLOCKS_UTC = [
    {"hour": 12, "min_start": 15, "min_end": 45}, # 8:30 AM EST
    {"hour": 14, "min_start": 0, "min_end": 15}   # 10:00 AM EST
]

# 5. ML Model Paths
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(BASE_DIR, "models", "mtf_classifier.pkl")
FEATURES_PATH = os.path.join(BASE_DIR, "models", "mtf_features.pkl")
RECORDINGS_DIR = os.path.join(BASE_DIR, "data", "live_recordings")
