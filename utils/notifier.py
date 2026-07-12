import requests
import json
import threading
import logging
from utils.account_manager import AccountManager

logger = logging.getLogger("Notifier")

class NotificationCenter:
    """Handles independent push notifications to Telegram or Discord."""
    
    _cached_config = None

    @staticmethod
    def notify(message: str):
        """Routes the message to the active platform asynchronously."""
        try:
            if NotificationCenter._cached_config is None:
                NotificationCenter._cached_config = AccountManager().get_or_create_notifications()
            config = NotificationCenter._cached_config
            platform = config.get("platform", "NONE").upper()
            
            if platform == "DISCORD" and config.get("discord_url"):
                threading.Thread(target=NotificationCenter._send_discord, args=(config["discord_url"], message), daemon=True).start()
                    
            elif platform == "TELEGRAM" and config.get("tg_token") and config.get("tg_chat_id"):
                threading.Thread(target=NotificationCenter._send_telegram, args=(config["tg_token"], config["tg_chat_id"], message), daemon=True).start()
        except Exception as e:
            logger.error(f"Notifier failed to read config: {e}")

    @staticmethod
    def _send_discord(webhook_url: str, message: str):
        try:
            import re
            # Convert HTML to Discord Markdown
            msg = message.replace('<b>', '**').replace('</b>', '**')
            msg = re.sub(r"<a href='[^']+'>([^<]+)</a>", r"\1", msg)
            
            payload = {"content": msg}
            headers = {"Content-Type": "application/json"}
            requests.post(webhook_url, data=json.dumps(payload), headers=headers, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")

    @staticmethod
    def _send_telegram(token: str, chat_id: str, message: str):
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
