const byte GREEN_LED = 2;
const byte RED_LED = 3;
const byte BUZZER = 4;
const byte MOTOR_IN1 = 5;
const byte MOTOR_IN2 = 6;
const byte MOTOR_ENA = 9;

const unsigned long WATCHDOG_MS = 3000;
const unsigned long CAUTION_PERIOD_MS = 1800;
const unsigned long CAUTION_ON_MS = 100;
const unsigned long HIGH_PERIOD_MS = 500;
const unsigned long HIGH_ON_MS = 200;

unsigned long lastCommandAt = 0;
char activeMode = 'F';
bool watchdogFailure = true;
bool buzzerActive = false;
unsigned int activeTone = 0;

void stopMotor() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, LOW);
  analogWrite(MOTOR_ENA, 0);
}

void runMotor() {
  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, LOW);
  analogWrite(MOTOR_ENA, 180);
}

void setBuzzer(bool enabled, unsigned int frequency = 0) {
  if (!enabled) {
    if (buzzerActive) {
      noTone(BUZZER);
      buzzerActive = false;
      activeTone = 0;
    }
    return;
  }

  if (!buzzerActive || activeTone != frequency) {
    tone(BUZZER, frequency);
    buzzerActive = true;
    activeTone = frequency;
  }
}

void failureMode() {
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, HIGH);
  setBuzzer(false);
  stopMotor();
}

void applyMode(unsigned long now) {
  if (activeMode == 'N') {
    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(RED_LED, LOW);
    setBuzzer(false);
    runMotor();
  } else if (activeMode == 'C') {
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED, HIGH);
    runMotor();
    setBuzzer(now % CAUTION_PERIOD_MS < CAUTION_ON_MS, 1500);
  } else if (activeMode == 'H') {
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED, HIGH);
    stopMotor();
    setBuzzer(now % HIGH_PERIOD_MS < HIGH_ON_MS, 1900);
  } else if (activeMode == 'X') {
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(RED_LED, HIGH);
    stopMotor();
    setBuzzer(true, 2200);
  } else {
    failureMode();
  }
}

void setup() {
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(MOTOR_IN1, OUTPUT);
  pinMode(MOTOR_IN2, OUTPUT);
  pinMode(MOTOR_ENA, OUTPUT);
  Serial.begin(9600);
  lastCommandAt = millis();
  failureMode();
}

void loop() {
  while (Serial.available() > 0) {
    const char command = Serial.read();
    if (command == 'N' || command == 'C' || command == 'H' ||
        command == 'X' || command == 'F') {
      activeMode = command;
      watchdogFailure = false;
      lastCommandAt = millis();
    }
  }

  const unsigned long now = millis();
  if (now - lastCommandAt >= WATCHDOG_MS) {
    watchdogFailure = true;
  }

  if (watchdogFailure || activeMode == 'F') {
    failureMode();
    return;
  }
  applyMode(now);
}
