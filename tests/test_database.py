import os
import sqlite3
import tempfile

import config
import database


def _result(status="HIGH RISK", score=60):
    return {
        "face_detected": True,
        "ear": 0.18,
        "mar": 0.4,
        "perclos": 25.0,
        "eye_closed": True,
        "eye_closure_event": False,
        "eye_closures": 1,
        "yawning": False,
        "yawning_event": False,
        "yawning_count": 0,
        "head_nodding": False,
        "head_nodding_event": False,
        "head_nodding_count": 0,
        "risk_score": score,
        "status": status,
        "reasons": ["prolonged eye closure"],
        "message": "",
    }


def test_database_round_trip_and_transition_counts(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setattr(config, "DATABASE_PATH", os.path.join(directory, "test.db"))
        database.initialize_database()
        session_id = database.start_session("2026-01-01T10:00:00")
        database.insert_fatigue_event(
            session_id, "2026-01-01T10:00:05", _result(), "status"
        )
        database.insert_fatigue_event(
            session_id, "2026-01-01T10:00:06", _result(score=61), "behavior"
        )
        database.insert_detection_sample(
            session_id, "2026-01-01T10:00:07", _result()
        )

        history = database.get_history()
        assert len(history) == 2
        assert history[-1]["risk_score"] == 60
        assert database.get_session_stats()["total_events"] == 1
        assert database.get_analytics()["samples"][0]["risk_score"] == 60


def test_state_publication_and_read_only_access(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "test.db")
        monkeypatch.setattr(config, "DATABASE_PATH", database_path)
        database.initialize_database()
        database.publish_state(
            _result(), True, "CONNECTED", "2026-01-01T10:00:00+00:00"
        )

        state = database.get_latest_state(read_only=True)
        assert state["engine_running"] is True
        assert state["status"] == "HIGH RISK"
        assert state["arduino_status"] == "CONNECTED"


def test_read_only_queries_do_not_create_database(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "not-created.db")
        monkeypatch.setattr(config, "DATABASE_PATH", database_path)

        assert database.get_latest_state(read_only=True)["status"] == "NOT DETECTED"
        assert database.get_history(read_only=True) == []
        assert database.get_analytics(read_only=True) == {
            "samples": [],
            "behavior_frequency": [],
        }
        assert not os.path.exists(database_path)


def test_legacy_database_remains_read_only_until_engine_migrates(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        database_path = os.path.join(directory, "legacy.db")
        connection = sqlite3.connect(database_path)
        connection.executescript(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER DEFAULT 0,
                total_alerts INTEGER DEFAULT 0,
                maximum_risk_score INTEGER DEFAULT 0
            );
            CREATE TABLE fatigue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                fatigue_level TEXT NOT NULL,
                ear REAL,
                mar REAL,
                perclos REAL,
                yawning INTEGER DEFAULT 0,
                head_nodding INTEGER DEFAULT 0
            );
            INSERT INTO sessions (start_time) VALUES ('2026-01-01T10:00:00');
            INSERT INTO fatigue_events
                (session_id, timestamp, risk_score, fatigue_level, ear, mar, perclos)
            VALUES (1, '2026-01-01T10:00:01', 60, 'HIGH RISK', 0.18, 0.4, 25.0);
            """
        )
        connection.close()
        monkeypatch.setattr(config, "DATABASE_PATH", database_path)

        assert database.get_latest_state(read_only=True)["status"] == "NOT DETECTED"
        assert database.get_analytics(read_only=True)["samples"] == []
        assert database.get_history(read_only=True)[0]["risk_score"] == 60
        connection = sqlite3.connect(database_path)
        legacy_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(fatigue_events)")
        }
        connection.close()
        assert "event_type" not in legacy_columns

        database.initialize_database()
        history = database.get_history()
        assert len(history) == 1
        assert history[0]["event_type"] == "legacy"
        assert database.get_latest_state()["status"] == "NOT DETECTED"
