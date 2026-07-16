import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from gpiozero import OutputDevice
from time import sleep

# --- Y-ACHSE KONFIGURATION ---
# BCM 21 = Pin 40 (Enable, shared)
# BCM 10 = Pin 19 (Y Step)
# BCM 7  = Pin 26 (Y Dir)

enable   = OutputDevice(21, active_high=False, initial_value=False)
step_pin = OutputDevice(10)
dir_pin  = OutputDevice(7)

def run_y_test():
    try:
        print("=== Y-ACHSE TESTLAUF ===")
        print()

        print("1) Enable AN - Motor sollte fest werden...")
        enable.on()
        sleep(1.0)

        print("2) Drehe VORWAERTS - 200 Steps...")
        dir_pin.on()
        sleep(0.1)
        for i in range(200):
            step_pin.on();  sleep(0.05)
            step_pin.off(); sleep(0.05)
            if i % 50 == 0: print(f"   Step {i}/200")
        print("   Fertig!")
        sleep(1.0)

        print("3) Drehe RUECKWAERTS - 200 Steps...")
        dir_pin.off()
        sleep(0.1)
        for i in range(200):
            step_pin.on();  sleep(0.05)
            step_pin.off(); sleep(0.05)
            if i % 50 == 0: print(f"   Step {i}/200")
        print("   Fertig!")

        print()
        print("=== TEST ABGESCHLOSSEN ===")
        print("Falls Motor nicht dreht: Step/Dir Kabel am Shield tauschen!")

    finally:
        enable.off()
        step_pin.off()
        dir_pin.off()

if __name__ == "__main__":
    run_y_test()
