<div align="center">
  <h1>🚀 HUNTER ML BOT | V2</h1>
  <p><strong>Advanced Machine Learning & SMC Prop Firm Trading Engine</strong></p>
</div>

---

## 📖 Overview

The **Hunter ML Bot V2** is a fully automated algorithmic trading system built in Python for MetaTrader 5. It leverages Machine Learning (XGBoost/RandomForest) to classify high-probability trade setups based on Smart Money Concepts (SMC).

Designed specifically for **Proprietary Trading Firms** (e.g., FTMO, FundedNext, MyForexFunds), this bot includes advanced, hard-coded risk management safeguards to ensure accounts never breach daily or maximum drawdown limits.

## ✨ Key Features

- **Hybrid Trading Engines:**
  - **Sniper V2 (Daytime):** Trades the London and New York sessions using Multi-Timeframe (MTF) SMC alignments (FVGs, Order Blocks, Liquidity Sweeps) validated by an ML classifier.
  - **Asian Scalper (Nighttime):** A separate ML model dedicated to mean-reverting structures during the low-volatility Asian session.
- **Strict Prop Firm Risk Management:** 
  - Dynamic Daily Drawdown & Global Drawdown Circuit Breakers.
  - Automated lot sizing based on account size and specific risk % per trade.
  - Trade concurrency limits (e.g., Max 2 trades at a time, Max 1 per pair).
- **High-Impact News Avoidance:** Live synchronization with the ForexFactory calendar to pause trading exactly X minutes before and after high-impact (`red` folder) news events.
- **Weekend Liquidation:** Automatically closes all open positions on Friday evenings to avoid weekend gap exposure and prop firm weekend holding violations.
- **Real-time Web Dashboard:** A built-in Flask web server serving a stunning, real-time UI dashboard that tracks live PnL, active trades, historical performance, and risk metrics.

## 📂 Architecture

```text
hybrid_engine/
├── core/
│   ├── data_engine.py       # MT5 data fetching & MTF feature generation
│   ├── signal_engine.py     # SMC logic & ML classification
│   ├── trade_manager.py     # Execution, partials, trailing stops, FVG limit orders
│   └── news_engine.py       # ForexFactory XML parsing & news blocking
├── utils/
│   ├── account_manager.py   # Prop firm rule tracking & account state
│   ├── notifier.py          # Telegram/Discord integration
│   └── state_exporter.py    # Exports bot state to JSON for the dashboard
├── config/
│   ├── settings.py          # Main bot configurations & risk params
│   ├── prop_firm_presets.json # Firm-specific rule definitions
│   └── rule_scraper.py      # Automated scraping of prop firm rules
├── models/
│   ├── mtf_classifier.pkl   # ML Model for Sniper V2
│   └── asian_brain.xgb      # XGBoost Model for Asian Scalper
├── web/
│   ├── server.py            # Flask backend server
│   └── public/              # Real-time HTML/JS/CSS frontend dashboard
└── main.py                  # Primary entry point & orchestration loop
```

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+** (64-bit required for MT5 integration)
- **MetaTrader 5** terminal installed and running with Auto-Trading enabled.
- A supported Forex Broker/Prop Firm account connected to MT5.

### Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/RyzEnHunTer/hybridfunded.git
   cd hybridfunded
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Engine:**
   Ensure your MT5 terminal is open, logged in, and has the necessary currency pairs available in the Market Watch.
   ```bash
   python main.py
   ```

4. **Access the Dashboard:**
   Once running, the terminal will provide a Cloudflare URL or localhost port (default `5055`). Open the link in your browser to monitor the bot in real-time.

---

<div align="center">
  <i>Disclaimer: This software is for educational and research purposes. Trading foreign exchange on margin carries a high level of risk and may not be suitable for all investors.</i>
</div>
