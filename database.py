from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path

import config


@contextmanager
def get_connection(read_only=False):
    database_path = Path(config.DATABASE_PATH)
    if read_only:
        if not database_path.is_file():
            yield None
            return
        connection = sqlite3.connect(
            database_path.resolve().as_uri() + "?mode=ro",
            timeout=5,
            uri=True,
        )
    else:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(database_path), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        if not read_only:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        else:
            yield connection
    finally:
        connection.close()


def _ensure_event_columns(connection):
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(fatigue_events)")
    }
    additions = {
        "eye_closed": "INTEGER NOT NULL DEFAULT 0",
        "eye_closures": "INTEGER NOT NULL DEFAULT 0",
        "yawning_count": "INTEGER NOT NULL DEFAULT 0",
        "head_nodding_count": "INTEGER NOT NULL DEFAULT 0",
        "reason": "TEXT NOT NULL DEFAULT ''",
        "event_type": "TEXT NOT NULL DEFAULT 'legacy'",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE fatigue_events ADD COLUMN {column} {definition}"
            )


def _ensure_state_columns(connection):
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(detection_state)")
    }
    if "calibrating" not in columns:
        connection.execute(
            "ALTER TABLE detection_state ADD COLUMN calibrating "
            "INTEGER NOT NULL DEFAULT 0"
        )


def _table_exists(connection, table_name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _table_columns(connection, table_name):
    if not _table_exists(connection, table_name):
        return set()
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def initialize_database():
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER DEFAULT 0,
                total_alerts INTEGER DEFAULT 0,
                maximum_risk_score INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS fatigue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                fatigue_level TEXT NOT NULL,
                ear REAL,
                mar REAL,
                perclos REAL,
                yawning INTEGER NOT NULL DEFAULT 0,
                head_nodding INTEGER NOT NULL DEFAULT 0,
                eye_closed INTEGER NOT NULL DEFAULT 0,
                eye_closures INTEGER NOT NULL DEFAULT 0,
                yawning_count INTEGER NOT NULL DEFAULT 0,
                head_nodding_count INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT 'legacy',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE TABLE IF NOT EXISTS detection_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                fatigue_level TEXT NOT NULL,
                ear REAL NOT NULL,
                mar REAL NOT NULL,
                perclos REAL NOT NULL,
                eye_closed INTEGER NOT NULL,
                eye_closures INTEGER NOT NULL,
                yawning_count INTEGER NOT NULL,
                head_nodding_count INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE TABLE IF NOT EXISTS detection_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                updated_at TEXT,
                engine_running INTEGER NOT NULL DEFAULT 0,
                calibrating INTEGER NOT NULL DEFAULT 0,
                face_detected INTEGER NOT NULL DEFAULT 0,
                ear REAL NOT NULL DEFAULT 0,
                mar REAL NOT NULL DEFAULT 0,
                perclos REAL NOT NULL DEFAULT 0,
                eye_closed INTEGER NOT NULL DEFAULT 0,
                eye_closures INTEGER NOT NULL DEFAULT 0,
                yawning_count INTEGER NOT NULL DEFAULT 0,
                head_nodding_count INTEGER NOT NULL DEFAULT 0,
                risk_score INTEGER NOT NULL DEFAULT 100,
                fatigue_level TEXT NOT NULL DEFAULT 'NOT DETECTED',
                arduino_status TEXT NOT NULL DEFAULT 'DISCONNECTED',
                reasons TEXT NOT NULL DEFAULT '[]',
                message TEXT NOT NULL DEFAULT 'AI engine is not running'
            );
            CREATE TABLE IF NOT EXISTS calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                baseline_ear REAL NOT NULL,
                eye_threshold REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                serial_port TEXT DEFAULT '',
                notification_enabled INTEGER DEFAULT 0,
                telegram_chat_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_fatigue_events_session_id
                ON fatigue_events(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_detection_samples_timestamp
                ON detection_samples(timestamp);
            """
        )
        _ensure_event_columns(connection)
        _ensure_state_columns(connection)
        default_arduino_status = (
            "SIMULATION" if config.ARDUINO_SIMULATION else "DISCONNECTED"
        )
        connection.execute(
            "INSERT OR IGNORE INTO detection_state (id, arduino_status) VALUES (1, ?)",
            (default_arduino_status,),
        )
        connection.execute(
            "INSERT OR IGNORE INTO settings (id, serial_port, notification_enabled, telegram_chat_id) "
            "VALUES (1, ?, ?, ?)",
            (
                config.SERIAL_PORT,
                int(config.NOTIFICATION_ENABLED),
                config.TELEGRAM_CHAT_ID,
            ),
        )


def start_session(start_time):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO sessions (start_time) VALUES (?)", (start_time,)
        )
        return cursor.lastrowid


def end_session(session_id, end_time, duration_seconds, total_alerts,
                maximum_risk_score):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE sessions
            SET end_time = ?, duration_seconds = ?, total_alerts = ?,
                maximum_risk_score = ?
            WHERE id = ?
            """,
            (
                end_time,
                duration_seconds,
                total_alerts,
                maximum_risk_score,
                session_id,
            ),
        )


def publish_state(result, engine_running, arduino_status, updated_at):
    reasons = json.dumps(result.get("reasons", []))
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO detection_state (
                id, updated_at, engine_running, calibrating, face_detected, ear, mar,
                perclos, eye_closed, eye_closures, yawning_count,
                head_nodding_count, risk_score, fatigue_level,
                arduino_status, reasons, message
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                engine_running = excluded.engine_running,
                calibrating = excluded.calibrating,
                face_detected = excluded.face_detected,
                ear = excluded.ear,
                mar = excluded.mar,
                perclos = excluded.perclos,
                eye_closed = excluded.eye_closed,
                eye_closures = excluded.eye_closures,
                yawning_count = excluded.yawning_count,
                head_nodding_count = excluded.head_nodding_count,
                risk_score = excluded.risk_score,
                fatigue_level = excluded.fatigue_level,
                arduino_status = excluded.arduino_status,
                reasons = excluded.reasons,
                message = excluded.message
            """,
            (
                updated_at,
                int(engine_running),
                int(result.get("calibrating", False)),
                int(result.get("face_detected", False)),
                float(result.get("ear", 0.0)),
                float(result.get("mar", 0.0)),
                float(result.get("perclos", 0.0)),
                int(result.get("eye_closed", False)),
                int(result.get("eye_closures", 0)),
                int(result.get("yawning_count", 0)),
                int(result.get("head_nodding_count", 0)),
                int(result.get("risk_score", 100)),
                result.get("status", "NOT DETECTED"),
                arduino_status,
                reasons,
                result.get("message", ""),
            ),
        )


def get_latest_state(read_only=False):
    with get_connection(read_only=read_only) as connection:
        if connection is None:
            return _default_state()
        if not _table_exists(connection, "detection_state"):
            return _default_state()
        row = connection.execute(
            "SELECT * FROM detection_state WHERE id = 1"
        ).fetchone()
    if row is None:
        return _default_state()
    state = dict(row)
    state["engine_running"] = bool(state["engine_running"])
    state["calibrating"] = bool(state.get("calibrating", False))
    state["face_detected"] = bool(state["face_detected"])
    state["eye_closed"] = bool(state["eye_closed"])
    state["status"] = state.pop("fatigue_level")
    try:
        state["reasons"] = json.loads(state["reasons"])
    except (TypeError, json.JSONDecodeError):
        state["reasons"] = []
    return state


def _default_state():
    return {
        "updated_at": None,
        "engine_running": False,
        "calibrating": False,
        "face_detected": False,
        "ear": 0.0,
        "mar": 0.0,
        "perclos": 0.0,
        "eye_closed": False,
        "eye_closures": 0,
        "yawning_count": 0,
        "head_nodding_count": 0,
        "risk_score": 100,
        "status": "NOT DETECTED",
        "arduino_status": (
            "SIMULATION" if config.ARDUINO_SIMULATION else "DISCONNECTED"
        ),
        "reasons": [],
        "message": "AI engine is not running",
    }


def insert_detection_sample(session_id, timestamp, result):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO detection_samples (
                session_id, timestamp, risk_score, fatigue_level, ear, mar,
                perclos, eye_closed, eye_closures, yawning_count,
                head_nodding_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                int(result["risk_score"]),
                result["status"],
                float(result["ear"]),
                float(result["mar"]),
                float(result["perclos"]),
                int(result["eye_closed"]),
                int(result["eye_closures"]),
                int(result["yawning_count"]),
                int(result["head_nodding_count"]),
            ),
        )


def insert_fatigue_event(session_id, timestamp, result, event_type):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO fatigue_events (
                session_id, timestamp, risk_score, fatigue_level, ear, mar,
                perclos, yawning, head_nodding, eye_closed, eye_closures,
                yawning_count, head_nodding_count, reason, event_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                timestamp,
                int(result["risk_score"]),
                result["status"],
                float(result["ear"]),
                float(result["mar"]),
                float(result["perclos"]),
                int(result.get("yawning_event", False)),
                int(result.get("head_nodding_event", False)),
                int(result.get("eye_closure_event", False)),
                int(result["eye_closures"]),
                int(result["yawning_count"]),
                int(result["head_nodding_count"]),
                "; ".join(result.get("reasons", [])),
                event_type,
            ),
        )
        return cursor.lastrowid


def get_history(limit=100, level=None, read_only=False):
    limit = max(1, min(int(limit), 500))
    sql = "SELECT * FROM fatigue_events"
    parameters = []
    if level:
        sql += " WHERE fatigue_level = ?"
        parameters.append(level)
    sql += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)
    with get_connection(read_only=read_only) as connection:
        if connection is None:
            return []
        if not _table_exists(connection, "fatigue_events"):
            return []
        return [
            dict(row)
            for row in connection.execute(sql, parameters).fetchall()
        ]


def get_analytics(sample_limit=300, read_only=False):
    sample_limit = max(1, min(int(sample_limit), 1000))
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    with get_connection(read_only=read_only) as connection:
        if connection is None:
            return {"samples": [], "behavior_frequency": []}
        sample_columns = _table_columns(connection, "detection_samples")
        samples = []
        if {
            "timestamp", "risk_score", "fatigue_level", "eye_closed", "perclos"
        } <= sample_columns:
            samples = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT timestamp, risk_score, fatigue_level, eye_closed, perclos
                    FROM detection_samples
                    WHERE fatigue_level != 'NOT DETECTED'
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (sample_limit,),
                ).fetchall()
            ]
        event_columns = _table_columns(connection, "fatigue_events")
        frequencies = []
        if {
            "timestamp", "eye_closed", "yawning", "head_nodding", "event_type"
        } <= event_columns:
            frequencies = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT substr(timestamp, 1, 13) AS hour,
                           SUM(eye_closed) AS eye_closures,
                           SUM(yawning) AS yawns,
                           SUM(head_nodding) AS head_nods
                    FROM fatigue_events
                    WHERE timestamp >= ? AND event_type IN ('behavior', 'mixed')
                    GROUP BY substr(timestamp, 1, 13)
                    ORDER BY hour
                    """,
                    (cutoff,),
                ).fetchall()
            ]
    samples.reverse()
    return {"samples": samples, "behavior_frequency": frequencies}


def get_session_stats(read_only=False):
    with get_connection(read_only=read_only) as connection:
        if connection is None:
            return {
                "latest_session": None,
                "total_events": 0,
                "severity_counts": {},
            }
        session = (
            connection.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if _table_exists(connection, "sessions")
            else None
        )
        event_columns = _table_columns(connection, "fatigue_events")
        transition_rows = []
        if {"id", "session_id", "fatigue_level"} <= event_columns:
            transition_rows = connection.execute(
                """
                WITH ordered_events AS (
                    SELECT session_id, fatigue_level,
                           LAG(fatigue_level) OVER (
                               PARTITION BY session_id ORDER BY id
                           ) AS previous_level
                    FROM fatigue_events
                )
                SELECT fatigue_level, COUNT(*) AS count
                FROM ordered_events
                WHERE previous_level IS NULL OR fatigue_level != previous_level
                GROUP BY fatigue_level
                """
            ).fetchall()
        severity_counts = {
            row["fatigue_level"]: row["count"]
            for row in transition_rows
        }
    return {
        "latest_session": dict(session) if session else None,
        "total_events": sum(severity_counts.values()),
        "severity_counts": severity_counts,
    }


def save_calibration(baseline_ear, eye_threshold, created_at):
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO calibration (baseline_ear, eye_threshold, created_at) "
            "VALUES (?, ?, ?)",
            (baseline_ear, eye_threshold, created_at),
        )


def get_latest_calibration():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM calibration ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
