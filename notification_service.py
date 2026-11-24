import logging
from collections import deque
from datetime import datetime

import requests

import config


logger = logging.getLogger(__name__)


class NotificationGate:
    def __init__(self):
        self.critical_started_at = None
        self.critical_latched = False
        self.yawn_latched = False
        self.yawn_event_times = deque()

    def should_send_critical(self, status, now):
        if status != "CRITICAL":
            self.critical_started_at = None
            if status in ("NORMAL", "CAUTION"):
                self.critical_latched = False
            return False

        if self.critical_started_at is None:
            self.critical_started_at = now
        if (
            not self.critical_latched
            and now - self.critical_started_at >= config.CRITICAL_ALERT_DELAY_SECONDS
        ):
            self.critical_latched = True
            return True
        return False

    def observe_yawn(self, yawning_event, now):
        if yawning_event:
            self.yawn_event_times.append(now)
        cutoff = now - config.YAWN_ALERT_WINDOW_SECONDS
        while self.yawn_event_times and self.yawn_event_times[0] < cutoff:
            self.yawn_event_times.popleft()

        recent_yawns = len(self.yawn_event_times)
        if recent_yawns <= config.YAWN_ALERT_COUNT_THRESHOLD:
            self.yawn_latched = False
            return recent_yawns, False
        if self.yawn_latched:
            return recent_yawns, False
        self.yawn_latched = True
        return recent_yawns, True


class NotificationService:
    def send_critical(self, risk_score, reasons, detected_at=None):
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
        return self._send_message(text, "critical guardian alert")

    def send_yawn_advisory(self, recent_yawns, detected_at=None):
        detected_at = detected_at or datetime.now().astimezone()
        text = (
            "DRIVE SAFE ADVISORY\n\n"
            "You seem tired. Drink some water or rest for a while.\n\n"
            f"Yawns in the last minute: {recent_yawns}\n"
            f"Time: {detected_at.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        return self._send_message(text, "yawn advisory")

    def _send_message(self, text, alert_name):
        if not config.NOTIFICATION_ENABLED:
            logger.info("Guardian notifications are disabled")
            return False
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            logger.error("Telegram token or guardian chat ID is not configured")
            return False

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
            logger.info("Telegram confirmed the %s", alert_name)
            return True

        logger.error(
            "Telegram did not confirm delivery (HTTP %s): %s",
            response.status_code,
            payload.get("description", "unsuccessful API response"),
        )
        return False
