import os
import tempfile

import config
from dashboard import app as dashboard_module


def test_dashboard_reads_status_without_creating_database(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "missing.db")
        monkeypatch.setattr(config, "DATABASE_PATH", database_path)
        client = dashboard_module.app.test_client()

        response = client.get("/api/status")
        assert response.status_code == 200
        assert response.get_json()["status"] == "NOT DETECTED"
        assert not os.path.exists(database_path)
        assert client.get("/").status_code == 200


def test_dashboard_history_and_read_only_methods(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setattr(
            config, "DATABASE_PATH", os.path.join(directory, "missing.db")
        )
        client = dashboard_module.app.test_client()

        assert client.get("/api/history").get_json() == []
        assert client.get("/api/history?limit=invalid").status_code == 400
        assert client.get("/api/sessions").get_json()["severity_counts"] == {}
        assert client.post("/api/status").status_code == 405


def test_dashboard_module_does_not_import_camera_or_hardware_control():
    assert "cv2" not in dashboard_module.__dict__
    assert "DetectionEngine" not in dashboard_module.__dict__
    assert "ArduinoController" not in dashboard_module.__dict__
