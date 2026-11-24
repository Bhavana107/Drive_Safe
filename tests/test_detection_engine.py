from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from detection_engine import DetectionEngine


class FakeCamera:
    def __init__(self, reads, opened=True):
        self.reads = list(reads)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return self.reads.pop(0) if self.reads else (False, None)

    def set(self, _property, _value):
        return True

    def release(self):
        self.released = True


def _engine(camera):
    engine = object.__new__(DetectionEngine)
    engine.camera_index = 0
    engine.camera = camera
    engine.camera_backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    engine.camera_backend_index = 0
    return engine


def test_read_retries_transient_camera_frame_failure(monkeypatch):
    monkeypatch.setattr("detection_engine.time.sleep", lambda _seconds: None)
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    engine = _engine(FakeCamera([(False, None), (True, frame)]))

    success, captured_frame = engine.read()

    assert success is True
    assert captured_frame is frame


def test_read_reopens_camera_with_another_backend(monkeypatch):
    monkeypatch.setattr("detection_engine.time.sleep", lambda _seconds: None)
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    disconnected_camera = FakeCamera([(False, None)] * 3)
    replacement_camera = FakeCamera([(True, frame)])
    engine = _engine(disconnected_camera)
    opened_backends = []

    def open_camera(index, backend):
        opened_backends.append((index, backend))
        return replacement_camera

    monkeypatch.setattr(cv2, "VideoCapture", open_camera)

    success, captured_frame = engine.read()

    assert success is True
    assert captured_frame is frame
    assert disconnected_camera.released is True
    assert opened_backends == [(0, cv2.CAP_MSMF)]


def test_mar_uses_upper_and_lower_lip_landmarks():
    landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
    coordinates = {
        1: (0.50, 0.50),
        152: (0.50, 0.80),
        33: (0.38, 0.42),
        263: (0.62, 0.42),
        61: (0.30, 0.60),
        291: (0.70, 0.60),
        0: (0.50, 0.38),
        13: (0.50, 0.43),
        14: (0.50, 0.57),
        17: (0.50, 0.62),
        160: (0.40, 0.40),
        158: (0.42, 0.40),
        133: (0.44, 0.42),
        153: (0.42, 0.44),
        144: (0.40, 0.44),
        362: (0.56, 0.42),
        385: (0.58, 0.40),
        387: (0.60, 0.40),
        373: (0.58, 0.44),
        380: (0.56, 0.44),
    }
    for index, (x, y) in coordinates.items():
        landmarks[index] = SimpleNamespace(x=x, y=y)
    engine = object.__new__(DetectionEngine)
    engine.face_mesh = SimpleNamespace(
        process=lambda _image: SimpleNamespace(
            multi_face_landmarks=[SimpleNamespace(landmark=landmarks)]
        )
    )

    measurements = engine.analyze_frame(np.zeros((100, 100, 3), dtype=np.uint8))

    assert measurements["face_detected"] is True
    assert measurements["mar"] == pytest.approx(0.475)
