import logging
import os
import time

import cv2
import numpy as np

import config
from fatigue_calculator import calculate_ear, calculate_mar

try:
    import mediapipe as mp
except ImportError:
    mp = None


logger = logging.getLogger(__name__)
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)
MOUTH = (61, 291, 0, 13, 14, 17)


class DetectionUnavailableError(RuntimeError):
    pass


class CameraUnavailableError(RuntimeError):
    pass


class DetectionEngine:
    """Owns the webcam and MediaPipe; it does not calculate fatigue risk."""

    READ_RETRIES = 3
    READ_RETRY_DELAY = 0.05

    def __init__(self, camera_index=None):
        if mp is None:
            raise DetectionUnavailableError(
                "MediaPipe is unavailable; install the project requirements."
            )
        self.camera_index = config.WEBCAM_INDEX if camera_index is None else camera_index
        self.camera = None
        self.camera_backends = (
            [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
            if os.name == "nt"
            else [cv2.CAP_ANY]
        )
        self.camera_backend_index = 0
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def open(self):
        self._release_camera()
        backend_count = len(self.camera_backends)
        for offset in range(backend_count):
            backend_index = (self.camera_backend_index + offset) % backend_count
            backend = self.camera_backends[backend_index]
            camera = cv2.VideoCapture(self.camera_index, backend)
            if not camera.isOpened():
                camera.release()
                logger.warning(
                    "Webcam index %s did not open with backend %s",
                    self.camera_index,
                    backend,
                )
                continue

            camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.camera = camera
            self.camera_backend_index = backend_index
            logger.info(
                "Webcam opened at index %s with backend %s",
                self.camera_index,
                backend,
            )
            return

        raise CameraUnavailableError(
            f"Cannot open webcam index {self.camera_index} with available backends."
        )

    def read(self):
        if self.camera is None:
            raise CameraUnavailableError("The webcam has not been opened.")
        for attempt in range(self.READ_RETRIES):
            success, frame = self.camera.read()
            if success and frame is not None and frame.size:
                return True, frame
            if attempt + 1 < self.READ_RETRIES:
                time.sleep(self.READ_RETRY_DELAY)

        logger.warning(
            "Webcam index %s stopped returning frames; trying another backend",
            self.camera_index,
        )
        self.camera_backend_index = (
            self.camera_backend_index + 1
        ) % len(self.camera_backends)
        self.open()
        for attempt in range(self.READ_RETRIES):
            success, frame = self.camera.read()
            if success and frame is not None and frame.size:
                return True, frame
            if attempt + 1 < self.READ_RETRIES:
                time.sleep(self.READ_RETRY_DELAY)

        raise CameraUnavailableError(
            f"Webcam index {self.camera_index} could not return frames after reconnecting."
        )

    def _release_camera(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None

    def analyze_frame(self, frame):
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        if not results.multi_face_landmarks:
            return {
                "face_detected": False,
                "ear": 0.0,
                "mar": 0.0,
                "pitch": 0.0,
            }

        landmarks = results.multi_face_landmarks[0].landmark
        left_eye = [
            (landmarks[index].x * width, landmarks[index].y * height)
            for index in LEFT_EYE
        ]
        right_eye = [
            (landmarks[index].x * width, landmarks[index].y * height)
            for index in RIGHT_EYE
        ]
        mouth = [
            (landmarks[index].x * width, landmarks[index].y * height)
            for index in MOUTH
        ]
        ear = (calculate_ear(left_eye) + calculate_ear(right_eye)) / 2.0
        mar = calculate_mar(mouth)
        pitch = self._estimate_pitch(landmarks, width, height)
        return {
            "face_detected": True,
            "ear": ear,
            "mar": mar,
            "pitch": pitch,
            "landmarks": landmarks,
        }

    @staticmethod
    def _estimate_pitch(landmarks, width, height):
        image_points = np.array([
            (landmarks[index].x * width, landmarks[index].y * height)
            for index in (1, 152, 33, 263, 61, 291)
        ], dtype="double")
        model_points = np.array([
            (0.0, 0.0, 0.0),
            (0.0, -63.6, -12.5),
            (-43.3, 32.7, -26.0),
            (43.3, 32.7, -26.0),
            (-28.9, -28.4, -24.1),
            (28.9, -28.4, -24.1),
        ], dtype="double")
        camera_matrix = np.array([
            [width, 0, width / 2],
            [0, width, height / 2],
            [0, 0, 1],
        ], dtype="double")
        try:
            success, rotation_vector, _ = cv2.solvePnP(
                model_points,
                image_points,
                camera_matrix,
                np.zeros((4, 1)),
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not success:
                return 0.0
            rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
            return float(np.degrees(np.arctan2(
                rotation_matrix[2, 1], rotation_matrix[2, 2]
            )))
        except cv2.error:
            logger.exception("Head-pose estimation failed")
            return 0.0

    @staticmethod
    def draw_overlay(frame, measurements, result, calibrating=False):
        if measurements.get("face_detected"):
            landmarks = measurements.get("landmarks", ())
            for index in LEFT_EYE + RIGHT_EYE:
                x = int(landmarks[index].x * frame.shape[1])
                y = int(landmarks[index].y * frame.shape[0])
                cv2.circle(frame, (x, y), 2, (0, 255, 180), -1)

        if calibrating:
            lines = [
                "CALIBRATING - face the camera normally",
                f"EAR: {measurements.get('ear', 0.0):.2f}",
                "Status: NOT DETECTED",
            ]
        else:
            lines = [
                f"EAR: {result['ear']:.2f}  MAR: {result['mar']:.2f}",
                f"PERCLOS: {result['perclos']:.1f}%",
                f"Score: {result['risk_score']}/100  {result['status']}",
                (
                    f"Eye closures: {result['eye_closures']}  "
                    f"Yawns: {result['yawning_count']}  "
                    f"Nods: {result['head_nodding_count']}"
                ),
            ]
        for line_number, text in enumerate(lines):
            cv2.putText(
                frame,
                text,
                (16, 28 + line_number * 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 180),
                2,
            )
        if not measurements.get("face_detected"):
            cv2.putText(
                frame,
                "NO FACE DETECTED",
                (16, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )
        return frame

    def close(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        if self.face_mesh is not None:
            self.face_mesh.close()
            self.face_mesh = None
