import os
from dotenv import load_dotenv

load_dotenv()

WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CALIBRATION_SECONDS = float(os.getenv("CALIBRATION_SECONDS", "8"))
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
SERIAL_PORT = os.getenv("SERIAL_PORT", "COM10")
BAUD_RATE = int(os.getenv("BAUD_RATE", "9600"))
ARDUINO_SIMULATION = os.getenv("ARDUINO_SIMULATION", "true").lower() == "true"

EYE_CLOSURE_THRESHOLD = float(os.getenv("EYE_CLOSURE_THRESHOLD", "0.21"))
EYE_CLOSURE_DURATION = float(os.getenv("EYE_CLOSURE_DURATION", "1.5"))
SUSTAINED_SLEEPING_SECONDS = float(os.getenv("SUSTAINED_SLEEPING_SECONDS", "3.0"))
YAWNING_DURATION = float(os.getenv("YAWNING_DURATION", "2.0"))
YAWN_MAR_THRESHOLD = float(os.getenv("YAWN_MAR_THRESHOLD", "0.50"))
HEAD_NOD_DURATION = float(os.getenv("HEAD_NOD_DURATION", "1.2"))
HEAD_NOD_PITCH_THRESHOLD = float(os.getenv("HEAD_NOD_PITCH_THRESHOLD", "12"))
PERCLOS_WINDOW = float(os.getenv("PERCLOS_WINDOW", "60"))
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "1"))
CRITICAL_ALERT_DELAY_SECONDS = float(
    os.getenv("CRITICAL_ALERT_DELAY_SECONDS", "10")
)
YAWN_ALERT_COUNT_THRESHOLD = int(os.getenv("YAWN_ALERT_COUNT_THRESHOLD", "4"))
YAWN_ALERT_WINDOW_SECONDS = float(os.getenv("YAWN_ALERT_WINDOW_SECONDS", "60"))

RISK_CAUTION_THRESHOLD = int(os.getenv("RISK_CAUTION_THRESHOLD", "30"))
RISK_HIGH_THRESHOLD = int(os.getenv("RISK_HIGH_THRESHOLD", "50"))
RISK_CRITICAL_THRESHOLD = int(os.getenv("RISK_CRITICAL_THRESHOLD", "80"))

NOTIFICATION_ENABLED = os.getenv("NOTIFICATION_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/drive_safe.db")
LOG_PATH = os.getenv("LOG_PATH", "logs/drive_safe.log")
