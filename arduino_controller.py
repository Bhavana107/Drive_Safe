import logging
import time

import serial

import config


logger = logging.getLogger(__name__)
STATUS_COMMANDS = {
    "NORMAL": "N",
    "CAUTION": "C",
    "HIGH RISK": "H",
    "CRITICAL": "X",
    "NOT DETECTED": "F",
}


class ArduinoController:
    HEARTBEAT_SECONDS = 1.0
    RECONNECT_SECONDS = 2.0

    def __init__(self, port=None, baud_rate=None, simulation=None):
        self.port = config.SERIAL_PORT if port is None else port
        self.baud_rate = config.BAUD_RATE if baud_rate is None else baud_rate
        self.simulation = (
            config.ARDUINO_SIMULATION if simulation is None else simulation
        )
        self.connection = None
        self.connected = False
        self.current_status = None
        self.last_sent_at = None
        self.last_connect_attempt = None

    def connect(self):
        if self.simulation:
            logger.info("Arduino simulation enabled; no serial connection opened")
            return False
        if not self.port:
            logger.warning("Arduino serial port is not configured")
            return False
        if (
            self.connected
            and self.connection is not None
            and getattr(self.connection, "is_open", True)
        ):
            return True

        now = time.monotonic()
        if (
            self.last_connect_attempt is not None
            and now - self.last_connect_attempt < self.RECONNECT_SECONDS
        ):
            return False
        self.last_connect_attempt = now

        try:
            self.connection = serial.Serial(
                self.port, self.baud_rate, timeout=1, write_timeout=1
            )
        except (serial.SerialException, OSError):
            self.connection = None
            self.connected = False
            logger.exception("Could not connect to Arduino on %s", self.port)
            return False

        self.connected = True
        self.current_status = None
        self.last_sent_at = None
        logger.info("Connected to Arduino on %s at %s baud", self.port, self.baud_rate)
        return True

    def send_status(self, status):
        command = STATUS_COMMANDS.get(status)
        if command is None:
            logger.error("Unknown detection status %r; sending failsafe F", status)
            status = "NOT DETECTED"
            command = STATUS_COMMANDS[status]

        now = time.monotonic()
        changed = status != self.current_status
        heartbeat_due = (
            self.last_sent_at is None
            or now - self.last_sent_at >= self.HEARTBEAT_SECONDS
        )
        if not changed and not heartbeat_due:
            return True

        if self.simulation:
            self.current_status = status
            self.last_sent_at = now
            return True

        if not self.connected and not self.connect():
            return False
        if self.connection is None:
            return False

        payload = (command + "\n").encode("ascii")
        try:
            written = self.connection.write(payload)
            if written != len(payload):
                raise serial.SerialException("Serial write was incomplete")
        except (serial.SerialException, OSError):
            logger.exception("Lost Arduino serial connection on %s", self.port)
            self._close_connection()
            return False

        self.current_status = status
        self.last_sent_at = now
        return True

    def stop_motor(self):
        return self.send_status("NOT DETECTED")

    def disconnect(self, send_safe=True):
        if send_safe and self.connected:
            self.send_status("NOT DETECTED")
        self._close_connection()

    def status_name(self):
        if self.simulation:
            return "SIMULATION"
        return "CONNECTED" if self.connected else "DISCONNECTED"

    def _close_connection(self):
        connection = self.connection
        self.connection = None
        self.connected = False
        self.current_status = None
        self.last_sent_at = None
        if connection is not None and getattr(connection, "is_open", False):
            try:
                connection.close()
            except (serial.SerialException, OSError):
                logger.exception("Error closing Arduino serial connection")
