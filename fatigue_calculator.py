from collections import Counter, deque
from statistics import median
import math
import time

import config


def euclidean(point_a, point_b):
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def calculate_ear(eye_points):
    if len(eye_points) != 6:
        return 0.0
    vertical_one = euclidean(eye_points[1], eye_points[5])
    vertical_two = euclidean(eye_points[2], eye_points[4])
    horizontal = euclidean(eye_points[0], eye_points[3])
    if horizontal == 0:
        return 0.0
    return (vertical_one + vertical_two) / (2.0 * horizontal)


def calculate_mar(mouth_points):
    if len(mouth_points) != 6:
        return 0.0
    vertical = (
        euclidean(mouth_points[2], mouth_points[5])
        + euclidean(mouth_points[3], mouth_points[4])
    ) / 2.0
    horizontal = euclidean(mouth_points[0], mouth_points[1])
    if horizontal == 0:
        return 0.0
    return vertical / horizontal


def calculate_fatigue_risk(eye_score, perclos_score, yawning_score, nodding_score):
    components = (
        (eye_score, 0.40),
        (perclos_score, 0.25),
        (yawning_score, 0.20),
        (nodding_score, 0.15),
    )
    score = sum(max(0.0, min(100.0, value)) * weight
                for value, weight in components)
    return int(round(max(0.0, min(100.0, score))))


def classify_fatigue(score):
    if score >= config.RISK_CRITICAL_THRESHOLD:
        return "CRITICAL"
    if score >= config.RISK_HIGH_THRESHOLD:
        return "HIGH RISK"
    if score >= config.RISK_CAUTION_THRESHOLD:
        return "CAUTION"
    return "NORMAL"


class FatigueCalculator:
    """Turns facial measurements into smoothed fatigue status and event counts."""

    def __init__(self):
        self.eye_threshold = config.EYE_CLOSURE_THRESHOLD
        self.baseline_ear = None
        self.calibrated = False
        self.calibration_samples = []
        self.perclos_samples = deque()
        self.eye_closure_started = None
        self.eye_closure_recorded = False
        self.eye_closures = 0
        self.yawn_started = None
        self.yawn_recorded = False
        self.yawning_count = 0
        self.yawn_event_times = deque()
        self.nod_started = None
        self.nod_recorded = False
        self.head_nodding_count = 0
        self.nod_event_times = deque()
        self.smoothed_score = 0.0
        self.status_history = deque(maxlen=5)
        self.status = "NOT DETECTED"

    def add_calibration_sample(self, ear):
        if not self.calibrated and 0.05 < ear < 0.8:
            self.calibration_samples.append(float(ear))

    def finish_calibration(self):
        if len(self.calibration_samples) >= 20:
            self.baseline_ear = median(self.calibration_samples)
            self.eye_threshold = max(0.12, min(0.35, self.baseline_ear * 0.78))
        self.calibrated = True
        return {
            "baseline_ear": self.baseline_ear,
            "eye_threshold": self.eye_threshold,
            "sample_count": len(self.calibration_samples),
        }

    def not_detected(self, message="No face detected"):
        self.eye_closure_started = None
        self.eye_closure_recorded = False
        self.yawn_started = None
        self.yawn_recorded = False
        self.nod_started = None
        self.nod_recorded = False
        self.perclos_samples.clear()
        self.status_history.clear()
        self.smoothed_score = 0.0
        self.status = "NOT DETECTED"
        return {
            "face_detected": False,
            "ear": 0.0,
            "mar": 0.0,
            "perclos": 0.0,
            "eye_closed": False,
            "eye_closure_event": False,
            "eye_closures": self.eye_closures,
            "sleeping": False,
            "yawning": False,
            "yawning_event": False,
            "yawning_count": self.yawning_count,
            "head_nodding": False,
            "head_nodding_event": False,
            "head_nodding_count": self.head_nodding_count,
            "risk_score": 100,
            "status": "NOT DETECTED",
            "reasons": [],
            "message": message,
        }

    def assess(self, ear, mar, pitch, now=None):
        now = time.monotonic() if now is None else now
        eye_sample_closed = ear < self.eye_threshold
        self.perclos_samples.append((now, eye_sample_closed))
        cutoff = now - config.PERCLOS_WINDOW
        while self.perclos_samples and self.perclos_samples[0][0] < cutoff:
            self.perclos_samples.popleft()
        perclos = (
            100.0 * sum(closed for _, closed in self.perclos_samples)
            / len(self.perclos_samples)
            if self.perclos_samples else 0.0
        )

        eye_closure_event = False
        eye_duration = 0.0
        if eye_sample_closed:
            if self.eye_closure_started is None:
                self.eye_closure_started = now
            eye_duration = now - self.eye_closure_started
        else:
            self.eye_closure_started = None
            self.eye_closure_recorded = False
        eye_closed = eye_duration >= config.EYE_CLOSURE_DURATION
        if eye_closed and not self.eye_closure_recorded:
            self.eye_closure_recorded = True
            self.eye_closures += 1
            eye_closure_event = True
        sleeping = eye_duration >= config.SUSTAINED_SLEEPING_SECONDS

        yawning_event = False
        if mar >= config.YAWN_MAR_THRESHOLD:
            if self.yawn_started is None:
                self.yawn_started = now
            if (now - self.yawn_started >= config.YAWNING_DURATION
                    and not self.yawn_recorded):
                self.yawn_recorded = True
                self.yawning_count += 1
                self.yawn_event_times.append(now)
                yawning_event = True
        else:
            self.yawn_started = None
            self.yawn_recorded = False
        yawning = self.yawn_recorded

        head_nodding_event = False
        if pitch > config.HEAD_NOD_PITCH_THRESHOLD:
            if self.nod_started is None:
                self.nod_started = now
            if (now - self.nod_started >= config.HEAD_NOD_DURATION
                    and not self.nod_recorded):
                self.nod_recorded = True
                self.head_nodding_count += 1
                self.nod_event_times.append(now)
                head_nodding_event = True
        else:
            self.nod_started = None
            self.nod_recorded = False
        head_nodding = self.nod_recorded

        while self.yawn_event_times and self.yawn_event_times[0] < cutoff:
            self.yawn_event_times.popleft()
        while self.nod_event_times and self.nod_event_times[0] < cutoff:
            self.nod_event_times.popleft()

        eye_score = 0.0
        if eye_closed:
            eye_score = min(
                100.0,
                70.0 + 20.0 * max(0.0, eye_duration - config.EYE_CLOSURE_DURATION),
            )
        perclos_score = min(100.0, max(0.0, (perclos - 5.0) * 4.0))
        yawn_score = min(100.0, 30.0 * len(self.yawn_event_times))
        nodding_score = min(100.0, 35.0 * len(self.nod_event_times))
        raw_score = calculate_fatigue_risk(
            eye_score, perclos_score, yawn_score, nodding_score
        )
        self.smoothed_score = 0.65 * self.smoothed_score + 0.35 * raw_score
        if sleeping:
            self.smoothed_score = max(
                self.smoothed_score, config.RISK_CRITICAL_THRESHOLD
            )

        candidate = classify_fatigue(round(self.smoothed_score))
        self.status_history.append(candidate)
        counts = Counter(self.status_history)
        stable_status, stable_count = counts.most_common(1)[0]
        if sleeping:
            self.status = "CRITICAL"
        elif stable_count >= 3 or len(self.status_history) < 3:
            self.status = stable_status

        reasons = []
        if eye_closed:
            reasons.append("prolonged eye closure")
        if sleeping:
            reasons.append("sustained eye closure or sleeping")
        if yawning:
            reasons.append("yawning")
        if head_nodding:
            reasons.append("head nodding")

        return {
            "face_detected": True,
            "ear": round(float(ear), 3),
            "mar": round(float(mar), 3),
            "perclos": round(perclos, 1),
            "eye_closed": eye_closed,
            "eye_closure_event": eye_closure_event,
            "eye_closures": self.eye_closures,
            "sleeping": sleeping,
            "yawning": yawning,
            "yawning_event": yawning_event,
            "yawning_count": self.yawning_count,
            "head_nodding": head_nodding,
            "head_nodding_event": head_nodding_event,
            "head_nodding_count": self.head_nodding_count,
            "risk_score": int(round(self.smoothed_score)),
            "status": self.status,
            "reasons": reasons,
            "message": "",
        }
