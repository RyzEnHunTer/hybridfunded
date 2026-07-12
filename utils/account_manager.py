import json
import os
from pathlib import Path
import logging

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

logger = logging.getLogger("AccountManager")

class AccountManager:
    """
    Manages persistent prop firm rules (Phase 1, Phase 2, Funded) per MT5 login.
    """
    def __init__(self):
        self.accounts_file = DATA_DIR / "accounts.json"
        self.notifications_file = DATA_DIR / "notifications.json"
        self.accounts = self._load_accounts()

    def _load_accounts(self) -> dict:
        if self.accounts_file.exists():
            try:
                with open(self.accounts_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load accounts.json: {e}")
        return {}

    def _save_accounts(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.accounts_file, "w") as f:
                json.dump(self.accounts, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save accounts.json: {e}")

    def get_or_create_account(self, login: int, balance: float, force_prompt=False) -> dict:
        """
        Retrieves account config. If it doesn't exist or force_prompt is True, prompts the user.
        """
        login_str = str(login)
        if not force_prompt and login_str in self.accounts:
            return self.accounts[login_str]

        # New account - trigger interactive setup
        print("\n" + "=" * 60)
        if force_prompt:
            print(f"  🔔 UPDATING ACCOUNT RULES: {login}")
        else:
            print(f"  🔔 NEW ACCOUNT DETECTED: {login}")
        print("=" * 60)
        
        if not force_prompt:
            print("  This account is not in the database. Please configure the Prop Firm rules.\n")
        
        while True:
            phase = input("  Phase Type (1=Phase 1, 2=Phase 2, 3=Funded/Passed): ").strip()
            if phase in ["1", "2", "3"]:
                break
            print("  Invalid choice. Enter 1, 2, or 3.")

        if phase == "3":
            phase_type = "FUNDED"
            profit_target_pct = 0.0
            print(f"  --> Account marked as FUNDED (No profit target).")
        else:
            phase_type = f"PHASE {phase}"
            while True:
                try:
                    profit_target_pct = float(input(f"  Profit Target % for Phase {phase} (e.g. 8.0): "))
                    break
                except ValueError:
                    print("  Invalid number. Please enter a percentage like 8.0")
        
        while True:
            try:
                max_daily_dd = float(input("  Max Daily Drawdown % (e.g. 5.0): "))
                break
            except ValueError:
                print("  Invalid number. Please enter a percentage like 5.0")
                
        while True:
            try:
                max_total_dd = float(input("  Max Total Drawdown % (e.g. 10.0): "))
                break
            except ValueError:
                print("  Invalid number. Please enter a percentage like 10.0")

        # Convert user inputs (5.0) to internal representation (0.05)
        config = {
            "phase_type": phase_type,
            "starting_balance": balance,
            "profit_target_pct": profit_target_pct,
            "max_daily_dd": max_daily_dd,
            "max_total_dd": max_total_dd
        }

        self.accounts[login_str] = config
        self._save_accounts()
        print("\n  ✅ Account rules saved successfully!")
        
        return config

    def update_account_rules(self, login: int, updates: dict):
        """Updates specific fields in an account and saves."""
        login_str = str(login)
        if login_str in self.accounts:
            self.accounts[login_str].update(updates)
            self._save_accounts()

    def get_or_create_notifications(self, force_prompt=False) -> dict:
        """
        Retrieves global notification settings. If they don't exist, prompts the user.
        """
        if not force_prompt and self.notifications_file.exists():
            try:
                with open(self.notifications_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load notifications.json: {e}")
        
        # New notification setup
        print("\n" + "=" * 60)
        print("  🔔 NOTIFICATION ENGINE SETUP")
        print("=" * 60)
        print("  Where should the bot send trade alerts and dashboard links?")
        print("  [1] Telegram")
        print("  [2] Discord Webhook")
        print("  [3] None")
        
        while True:
            choice = input("  Choice (1/2/3): ").strip()
            if choice in ["1", "2", "3"]:
                break
            print("  Invalid choice.")
            
        config = {"platform": "NONE", "discord_url": "", "tg_token": "", "tg_chat_id": ""}
        
        if choice == "1":
            config["platform"] = "TELEGRAM"
            config["tg_token"] = input("  Telegram Bot Token: ").strip()
            config["tg_chat_id"] = input("  Telegram Chat ID: ").strip()
        elif choice == "2":
            config["platform"] = "DISCORD"
            config["discord_url"] = input("  Discord Webhook URL: ").strip()
            
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.notifications_file, "w") as f:
                json.dump(config, f, indent=4)
            print("  ✅ Notification settings saved successfully!")
        except Exception as e:
            print(f"Failed to save notifications.json: {e}")
            logger.error(f"Failed to save notifications.json: {e}")
            
        return config
