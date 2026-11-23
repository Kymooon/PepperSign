# -*- coding: utf-8 -*-
"""
Test di non regressione per il refactor di Controll (Python 2.7, robot simulato).
Uso: python2.7 harness.py <cartella Controll> <output.json>
Registra i risultati di ogni chiamata pubblica e il log del controller, cosi'
il comportamento prima e dopo il refactor si puo' confrontare riga per riga.
"""
from __future__ import print_function

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import BaseHTTPServer

ROOT = os.path.abspath(sys.argv[1])
OUT = sys.argv[2]
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402

fake_qi.MAX_SIMULATED_SECONDS = 0.02

from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign import controller as controller_module  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign.utils import write_json  # noqa: E402

RESULTS = []
LOGS = []
LOG_LOCK = threading.Lock()


def norm(value):
    """Arrotonda i float per un confronto stabile."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (list, tuple)):
        return [norm(v) for v in value]
    if isinstance(value, dict):
        return dict((str(k), norm(v)) for k, v in value.items())
    if isinstance(value, unicode):
        return value.encode("utf-8")
    return value


def log_cb(message):
    with LOG_LOCK:
        LOGS.append(message if isinstance(message, str) else message.encode("utf-8"))


def call(label, fn, *args, **kwargs):
    with LOG_LOCK:
        LOGS.append("=== %s" % label)
    try:
        result = fn(*args, **kwargs)
        RESULTS.append([label, "ok", norm(result)])
    except Exception as exc:
        RESULTS.append([label, "exc", "%s: %s" % (type(exc).__name__, exc)])


# ------------------------------------------------------------------ setup
tmp = tempfile.mkdtemp(prefix="ps_harness_")
gdir = os.path.join(tmp, "gestures")
os.makedirs(gdir)
JOINTS = ["HeadYaw", "HeadPitch",
          "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
          "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand"]
POSE_A = [0.0, -0.2, 1.5, 0.15, -1.2, -0.5, 0.0, 0.6, 1.5, -0.15, 1.2, 0.5, 0.0, 0.6]
POSE_B = [0.3, 0.3, 0.2, 0.3, -1.0, -1.2, 0.5, 1.0, -0.5, -0.4, 1.1, 1.4, -0.3, 0.0]
FRAMES = [{"angles": POSE_A, "dt": 0.8}, {"angles": POSE_B, "dt": 0.05, "no_arm_collision": True},
          {"angles": POSE_A, "dt": 1.2}]
write_json(os.path.join(gdir, "ciao.json"), {"name": "Ciao", "format": "frames_v1", "joints": JOINTS,
                                             "frames": FRAMES})
# formato ready_v1 non piu' supportato (rimosso il 10/11/2026): deve essere rifiutato senza muovere il robot
write_json(os.path.join(gdir, "acqua_ready_1.json"), {
    "name": "acqua", "format": "ready_v1", "joints": ["RShoulderPitch", "RHand", "HeadPitch", "HeadYaw"],
    "times": [[0.5, 1.0], [0.5, 1.0], [0.5, 1.0], [0.5, 1.0]],
    "angles": [[-3.0, 1.0], [0.2, 1.5], [0.9, -0.9], [2.0, 0.0]],
    "no_arm_collision_windows": [[0.0, 0.6]], "arm_collision_chain": "RArm"})
write_json(os.path.join(gdir, "rotto.json"), {"format": "frames_v1"})

config = build_runtime_config(None)
config["paths"]["gesture_dir"] = gdir
config["paths"]["save_dir"] = gdir
config["robot_defaults"]["gesture_pre_delay"] = 0.0
config["robot_defaults"]["gesture_post_delay"] = 0.0
config["webapp"]["poll_sleep_ok"] = 0.01
config["webapp"]["poll_sleep_idle"] = 0.01
config["webapp"]["poll_sleep_error"] = 0.05
config["webapp"]["poll_timeout"] = 2

store = GestureStore(gdir, log_cb=log_cb)
store.reload()
ctrl = PepperController(config, gesture_store=store, log_cb=log_cb)

# superficie pubblica (metodi e attributi usati da GUI/main)
surface = sorted(n for n in dir(ctrl) if not n.startswith("_"))
module_names = sorted(n for n in dir(controller_module) if not n.startswith("_"))

call("connect", ctrl.connect)
for attr in ("robot_connected", "connection_state", "fake_robot", "robot_ip", "robot_port",
             "cached_volume", "cached_life_state", "reconnect_interval", "last_error",
             "connected_to_webapp", "last_cmd", "running"):
    call("attr " + attr, getattr, ctrl, attr)

# voce e volume
call("say", ctrl.say, u"Ciao città")
call("say vuoto", ctrl.say, "  ")
call("say_animated", ctrl.say_animated, "buongiorno")
call("say_animated vuoto", ctrl.say_animated, "")
call("get_volume", ctrl.get_volume)
call("set_volume", ctrl.set_volume, 55)
call("set_volume 150", ctrl.set_volume, 150)
call("volume_up", ctrl.volume_up)
call("volume_down", ctrl.volume_down, 25)
call("attr cached_volume 2", getattr, ctrl, "cached_volume")

# autonomia
call("life off", ctrl.set_autonomous_life, False)
call("life state", ctrl.get_autonomous_life_state)
call("life on", ctrl.set_autonomous_life, True)
call("life state 2", ctrl.get_autonomous_life_state)
call("attr cached_life_state 2", getattr, ctrl, "cached_life_state")

# stiffness, mani, pose
for name in ("free_arms", "hold_arms", "free_left_arm", "hold_left_arm", "free_right_arm",
             "hold_right_arm", "move_only_left_arm", "move_only_right_arm", "free_head", "hold_head",
             "open_both_hands", "close_both_hands"):
    call(name, getattr(ctrl, name))
call("open_hand L", ctrl.open_hand, "LHand")
call("close_hand R", ctrl.close_hand, "RHand")
call("set_hand bad", ctrl.set_hand, "XHand", True)
call("set_stiffness", ctrl.set_stiffness, ["LHand"], 0.5)
call("get_pose", ctrl.get_pose, JOINTS)
call("center_head_forward", ctrl.center_head_forward, 5.0)
call("prepare_gesture_recording", ctrl.prepare_gesture_recording)

# validazione, limiti, interpolazione
call("validate ok", ctrl.validate_frame_pose, JOINTS, POSE_A)
call("validate near/out", ctrl.validate_frame_pose, JOINTS,
     [0.0, 0.44, 2.08, 0.15, -1.2, -0.5, 0.0, 0.6, 1.5, -0.15, 1.2, 3.0, 0.0, 0.6])
call("validate nan", ctrl.validate_frame_pose, JOINTS, [float("nan")] * 14)
call("validate len", ctrl.validate_frame_pose, JOINTS, [0.0])
call("validate empty", ctrl.validate_frame_pose, [], [])
call("validate headpitch", ctrl.validate_frame_pose, ["HeadYaw", "HeadPitch"], [1.9, 0.4])
call("head_pitch_limits", ctrl.head_pitch_limits, 1.2)
call("clamp", ctrl.clamp_angles_to_limits, JOINTS,
     [5.0, 5.0, 5.0, -5.0, 5.0, 5.0, 5.0, 5.0, -5.0, 5.0, -5.0, -5.0, 5.0, -5.0])
call("build_interpolation", ctrl.build_interpolation_from_frames, JOINTS, FRAMES)
call("build_interpolation short", ctrl.build_interpolation_from_frames, JOINTS,
     [{"angles": [0.1], "dt": "x"}])
call("build_interpolation empty", ctrl.build_interpolation_from_frames, JOINTS, [])
call("arm_collision_windows", controller_module.arm_collision_windows, FRAMES)
call("frame_dt", controller_module.frame_dt, {"dt": 0.01})
call("native_joint_names", controller_module.native_joint_names, u"LHand")
call("normalize_collision_chain", controller_module.normalize_collision_chain, "xx")
call("validate_robot_address", controller_module.validate_robot_address, "127.0.0.1", "9559")
call("validate_robot_address bad", controller_module.validate_robot_address, "a b", 1)
call("validate_robot_address port", controller_module.validate_robot_address, "127.0.0.1", 70000)

# esecuzione dei gesti
call("run_frames_gesture", ctrl.run_frames_gesture, JOINTS, FRAMES, collision_chain="Arms")
call("run_frames_gesture empty", ctrl.run_frames_gesture, JOINTS, [])
call("play ciao", ctrl.play_gesture, "Ciao")
call("play acqua", ctrl.play_gesture, "acqua")
call("play missing", ctrl.play_gesture, "nessuno")
call("play empty", ctrl.play_gesture, "")
call("go_to_pose", ctrl.go_to_pose, JOINTS, POSE_B)
call("go_to_pose bad", ctrl.go_to_pose, JOINTS, [0.0])
call("pose after", ctrl.get_pose, JOINTS)

# braccia morbide
call("soft state 0", ctrl.soft_hold_state)
call("soft bad group", ctrl.start_soft_hold, "x")
call("soft start", ctrl.start_soft_hold, "left", 0.4)
call("soft state 1", ctrl.soft_hold_state)
time.sleep(0.3)
call("soft stop", ctrl.stop_soft_hold, 1.0)
call("soft stop again", ctrl.stop_soft_hold)
call("soft start 2", ctrl.start_soft_hold, "both")
call("gesture while soft", ctrl.run_frames_gesture, JOINTS, [{"angles": POSE_A, "dt": 0.5}])
call("soft state 2", ctrl.soft_hold_state)

# sicurezza
call("refresh_protections", ctrl.refresh_protections)
call("attr cached_protections", getattr, ctrl, "cached_protections")
call("set_protection off", ctrl.set_protection, "self_Arms", False)
call("set_protection diag", ctrl.set_protection, "diagnosis", False)
call("set_protection unknown", ctrl.set_protection, "zzz", False)
call("set_protection ext", ctrl.set_protection, "external_LArm", False)
call("restore_protections", ctrl.restore_protections)
call("restore_protections 2", ctrl.restore_protections)
call("simulate_obstacle", ctrl.simulate_obstacle, [0.25, -0.35, 0.0])
call("refresh_obstacles", ctrl.refresh_obstacles)
call("attr cached_obstacles", getattr, ctrl, "cached_obstacles")
call("simulate_obstacle off", ctrl.simulate_obstacle, None)
call("refresh_temperatures", ctrl.refresh_temperatures)
call("temperatures keys", lambda: sorted(ctrl.cached_temperatures.keys()))
call("hottest_joint", ctrl.hottest_joint)
call("temperature_level", ctrl.temperature_level, 65.0, None)
call("temperature_level status", ctrl.temperature_level, 30.0, 2)
call("safety_counts", ctrl.safety_counts)
call("safety_events keys", lambda: sorted(ctrl.safety_events.keys()))
call("reset_safety_counts", ctrl.reset_safety_counts)

# comandi della WebApp (dispatcher)
for cmd in ({"action": "SAY", "text": "ciao"}, {"action": "animated_say", "text": "ok"},
            {"action": "PLAY_GESTURE", "gestureId": "ciao"}, {"action": "PLAY_GESTURE", "gestureId": "xx"},
            {"action": "WAKEUP"}, {"action": "REST"}, {"action": "LIFE_OFF"}, {"action": "LIFE_ON"},
            {"action": "NONE"}, {"action": ""}, {"action": "BOH"},
            {"action": "SAY_AND_LISTEN", "sessionId": "s1", "prompt": "parla"},
            {"action": "SAY_AND_LISTEN"}):
    call("handle_command %s" % cmd.get("action"), ctrl.handle_command, cmd)
call("wakeup", ctrl.wakeup)
call("rest", ctrl.rest)
call("set_error", ctrl.set_error, "errore di prova")
call("attr last_error", getattr, ctrl, "last_error")

# polling della WebApp con un server HTTP locale
COMMANDS = [{"action": "SAY", "text": "dal web"}, {"action": "PLAY_GESTURE", "gestureId": "ciao"}]
SERVED = []


class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        cmd = COMMANDS.pop(0) if COMMANDS else {"action": "NONE"}
        SERVED.append(cmd["action"])
        body = json.dumps(cmd)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = BaseHTTPServer.HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever).start()
ctrl.config["webapp"]["next_url"] = "http://127.0.0.1:%d/api/pepper/next" % server.server_address[1]
poll = threading.Thread(target=ctrl.poll_webapp_loop)
poll.daemon = True
poll.start()
time.sleep(1.5)
call("poll served", lambda: SERVED[:3])
call("poll connected", getattr, ctrl, "connected_to_webapp")
call("poll last_cmd", getattr, ctrl, "last_cmd")
ctrl.config["webapp"]["poll_sleep_error"] = 1000   # dopo il primo errore il polling si ferma: log stabile
server.shutdown()
server.server_close()
end = time.time() + 6.0          # attendo che il polling si accorga della WebApp spenta
while ctrl.connected_to_webapp and time.time() < end:
    time.sleep(0.05)
time.sleep(0.3)
call("poll lost", getattr, ctrl, "connected_to_webapp")

# monitor: disconnessione simulata e riconnessione automatica
ctrl.reconnect_interval = 0.2
monitor = threading.Thread(target=ctrl.monitor_loop)
monitor.daemon = True
monitor.start()
time.sleep(1.5)
call("monitor cache volume", getattr, ctrl, "cached_volume")
call("simulate_disconnect", ctrl.simulate_disconnect, 1)
time.sleep(0.8)
call("monitor disconnected", lambda: (ctrl.robot_connected, ctrl.connection_state.split(" ")[0]))
time.sleep(2.5)
call("monitor reconnected", lambda: (ctrl.robot_connected, ctrl.connection_state))
call("configure_target bad", ctrl.configure_target, False, "a b", 9559)
call("configure_target demo", ctrl.configure_target, True, "10.0.0.5", "9600")
time.sleep(2.0)
call("after configure", lambda: (ctrl.robot_connected, ctrl.robot_ip, ctrl.robot_port, ctrl.fake_robot))
call("request_reconnect", ctrl.request_reconnect)
time.sleep(2.0)
call("after reconnect", getattr, ctrl, "robot_connected")
ctrl.running = False
time.sleep(1.2)

# ------------------------------------------------------------------ output
NUM = re.compile(r"\d+(\.\d+)?")
THREAD_NOISE = ("Anti-collisione braccia OFF a", "Anti-collisione braccia di nuovo ON a", "[POLL]",
                "Polling WebApp fallito", "Connessione alla Web App", "perso la connessione",
                "ALMemory", "getListData", "getChainClosestObstaclePosition", "getPosition(",
                "isConnected", "Riconnessione", "riprovo", "Connessione QI", "[MORBIDO]",
                "getAngles", "setAngles", "getOutputVolume", "getState", "Get", "get",
                "is", "Collision")


def clean(lines):
    out = []
    for line in lines:
        out.append(NUM.sub("#", line))
    return out


main_log = clean(LOGS)
result = {"surface": surface, "module": module_names, "results": RESULTS,
          "log": main_log}
with open(OUT, "w") as handle:
    json.dump(result, handle, indent=1, sort_keys=True)
shutil.rmtree(tmp, ignore_errors=True)
print("OK: %d risultati, %d righe di log" % (len(RESULTS), len(LOGS)))
os._exit(0)
