import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from flask import Flask, request, jsonify, render_template
from gpiozero import OutputDevice
from time import sleep
import threading

app = Flask(__name__)

enable = OutputDevice(21, active_high=False, initial_value=False)

axes = {
    "x": {"step": OutputDevice(17), "dir": OutputDevice(27), "position": 0},
    "y": {"step": OutputDevice(10), "dir": OutputDevice(7),  "position": 0},
}

state      = {"enabled": False}
homing     = {
    "xy": {"status": "idle", "work_area": 0},
    "za": {"status": "idle", "work_area": 0},
}
loop_state = {"running": False, "total": 0, "current": 0}
move_lock  = threading.Lock()
stop_flags = {"xy": False, "za": False}
abort      = threading.Event()   # Not-Aus / Motoren aus: beendet jede laufende Fahrt sofort


PAIR_AXES = {
    "xy": ["x", "y"],
    "za": ["z", "a"],
}

def do_move(axis, steps, direction, delay_end=0.002):
    return do_move_sync([axis], steps, direction, delay_end)


def do_move_sync(axis_names, steps, direction, delay_end=0.002):
    """Faehrt mehrere Achsen taktgleich: beide STEP-Pins gehen im selben Takt high/low.
    Pulsform und Rampe identisch zur bisherigen do_move()."""
    delay_start = min(delay_end * 3, 0.010)
    ramp_steps  = min(30, abs(steps) // 2)
    devs = [axes[ax] for ax in axis_names if ax in axes]
    for a in devs:
        a["dir"].on() if direction > 0 else a["dir"].off()
    sleep(0.001)
    moved = 0
    for i in range(abs(steps)):
        if abort.is_set():
            break
        d = delay_start - (delay_start - delay_end) * (i / ramp_steps) if i < ramp_steps else delay_end
        for a in devs: a["step"].on()
        sleep(d)
        for a in devs: a["step"].off()
        sleep(d)
        for a in devs: a["position"] += direction      # Position live mitzaehlen
        moved += 1
    return moved


def move_parallel(steps, direction, delay=0.002, pair="xy"):
    return do_move_sync(PAIR_AXES[pair], steps, direction, delay)


def move_until_stop(pair, direction, speed):
    axis_names = [ax for ax in PAIR_AXES[pair] if ax in axes]
    devs = [axes[ax] for ax in axis_names]
    for a in devs:
        a["dir"].on() if direction > 0 else a["dir"].off()
    sleep(0.001)
    start = min(speed * 3, 0.010)          # Anfahrrampe wie bei do_move, gegen Schrittverlust
    i = 0
    while not stop_flags[pair] and not abort.is_set():
        d = start - (start - speed) * (i / 30) if i < 30 else speed
        for a in devs: a["step"].on()
        sleep(d)
        for a in devs: a["step"].off()
        sleep(d)
        for ax in axis_names:
            axes[ax]["position"] += direction
        i += 1


def run_homing(pair="xy", speed=0.0005):
    stop_flags[pair] = False
    h = homing[pair]
    axis_names = [ax for ax in PAIR_AXES[pair] if ax in axes]
    try:
        with move_lock:
            h["status"] = "homing_up"
            move_until_stop(pair, -1, speed)
            if abort.is_set():
                h["status"] = "idle"; h["work_area"] = 0
                return
            for ax in axis_names:
                axes[ax]["position"] = 0
            stop_flags[pair] = False

            h["status"] = "homing_down"
            move_until_stop(pair, 1, speed)
            if abort.is_set():
                h["status"] = "idle"; h["work_area"] = 0
                return
            h["work_area"] = abs(axes[axis_names[0]]["position"]) if axis_names else 0
            h["status"] = "done"
    except Exception as e:
        print("Fehler in der Referenzfahrt:", e)
        h["status"] = "idle"; h["work_area"] = 0
    finally:
        stop_flags[pair] = False


def run_loop(cycles, delay, height_pct=100):
    loop_state["running"] = True
    loop_state["total"]   = cycles
    loop_state["current"] = 0
    work = int(homing["xy"]["work_area"] * height_pct / 100)
    try:
        for i in range(cycles):
            if not loop_state["running"] or abort.is_set():
                break
            loop_state["current"] = i + 1
            with move_lock:
                move_parallel(work, -1, delay, pair="xy")
                move_parallel(work,  1, delay, pair="xy")
    except Exception as e:
        print("Fehler im Hubzyklus:", e)
    finally:
        loop_state["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/enable", methods=["POST"])
def enable_motor():
    abort.clear()
    enable.on(); state["enabled"] = True
    return jsonify(get_state())


@app.route("/disable", methods=["POST"])
def disable_motor():
    abort.set()                      # laufende Fahrt beenden, sonst laeuft sie nach "Ein" weiter
    loop_state["running"] = False
    enable.off(); state["enabled"] = False
    return jsonify(get_state())


@app.route("/move", methods=["POST"])
def move():
    if not state["enabled"]:       return jsonify({"error": "Motor nicht aktiviert"}), 400
    if move_lock.locked():         return jsonify({"error": "Bewegung läuft"}), 400
    d      = request.get_json()
    axis   = d.get("axis", "x")
    steps  = int(d.get("steps", 0))
    dirn   = int(d.get("dir", 1))
    delay  = float(d.get("delay", 0.002))
    if axis not in axes or steps <= 0: return jsonify({"error": "Ungültige Parameter"}), 400
    with move_lock:
        do_move(axis, steps, dirn, delay)
    return jsonify(get_state())


@app.route("/move_both", methods=["POST"])
def move_both():
    if not state["enabled"]: return jsonify({"error": "Motor nicht aktiviert"}), 400
    if move_lock.locked():   return jsonify({"error": "Bewegung läuft"}), 400
    d     = request.get_json()
    steps = int(d.get("steps", 0))
    delay = float(d.get("delay", 0.002))
    dir_x = int(d.get("dir_x", 1))
    dir_y = int(d.get("dir_y", 1))
    if steps <= 0: return jsonify({"error": "Ungültige Schrittanzahl"}), 400
    with move_lock:
        if dir_x == dir_y:
            do_move_sync(["x", "y"], steps, dir_x, delay)     # taktgleich
        else:
            do_move("x", steps, dir_x, delay)                 # Sonderfall: gegenlaeufig nacheinander
            do_move("y", steps, dir_y, delay)
    return jsonify(get_state())


@app.route("/home", methods=["POST"])
def start_homing():
    if not state["enabled"]: return jsonify({"error": "Motor nicht aktiviert"}), 400
    if move_lock.locked():   return jsonify({"error": "Bewegung läuft"}), 400
    d    = request.get_json(silent=True) or {}
    pair = d.get("pair", "xy")
    if pair not in PAIR_AXES: return jsonify({"error": "Ungültiges Paar"}), 400
    homing[pair]["status"] = "starting"
    threading.Thread(target=run_homing, args=(pair, 0.0005), daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/start_loop", methods=["POST"])
def start_loop_route():
    if not state["enabled"]:              return jsonify({"error": "Motor nicht aktiviert"}), 400
    if homing["xy"]["status"] != "done": return jsonify({"error": "Erst Homing durchführen"}), 400
    if loop_state["running"]:      return jsonify({"error": "Schleife läuft bereits"}), 400
    d           = request.get_json()
    cycles      = int(d.get("cycles", 1))
    delay       = float(d.get("delay", 0.002))
    height_pct  = int(d.get("height_pct", 100))
    threading.Thread(target=run_loop, args=(cycles, delay, height_pct), daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/emergency_stop", methods=["POST"])
def emergency_stop():
    abort.set()
    stop_flags["xy"]       = True
    stop_flags["za"]       = True
    loop_state["running"]  = False
    enable.off()
    state["enabled"]       = False
    return jsonify(get_state())


@app.route("/stop_homing", methods=["POST"])
def stop_homing():
    d    = request.get_json(silent=True) or {}
    pair = d.get("pair", "xy")
    if pair in stop_flags:
        stop_flags[pair] = True
    return jsonify({"status": "stopping"})


@app.route("/stop_loop", methods=["POST"])
def stop_loop():
    loop_state["running"] = False
    return jsonify({"status": "stopping"})


@app.route("/status")
def status():
    return jsonify(get_state())


def get_state():
    return {
        "enabled":   state["enabled"],
        "x":         axes["x"]["position"],
        "y":         axes["y"]["position"],
        "homing":    homing,
        "loop":      loop_state,
        "busy":      move_lock.locked(),
    }


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        enable.off()
