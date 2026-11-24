import arduino_controller


class FakeSerial:
    def __init__(self, port=None, baudrate=None, timeout=None, write_timeout=None):
        self.port = port
        self.baudrate = baudrate
        self.is_open = True
        self.commands = []

    def write(self, command):
        self.commands.append(command)
        return len(command)

    def close(self):
        self.is_open = False


def test_simulation_never_opens_serial():
    controller = arduino_controller.ArduinoController(simulation=True)
    assert controller.status_name() == "SIMULATION"
    assert controller.send_status("NORMAL") is True
    assert controller.connection is None


def test_status_changes_and_heartbeat(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(arduino_controller.time, "monotonic", lambda: now[0])
    controller = arduino_controller.ArduinoController(simulation=False)
    controller.connection = FakeSerial()
    controller.connected = True

    assert controller.send_status("NORMAL") is True
    assert controller.connection.commands == [b"N\n"]
    now[0] = 0.5
    controller.send_status("NORMAL")
    assert controller.connection.commands == [b"N\n"]
    now[0] = 1.1
    controller.send_status("NORMAL")
    controller.send_status("CRITICAL")
    assert controller.connection.commands == [b"N\n", b"N\n", b"X\n"]


def test_each_detection_status_maps_to_firmware_protocol():
    controller = arduino_controller.ArduinoController(simulation=False)
    controller.connection = FakeSerial()
    controller.connected = True

    for status in ("NORMAL", "CAUTION", "HIGH RISK", "CRITICAL", "NOT DETECTED"):
        assert controller.send_status(status) is True

    assert controller.connection.commands == [
        b"N\n", b"C\n", b"H\n", b"X\n", b"F\n"
    ]


def test_connect_reuses_open_port_and_reconnects(monkeypatch):
    now = [0.0]
    connections = []

    def open_serial(*args, **kwargs):
        connection = FakeSerial(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(arduino_controller.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(arduino_controller.serial, "Serial", open_serial)
    controller = arduino_controller.ArduinoController(
        port="COM5", simulation=False
    )

    assert controller.connect() is True
    assert controller.connect() is True
    assert len(connections) == 1
    controller._close_connection()
    now[0] = 3.0
    assert controller.connect() is True
    assert [connection.port for connection in connections] == ["COM5", "COM5"]
