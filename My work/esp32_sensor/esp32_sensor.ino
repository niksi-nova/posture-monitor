/*
  Posture Monitor - ESP32 Firmware
  ---------------------------------
  - Reads 4 flex sensor voltage dividers (GPIO 32, 33, 34, 35)
  - 8x oversampled averaging per channel per sample
  - Outputs JSON over Serial at fixed 50Hz (20ms interval)
  - Listens for 'V' byte over Serial -> fires vibration motor (GPIO27) for a short pulse

  JSON format per packet:
  {"t":1234567890123,"c":2048,"th":2010,"tlj":1990,"l":2050}
*/

// ---------- Pin definitions ----------
const int PIN_C = 32;   // Cervical (C5-C7)
const int PIN_TH = 33;  // Mid-upper thoracic (T1-T8)
const int PIN_TLJ = 34; // Thoracolumbar junction (T12-L1)
const int PIN_L = 35;   // Lumbar (L1-L4)
const int PIN_MOTOR = 27;

// ---------- Timing ----------
const unsigned long SAMPLE_INTERVAL_MS = 67;   // 15Hz
unsigned long lastSampleTime = 0;

// ---------- Motor pulse handling ----------
const unsigned long MOTOR_PULSE_MS = 300;      // how long the motor buzzes per trigger
bool motorActive = false;
unsigned long motorStartTime = 0;

// ---------- Oversampling ----------
const int OVERSAMPLE_COUNT = 8;

// Reads a pin OVERSAMPLE_COUNT times and returns the integer average
int readAveraged(int pin) {
  long sum = 0;
  for (int i = 0; i < OVERSAMPLE_COUNT; i++) {
    sum += analogRead(pin);
  }
  return (int)(sum / OVERSAMPLE_COUNT);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  // ADC pins are input-only on ESP32, no pinMode needed for analogRead,
  // but setting explicitly for clarity / safety.
  pinMode(PIN_C, INPUT);
  pinMode(PIN_TH, INPUT);
  pinMode(PIN_TLJ, INPUT);
  pinMode(PIN_L, INPUT);

  pinMode(PIN_MOTOR, OUTPUT);
  digitalWrite(PIN_MOTOR, LOW);

  // ESP32 default ADC resolution is 12-bit (0-4095) — explicit for clarity
  analogReadResolution(12);

  lastSampleTime = millis();
}

void loop() {
  unsigned long now = millis();

  // ---- Check for incoming serial command ----
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'V') {
      motorActive = true;
      motorStartTime = now;
      digitalWrite(PIN_MOTOR, HIGH);
    }
  }

  // ---- Turn motor off after pulse duration ----
  if (motorActive && (now - motorStartTime >= MOTOR_PULSE_MS)) {
    digitalWrite(PIN_MOTOR, LOW);
    motorActive = false;
  }

  // ---- Fixed 50Hz sensor sampling + JSON output ----
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;

    int val_c = readAveraged(PIN_C);
    int val_th = readAveraged(PIN_TH);
    int val_tlj = readAveraged(PIN_TLJ);
    int val_l = readAveraged(PIN_L);

    unsigned long t = millis();

    Serial.print("{\"t\":");
    Serial.print(t);
    Serial.print(",\"c\":");
    Serial.print(val_c);
    Serial.print(",\"th\":");
    Serial.print(val_th);
    Serial.print(",\"l\":");
    Serial.print(val_l);
    Serial.print(",\"tlj\":");
    Serial.print(val_tlj);
    Serial.println("}");
  }
}
