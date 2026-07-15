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


PAIR_AXES = {
    "xy": ["x", "y"],
    "za": ["z", "a"],
}

def do_move(axis, steps, direction, delay_end=0.002):
    delay_start = min(delay_end * 3, 0.010)
    ramp_steps  = min(30, abs(steps) // 2)
    a = axes[axis]
    a["dir"].on() if direction > 0 else a["dir"].off()
    sleep(0.001)
    moved = 0
    for i in range(abs(steps)):
        d = delay_start - (delay_start - delay_end) * (i / ramp_steps) if i < ramp_steps else delay_end
        a["step"].on();  sleep(d)
        a["step"].off(); sleep(d)
        moved += 1
    a["position"] += moved * direction


def move_parallel(steps, direction, delay=0.002, pair="xy"):
    axis_names = PAIR_AXES[pair]
    threads = [threading.Thread(target=do_move, args=(ax, steps, direction, delay)) for ax in axis_names if ax in axes]
    for t in threads: t.start()
    for t in threads: t.join()


def move_until_stop(pair, direction, speed):
    axis_names = [ax for ax in PAIR_AXES[pair] if ax in axes]
    devs = [axes[ax] for ax in axis_names]
    for a in devs:
        a["dir"].on() if direction > 0 else a["dir"].off()
    sleep(0.001)
    while not stop_flags[pair]:
        for a in devs: a["step"].on()
        sleep(speed)
        for a in devs: a["step"].off()
        sleep(speed)
        for ax in axis_names:
            axes[ax]["position"] += direction


def run_homing(pair="xy", speed=0.0005):
    stop_flags[pair] = False
    h = homing[pair]
    axis_names = [ax for ax in PAIR_AXES[pair] if ax in axes]
    with move_lock:
        h["status"] = "homing_up"
        move_until_stop(pair, -1, speed)
        for ax in axis_names:
            axes[ax]["position"] = 0
        stop_flags[pair] = False

        h["status"] = "homing_down"
        move_until_stop(pair, 1, speed)
        h["work_area"] = abs(axes[axis_names[0]]["position"]) if axis_names else 0
        h["status"] = "done"


def run_loop(cycles, delay, height_pct=100):
    loop_state["running"] = True
    loop_state["total"]   = cycles
    loop_state["current"] = 0
    work = int(homing["xy"]["work_area"] * height_pct / 100)
    for i in range(cycles):
        if not loop_state["running"]:
            break
        loop_state["current"] = i + 1
        with move_lock:
            move_parallel(work, -1, delay, pair="xy")
            move_parallel(work,  1, delay, pair="xy")
    loop_state["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/enable", methods=["POST"])
def enable_motor():
    enable.on(); state["enabled"] = True
    return jsonify(get_state())


@app.route("/disable", methods=["POST"])
def disable_motor():
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
        tx = threading.Thread(target=do_move, args=("x", steps, dir_x, delay))
        ty = threading.Thread(target=do_move, args=("y", steps, dir_y, delay))
        tx.start(); ty.start()
        tx.join();  ty.join()
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
        app.run(host="0.0.0.0", port=5000)
    finally:
        enable.off()
