import config
from notification_service import NotificationGate, NotificationService


def test_critical_alert_requires_ten_continuous_seconds(monkeypatch):
    monkeypatch.setattr(config, "CRITICAL_ALERT_DELAY_SECONDS", 10.0)
    gate = NotificationGate()

    assert gate.should_send_critical("CRITICAL", 0.0) is False
    assert gate.should_send_critical("CRITICAL", 9.9) is False
    assert gate.should_send_critical("HIGH RISK", 9.95) is False
    assert gate.should_send_critical("CRITICAL", 10.0) is False
    assert gate.should_send_critical("CRITICAL", 20.0) is True
    assert gate.should_send_critical("CRITICAL", 21.0) is False


def test_critical_alert_rearms_after_normal_or_caution(monkeypatch):
    monkeypatch.setattr(config, "CRITICAL_ALERT_DELAY_SECONDS", 10.0)
    gate = NotificationGate()
    gate.should_send_critical("CRITICAL", 0.0)
    assert gate.should_send_critical("CRITICAL", 10.0) is True
    assert gate.should_send_critical("CAUTION", 11.0) is False
    assert gate.should_send_critical("CRITICAL", 12.0) is False
    assert gate.should_send_critical("CRITICAL", 22.0) is True


def test_yawn_alert_triggers_once_above_four_and_rearms_after_window(monkeypatch):
    monkeypatch.setattr(config, "YAWN_ALERT_COUNT_THRESHOLD", 4)
    monkeypatch.setattr(config, "YAWN_ALERT_WINDOW_SECONDS", 60.0)
    gate = NotificationGate()

    for now in (0, 10, 20, 30):
        assert gate.observe_yawn(True, now) == (now // 10 + 1, False)
    assert gate.observe_yawn(True, 40) == (5, True)
    assert gate.observe_yawn(False, 41) == (5, False)
    assert gate.observe_yawn(False, 61) == (4, False)
    assert gate.observe_yawn(True, 62) == (5, True)


def test_yawn_advisory_contains_requested_message(monkeypatch):
    monkeypatch.setattr(config, "NOTIFICATION_ENABLED", True)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "12345")
    requests = []

    class SuccessfulResponse:
        ok = True

        @staticmethod
        def json():
            return {"ok": True}

    def fake_post(url, json, timeout):
        requests.append((url, json, timeout))
        return SuccessfulResponse()

    monkeypatch.setattr("notification_service.requests.post", fake_post)

    assert NotificationService().send_yawn_advisory(5) is True
    assert "You seem tired. Drink some water or rest for a while." in (
        requests[0][1]["text"]
    )
