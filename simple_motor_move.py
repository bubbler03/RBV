import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from gpiozero import OutputDevice
from time import sleep

# --- KONFIGURATION (Basierend auf unserem 100% Plan) ---
# BCM 21 = Physischer Pin 40 (Enable)
# BCM 17 = Physischer Pin 11 (Step)
# BCM 27 = Physischer Pin 13 (Direction)

# active_high=False bedeutet: 0V (LOW) schaltet den Motor AN
enable = OutputDevice(21, active_high=False, initial_value=False)
step_pin = OutputDevice(17)
dir_pin = OutputDevice(27)

def run_stepper_test():
    try:
        print("--- START DES TESTLAUFS ---")

        # 1. Treiber aktivieren
        print("Schritt 1: Aktiviere Treiber (Motor sollte jetzt fest werden)...")
        enable.on() # Setzt GPIO 21 auf LOW
        sleep(1.0) # Kurze Pause zum Prüfen des Haltemoments

        # 2. Vorwärts drehen
        print("Schritt 2: Drehe vorwärts (3200 Schritte / 1 Umdrehung)...")
        dir_pin.on() # Richtung festlegen
        for i in range(3200):
            step_pin.on()
            sleep(0.002) # Puls-Dauer (0.002s ist sicher und flüssig)
            step_pin.off()
            sleep(0.002)

        sleep(0.5) # Kurze Pause zwischen den Richtungen

        # 3. Rückwärts drehen
        print("Schritt 3: Drehe rückwärts...")
        dir_pin.off() # Richtung wechseln
        for i in range(3200):
            step_pin.on()
            sleep(0.002)
            step_pin.off()
            sleep(0.002)

        print("--- TEST ERFOLGREICH BEENDET ---")

    except KeyboardInterrupt:
        print("\nAbbruch durch Nutzer...")

    finally:
        # 4. Sicherheit: Motor immer stromlos schalten am Ende
        enable.off() # Setzt GPIO 21 auf HIGH (Motor aus)
        print("Treiber deaktiviert (Motor ist wieder locker).")

if __name__ == "__main__":
    run_stepper_test()
