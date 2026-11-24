# DRIVE SAFE 2.0

DRIVE SAFE is an academic driver-fatigue monitoring prototype. A local Python
engine reads a webcam, estimates facial measurements, records results in
SQLite, and sends status letters to an Arduino. A separate Flask dashboard
reads the SQLite database and displays current status, trends, and event
history. The dashboard cannot start the camera, change the detection status,
or control the Arduino.

> **Safety:** This is not a medical device or an automotive-certified safety
> system. Do not connect its motor output to a vehicle. Use the motor only as a
> tabletop demonstration, and keep it disconnected while testing software.

## Architecture

```text
Webcam -> main.py -> MediaPipe / fatigue_calculator.py
                  -> SQLite (state, samples, events)
                  -> Arduino serial (N/C/H/X/F)
                  -> optional Telegram alert

SQLite <- dashboard/app.py -> read-only HTTP dashboard
```

- `main.py` is the only process that opens the webcam or serial port. It also
  displays the OpenCV live window; press **q** or **Esc** there to stop it.
- `detection_engine.py` owns camera and facial-landmark processing.
- `fatigue_calculator.py` calculates EAR, MAR, PERCLOS, behavior events, a
  weighted risk score, and a smoothed status.
- `arduino_controller.py` sends the current status and a one-second heartbeat.
- `dashboard/app.py` exposes GET-only views of the SQLite data; it does not
  import or control the camera, AI engine, or Arduino.
- SQLite is the shared boundary between the two independent processes.

## Requirements and installation

Use Python 3.11 on Windows for the pinned MediaPipe version. In PowerShell,
from the project directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` to select the webcam index and, when ready, the Arduino COM port.
The default `ARDUINO_SIMULATION=true` deliberately prevents serial output. To
use a connected controller, set `ARDUINO_SIMULATION=false` and verify
`SERIAL_PORT` (for example `COM10`). Close Arduino IDE's Serial Monitor before
starting the engine.

## Run the application

Use **two PowerShell terminals** in the project directory.

**Terminal 1 — live AI engine (opens the webcam):**

```powershell
.\.venv\Scripts\python.exe main.py
```

The engine calibrates for the configured number of seconds, then displays live
measurements in its OpenCV window. Face the camera normally during calibration.
Press **q** or **Esc** in that window, or press Ctrl+C in the terminal, to stop.

**Terminal 2 — read-only dashboard:**

```powershell
.\.venv\Scripts\python.exe -m dashboard.app
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The dashboard polls the
database for updates; it does not show a camera stream. If the engine is not
running, the dashboard reports **ENGINE OFFLINE** and **NOT DETECTED**.
If an older dashboard is still open on port 5000, stop that old server with
Ctrl+C first. Alternatively, start the new dashboard on another port:

```powershell
$env:FLASK_PORT = "5001"
.\.venv\Scripts\python.exe -m dashboard.app
```

Then open [http://127.0.0.1:5001](http://127.0.0.1:5001).

## Detection and status protocol

The score combines prolonged eye closure (40%), PERCLOS (25%), recent yawns
(20%), and head nods (15%), then smooths the result over time. Normal blinks do
not count as prolonged closures. A continuous closure or other behavioral
event must meet its configured duration before it is counted. PERCLOS uses a
rolling window; losing the face reports **NOT DETECTED**, not **NORMAL**.

Default score bands are `NORMAL` below 30, `CAUTION` from 30, `HIGH RISK` from
50, and `CRITICAL` from 75. Values can be adjusted in `.env`.

| Python status | Serial letter | Firmware behavior |
|---|---:|---|
| NORMAL | `N` | Green LED; motor runs; buzzer off |
| CAUTION | `C` | Red LED; brief intermittent buzzer; motor continues |
| HIGH RISK | `H` | Red LED; faster intermittent buzzer; motor stops |
| CRITICAL | `X` | Red LED; steady buzzer; motor stops |
| NOT DETECTED / startup / failure | `F` | Red LED; buzzer off; motor stopped |

The Arduino watchdog enters the safe `F` outputs after three seconds without a
valid command. Firmware buzzer patterns use `millis()` and do not block
watchdog processing. Test only with an unloaded tabletop motor.

## Arduino setup

1. Open `arduino/drive_safe.ino` in Arduino IDE.
2. Select **Arduino Uno** and the correct COM port; upload the sketch.
3. Close Arduino IDE's Serial Monitor.
4. Wire indicators and motor driver as shown below. Keep the motor supply
   disconnected until the signal-only test has passed.
5. Set `SERIAL_PORT` to the same COM port and `ARDUINO_SIMULATION=false` in
   `.env`, then start `main.py`.

| Uno pin | Connection |
|---|---|
| D2 | Green LED anode through a 220-ohm resistor |
| D3 | Red LED anode through a 220-ohm resistor |
| D4 | 5V-compatible buzzer positive |
| D5 / D6 | L298N IN1 / IN2 |
| D9 | L298N ENA (remove the ENA jumper for PWM control) |
| GND | LED cathodes, buzzer negative, Arduino GND, and L298N GND |
| L298N OUT1 / OUT2 | Tabletop DC motor terminals |

Use a motor supply that matches the motor and driver rating. Never connect the
motor battery to the Arduino 5V pin. Share ground between Arduino and L298N.
Follow the exact L298N module's regulator/jumper documentation.

## Optional Telegram guardian notifications

Create a Telegram bot and obtain the guardian chat ID. Set these values in
`.env`:

```text
NOTIFICATION_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Credentials are read only by the AI process and are never exposed by the
dashboard API. The engine requests an alert on entry to `CRITICAL`; it will not
send another until the status recovers to `CAUTION` or `NORMAL` and later
re-enters `CRITICAL`. Verify delivery using a non-driving demonstration.

## Viva concepts and evaluation

- **Feature extraction:** EAR measures the vertical-to-horizontal eye opening;
  MAR measures mouth opening; head pose estimates pitch from facial landmarks.
- **Personalisation:** a short baseline estimates an eye-closure threshold for
  the current camera and driver instead of assuming every face is identical.
- **Temporal reasoning:** blink-resistant durations, a rolling PERCLOS window,
  recent behavior counts, and score smoothing reduce one-frame false alarms.
- **State machine:** fatigue levels map to fixed serial letters; `NOT DETECTED`
  and startup/failure use the safe `F` output.
- **Process boundary:** SQLite shares results between the camera/hardware
  process and a Flask process that only reads data.
- **Reliability:** serial heartbeats and the Arduino watchdog fail toward a
  stopped tabletop motor; Telegram is an optional transition notification.
- **Limitations:** camera angle, lighting, occlusion, facial differences, and
  uncalibrated hardware affect results. Thresholds and scores are experimental,
  not clinically validated.

For an evaluation, label normal and drowsy intervals from a recorded,
consented demonstration, then calculate precision, recall, F1, false alarms,
and detection latency. Report measured results; do not infer accuracy from
these rules or treat this prototype as evidence of road safety.

## Data and logs

- `data/drive_safe.db` stores current engine state, timestamped samples,
  behavior/status events, calibration values, and session summaries.
- Database initialization applies additive schema migrations and preserves
  existing records.
- `logs/drive_safe.log` records engine, serial, database, and notification
  errors.
- Do not commit `.env`, database files, or logs.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover fatigue scoring and behavioral events, safe serial mappings,
database persistence, and the dashboard's read-only API. Physical Arduino,
webcam, and Telegram delivery require local hardware and credentials and are
not simulated by the automated tests.

## Troubleshooting

- **Camera opens then stops:** close other camera apps, try `WEBCAM_INDEX=1`
  (or another available index), and restart the AI engine. The engine tries
  Windows camera backends and retries/reopens a camera that briefly stops
  delivering frames.
- **Yawns are missed:** keep the mouth open for about two seconds and watch
  `MAR` in the OpenCV window. Set `YAWN_MAR_THRESHOLD=0.50` in `.env`; an older
  `.env` may still contain the previous higher value.
- **Arduino connects but indicators don't match:** upload the current
  `arduino/drive_safe.ino` again, close Serial Monitor, verify the COM port and
  9600 baud, and check LED polarity, common ground, and the L298N wiring.
- **Old dashboard appears or the port is occupied:** stop the old Flask process
  with Ctrl+C, or set `FLASK_PORT=5001` in `.env` and browse to port 5001.
