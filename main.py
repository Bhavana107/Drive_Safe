import logging
from pathlib import Path
import sqlite3
import threading
import time
from datetime import datetime

import cv2

import config
import database
from arduino_controller import ArduinoController
from detection_engine import (
    CameraUnavailableError,
    DetectionEngine,
    DetectionUnavailableError,
)
from fatigue_calculator import FatigueCalculator
from notification_service import NotificationService


logger = logging.getLogger(__name__)
WINDOW_NAME = "DRIVE SAFE 2.0 - Live Detection"


def configure_logging():
    Path(config.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _now_text():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _start_calibration_result(calculator, measurements, seconds_remaining):
    result = calculator.not_detected(
        f"Calibration in progress: {seconds_remaining} seconds remaining."
    )
    result["face_detected"] = bool(measurements["face_detected"])
    result["ear"] = round(float(measurements["ear"]), 3)
    result["mar"] = round(float(measurements["mar"]), 3)
    return result


def run_detection():
    configure_logging()
    arduino = ArduinoController()
    detector = FatigueCalculator()
    notifier = NotificationService()
    engine = None
    session_id = None
    session_started = time.monotonic()
    total_alerts = 0
    maximum_risk_score = 0
    previous_status = None
    critical_latched = False
    last_sample_at = 0.0
    last_published_status = None
    exit_code = 0
    failure_message = None

    try:
        database.initialize_database()
        session_id = database.start_session(_now_text())
        connected = arduino.connect()
        logger.info("Arduino status: %s", arduino.status_name())
        if not connected and not arduino.simulation:
            logger.warning(
                "AI detection will continue without Arduino output; port is %s",
                arduino.port or "not configured",
            )

        engine = DetectionEngine()
        engine.open()
        calibration_started = time.monotonic()
        logger.info("AI detection started; use q or Esc in the webcam window to stop")

        while True:
            success, frame = engine.read()
            if not success or frame is None:
                raise CameraUnavailableError("The webcam stopped returning frames.")

            measurements = engine.analyze_frame(frame)
            now = time.monotonic()
            calibrating = not detector.calibrated

            if calibrating:
                if measurements["face_detected"]:
                    detector.add_calibration_sample(measurements["ear"])
                elapsed = now - calibration_started
                if elapsed >= config.CALIBRATION_SECONDS:
                    calibration = detector.finish_calibration()
                    if calibration["baseline_ear"] is not None:
                        database.save_calibration(
                            calibration["baseline_ear"],
                            calibration["eye_threshold"],
                            _now_text(),
                        )
                    logger.info(
                        "Calibration complete: %s samples, EAR threshold %.3f",
                        calibration["sample_count"],
                        calibration["eye_threshold"],
                    )
                    calibrating = False
                else:
                    remaining = max(
                        0, int(config.CALIBRATION_SECONDS - elapsed + 0.99)
                    )
                    result = _start_calibration_result(
                        detector, measurements, remaining
                    )

            if not calibrating and detector.calibrated:
                if measurements["face_detected"]:
                    result = detector.assess(
                        measurements["ear"],
                        measurements["mar"],
                        measurements["pitch"],
                        now=now,
                    )
                else:
                    result = detector.not_detected()

            result["calibrating"] = calibrating
            result["updated_at"] = _now_text()
            previous = previous_status
            status = result["status"]
            if status in ("HIGH RISK", "CRITICAL") and status != previous:
                total_alerts += 1
            if not calibrating and result["status"] != "NOT DETECTED":
                maximum_risk_score = max(
                    maximum_risk_score, result["risk_score"]
                )

            event_types = []
            if status != previous:
                event_types.append("status")
            has_behavior_event = any((
                result["eye_closure_event"],
                result["yawning_event"],
                result["head_nodding_event"],
            ))
            if has_behavior_event:
                event_types.append("behavior")
            if session_id is not None and event_types:
                event_type = "mixed" if len(event_types) == 2 else event_types[0]
                database.insert_fatigue_event(
                    session_id, result["updated_at"], result, event_type
                )

            if status == "CRITICAL" and not critical_latched:
                threading.Thread(
                    target=notifier.send_critical,
                    args=(result["risk_score"], result["reasons"]),
                    daemon=False,
                ).start()
                critical_latched = True
            elif status in ("NORMAL", "CAUTION"):
                critical_latched = False
            previous_status = status

            arduino.send_status(status)
            arduino_status = arduino.status_name()
            should_sample = now - last_sample_at >= config.PUBLISH_INTERVAL
            if status != last_published_status or should_sample:
                database.publish_state(
                    result,
                    engine_running=True,
                    arduino_status=arduino_status,
                    updated_at=result["updated_at"],
                )
                last_published_status = status
            if should_sample and session_id is not None:
                database.insert_detection_sample(
                    session_id, result["updated_at"], result
                )
                last_sample_at = now

            result["total_alerts"] = total_alerts
            result["maximum_risk_score"] = maximum_risk_score
            result["arduino_status"] = arduino_status
            engine.draw_overlay(frame, measurements, result, calibrating)
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    except KeyboardInterrupt:
        logger.info("AI detection stopped by keyboard interrupt")
    except (
        CameraUnavailableError,
        DetectionUnavailableError,
        cv2.error,
        RuntimeError,
    ) as error:
        logger.exception("AI detection stopped: %s", error)
        failure_message = str(error)
        exit_code = 1
    except sqlite3.Error:
        logger.exception("Database operation failed in the AI engine")
        failure_message = "Database operation failed; see the engine log."
        exit_code = 1
    finally:
        arduino.disconnect(send_safe=True)
        if engine is not None:
            try:
                engine.close()
            except (cv2.error, RuntimeError):
                logger.exception("Could not close the detection engine cleanly")
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            logger.exception("Could not close the OpenCV window cleanly")

        final_result = detector.not_detected(
            failure_message or "AI engine is not running"
        )
        try:
            database.publish_state(
                final_result,
                engine_running=False,
                arduino_status=arduino.status_name(),
                updated_at=_now_text(),
            )
            if session_id is not None:
                database.end_session(
                    session_id,
                    _now_text(),
                    int(time.monotonic() - session_started),
                    total_alerts,
                    maximum_risk_score,
                )
        except sqlite3.Error:
            logger.exception("Could not save final AI engine state")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run_detection())
