"""
Live Bot Configuration — Single Source of Truth

All settings for the live MT5 trading bot are centralised here.
Change ONLY this file to tune behavior — no other module needs editing.
"""

from pathlib import Path

# ─── Project Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
LIVE_TRADE_LOG = DATA_DIR / "live_trade_log.csv"

# ─── 5. ML & DATA SETTINGS ──────────────────────────────────────────────────
MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "hybrid_xgboost.pkl"
FEATURES_PATH = PROJECT_ROOT / "ml" / "models" / "hybrid_features.pkl"
SCALER_PATH = PROJECT_ROOT / "ml" / "models" / "hybrid_scaler.pkl"

ML_PROBABILITY_THRESHOLD = 0.65
RETRAIN_INTERVAL_DAYS = 14
MIN_TRADES_FOR_RETRAIN = 30
RETRAIN_MIN_ACCURACY = 0.60

# ─── 6. NOTIFICATION & DASHBOARD ───────────────────────────────────────────
NOTIFICATION_PLATFORM = "NONE" # Options: "NONE", "DISCORD", "TELEGRAM"
DISCORD_WEBHOOK_URL = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Ensure directories exist
for d in [MODELS_DIR, LOGS_DIR, DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── MT5 Connection ──────────────────────────────────────────────────────────
MT5_LOGIN = 0           # Your MT5 account number (set before running)
MT5_PASSWORD = ""       # Your MT5 password (set before running)
MT5_SERVER = ""         # Your broker's server name (set before running)
MT5_PATH = ""           # Path to terminal64.exe (leave empty for auto-detect)

# ─── Trading Pairs ────────────────────────────────────────────────────────────
BASE_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",   # Majors
    "AUDNZD", "AUDCAD", "EURGBP",   # Asian Mean Reversion Specialists
    "GBPJPY", "EURJPY"              # London Breakout Specialists
]

# This dict will be populated at runtime by mt5_connector.auto_detect_symbols()
# Maps our clean pair name -> broker's actual symbol name (e.g. "EURUSD" -> "EURUSD.pro")
SYMBOL_MAP = {}

# ─── Dynamic Volatility Matrix ───────────────────────────────────────────────
# ATR multiplier for trailing stop distance — tuned per pair's noise profile
DYNAMIC_ATR_MULTIPLIER = {
    "EURUSD": 1.5,   # Smooth, tight trail
    "GBPUSD": 2.0,   # Standard trail
    "USDJPY": 2.0,   # Standard trail
    "AUDNZD": 1.5,   # Tight range trail
    "AUDCAD": 1.5,   # Tight range trail
    "EURGBP": 1.5,   # Tight range trail
    "GBPJPY": 3.0,   # Volatile "Widowmaker", wide trail to survive wicks
    "EURJPY": 2.5    # Volatile cross, medium-wide trail
}

# ─── ML Features ─────────────────────────────────────────────────────────────
FEATURE_COLS = [
    'hour', 'adx', 'rsi', 'atr',
    'bb_upper', 'bb_lower', 'bb_mid',
    'asian_high', 'asian_low', 'direction'
]

# ─── Trade Identity ──────────────────────────────────────────────────────────
MAGIC_NUMBER = 777888   # Unique ID attached to every trade — never change this

# ─── Risk Management ─────────────────────────────────────────────────────────
RISK_PER_TRADE = 0.01        # 1% risk per trade
MAX_DAILY_DD = 0.035         # 3.5% — panic close before 4.0% prop firm limit
MAX_TOTAL_DD = 0.075         # 7.5% — hard stop before 8.0% prop firm limit

# ─── Trade Limits ─────────────────────────────────────────────────────────────
MAX_OPEN_POSITIONS = 3       # Maximum simultaneous open trades across all pairs
MAX_TRADES_PER_PAIR_PER_DAY = 2   # Cap per-pair entries to prevent overtrading
MAX_TRADES_PER_DAY = 20      # Increased significantly to let winners run
COOLDOWN_CANDLES = 4         # 4 x 15min = 1 hour cooldown after each trade per pair

# ─── Spread Filter (in pips) ─────────────────────────────────────────────────
MAX_SPREAD_PIPS = {
    "EURUSD": 3.0,
    "GBPUSD": 3.0,
    "USDJPY": 3.0,
    "AUDNZD": 5.0,
    "AUDCAD": 5.0,
    "EURGBP": 3.0,
    "GBPJPY": 5.0,
    "EURJPY": 5.0
}

# ─── Session Windows (UTC hours) ─────────────────────────────────────────────
ASIAN_START = 22         # 22:00 UTC
ASIAN_END = 6            # 06:00 UTC
LONDON_NY_START = 7      # 07:00 UTC
LONDON_NY_END = 15       # 15:00 UTC

# ─── Weekend Kill Switch ─────────────────────────────────────────────────────
FRIDAY_KILL_HOUR = 20    # Close all trades at Friday 20:00 UTC

# ─── ML Threshold ─────────────────────────────────────────────────────────────
# ML_PROBABILITY_THRESHOLD is defined at the top of the file (0.85)

# ─── Auto-Retrainer ──────────────────────────────────────────────────────────
RETRAIN_INTERVAL_DAYS = 14        # Retrain every 2 weeks
RETRAIN_MIN_TRADES = 50           # Minimum new trades before allowing retrain
RETRAIN_MIN_ACCURACY = 0.55       # New model must beat 55% accuracy to replace old one
RETRAIN_LOOKBACK_DAYS = 90        # Rolling window: train on last 90 days of data

# ─── Pip Sizes ────────────────────────────────────────────────────────────────
PIP_SIZES = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
    "AUDNZD": 0.0001,
    "AUDCAD": 0.0001,
    "EURGBP": 0.0001,
    "GBPJPY": 0.01,
    "EURJPY": 0.01
}

# ─── Timeframe ────────────────────────────────────────────────────────────────
TIMEFRAME = "15m"
CANDLE_COUNT = 1000      # Fetch 10 days of candles for perfect indicator warmup

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = LOGS_DIR / "live_bot.log"
