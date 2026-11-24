import pytest

from fatigue_calculator import (
    FatigueCalculator,
    calculate_ear,
    calculate_fatigue_risk,
    calculate_mar,
    classify_fatigue,
)


def test_calculate_ear_and_mar():
    eye = [(0, 0), (1, 2), (1, 2), (4, 0), (1, -2), (1, -2)]
    mouth = [(0, 0), (4, 0), (2, 3), (2, 4), (2, 1), (2, -1)]
    assert calculate_ear(eye) == pytest.approx(1.0)
    assert calculate_mar(mouth) == pytest.approx(0.875)


def test_weighted_risk_score_and_classification():
    assert calculate_fatigue_risk(100, 100, 100, 100) == 100
    assert classify_fatigue(20) == "NORMAL"
    assert classify_fatigue(40) == "CAUTION"
    assert classify_fatigue(60) == "HIGH RISK"
    assert classify_fatigue(79) == "HIGH RISK"
    assert classify_fatigue(80) == "CRITICAL"


def test_short_blink_does_not_count_as_prolonged_closure():
    calculator = FatigueCalculator()
    calculator.finish_calibration()

    calculator.assess(0.1, 0.1, 0.0, now=0.0)
    result = calculator.assess(0.1, 0.1, 0.0, now=0.2)

    assert result["eye_closures"] == 0
    assert result["eye_closure_event"] is False


def test_sustained_eye_closure_is_counted_once():
    calculator = FatigueCalculator()
    calculator.finish_calibration()
    calculator.assess(0.1, 0.1, 0.0, now=0.0)
    calculator.assess(0.1, 0.1, 0.0, now=1.6)
    result = calculator.assess(0.1, 0.1, 0.0, now=2.0)

    assert result["eye_closures"] == 1
    assert result["eye_closure_event"] is False


def test_sustained_yawn_is_counted_once_until_mouth_closes():
    calculator = FatigueCalculator()
    calculator.finish_calibration()
    calculator.assess(0.3, 0.55, 0.0, now=0.0)
    first_yawn = calculator.assess(0.3, 0.55, 0.0, now=2.1)
    held_yawn = calculator.assess(0.3, 0.55, 0.0, now=2.5)

    assert first_yawn["yawning_event"] is True
    assert held_yawn["yawning_event"] is False
    assert held_yawn["yawning_count"] == 1


def test_lost_face_is_not_classified_as_normal():
    result = FatigueCalculator().not_detected()
    assert result["status"] == "NOT DETECTED"
    assert result["risk_score"] == 100
