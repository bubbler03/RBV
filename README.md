# CNC Motor Control (Pi + CNC Shield v3 + TMC2209)

Flask-Dashboard zur Steuerung von 2 Schrittmotor-Achsen (X/Y) über GPIO.

## Setup auf neuem Pi

```bash
sudo apt update
sudo apt install python3-gpiozero python3-lgpio python3-flask
```

Kein venv nötig — alles läuft über System-Pakete (siehe `dist-packages`).

## Start

```bash
python3 motor_ui.py
```

Dashboard dann unter `http://<pi-ip>:5000`.

## Pinbelegung (BCM)

- 21 = Enable (active_high=False)
- 17 = X Step, 27 = X Dir
- 10 = Y Step, 7 = Y Dir

## Dateien

- `motor_ui.py` — Flask-Server + Achssteuerung (Move, Homing, Loop, Emergency Stop)
- `simple_motor_move.py` — einfacher Testlauf ohne Dashboard
- `templates/index.html` — Dashboard-Oberfläche
