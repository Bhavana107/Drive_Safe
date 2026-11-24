import logging
from datetime import datetime

import requests

import config


logger = logging.getLogger(__name__)


class NotificationService:
    def send_critical(self, risk_score, reasons, detected_at=None):
        if not config.NOTIFICATION_ENABLED:
            logger.info("Guardian notifications are disabled")
            return False
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            logger.error("Telegram token or guardian chat ID is not configured")
            return False

        detected_at = detected_at or datetime.now().astimezone()
        reason_text = ", ".join(reasons) if reasons else "critical fatigue score"
        text = (
            "DRIVE SAFE ALERT\n\n"
            "Critical drowsiness detected!\n\n"
            f"Possible {reason_text}.\n\n"
            f"Fatigue Score: {risk_score}/100\n"
            "Risk Level: CRITICAL\n"
            f"Time: {detected_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
            "Please check on the driver immediately."
        )
        url = (
            "https://api.telegram.org/bot"
            f"{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        )
        try:
            response = requests.post(
                url,
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
                timeout=5,
            )
        except requests.RequestException as error:
            logger.error("Telegram request failed (%s)", type(error).__name__)
            return False

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.ok and payload.get("ok") is True:
            logger.info("Telegram confirmed the critical guardian alert")
            return True

        logger.error(
            "Telegram did not confirm delivery (HTTP %s): %s",
            response.status_code,
            payload.get("description", "unsuccessful API response"),
        )
        return False
