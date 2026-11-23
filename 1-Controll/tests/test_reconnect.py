# -*- coding: utf-8 -*-
"""
Test della riconnessione sicura (problema 10 della revisione), con il robot simulato.

Uso (dalla cartella 1-Controll):  python2.7 tests/test_reconnect.py .

Scenari:
  1. riconnessione manuale durante un gesto con l'anti-collisione spenta
  2. cambio robot (configure_target) durante un gesto
  3. robot che va offline durante un gesto (il gesto fallisce per forza):
     alla riconnessione anti-collisione e movimenti autonomi devono tornare attivi
  4. carico: gesti, letture del monitor, riconnessioni e braccia morbide in parallelo

Per ogni scenario si controlla lo stato del robot simulato alla fine:
protezioni attive, movimenti autonomi ripristinati, sessione e servizi coerenti.
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import os
import sys
import tempfile
import threading
import time
import traceback

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402

JOINTS = ["HeadYaw", "HeadPitch",
          "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
          "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand"]
POSE_A = [0.0, -0.2, 1.5, 0.15, -1.2, -0.5, 0.0, 0.6, 1.5, -0.15, 1.2, 0.5, 0.0, 0.6]
POSE_B = [0.0, 0.0, 0.2, 0.3, -1.0, -1.2, 0.5, 1.0, 0.2, -0.3, 1.0, 1.2, -0.5, 1.0]
# gesto di ~3 s con l'anti-collisione tra le braccia spenta per quasi tutto il tempo
LONG_GESTURE = [{"angles": POSE_A, "dt": 0.2}, {"angles": POSE_B, "dt": 2.6, "no_arm_collision": True},
                {"angles": POSE_A, "dt": 0.2}]

FAILURES = []
LOGS = []


def check(label, condition, detail=""):
    status = "OK  " if condition else "FAIL"
    print("  [%s] %s%s" % (status, label, (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


def robot_state():
    return fake_qi._ROBOT[0]


def wait_until(predicate, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def make_controller():
    tmp = tempfile.mkdtemp(prefix="ps_reconnect_")
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    config["paths"]["save_dir"] = tmp
    config["robot_defaults"]["gesture_pre_delay"] = 0.0
    config["robot_defaults"]["gesture_post_delay"] = 0.0
    config["robot"]["reconnect_interval"] = 0.3
    store = GestureStore(tmp, log_cb=LOGS.append)
    ctrl = PepperController(config, gesture_store=store, log_cb=LOGS.append)
    ctrl.connect()
    monitor = threading.Thread(target=ctrl.monitor_loop)
    monitor.daemon = True
    monitor.start()
    return ctrl


def run_async(fn, *args):
    box = {}

    def runner():
        try:
            box["result"] = fn(*args)
        except Exception as exc:
            box["error"] = "%s: %s" % (type(exc).__name__, exc)
    thread = threading.Thread(target=runner)
    thread.daemon = True
    thread.start()
    return thread, box


def check_final_state(ctrl, label):
    state = robot_state()
    check("%s: robot di nuovo connesso" % label, wait_until(lambda: ctrl.robot_connected, 6.0),
          ctrl.connection_state)
    protections = dict(state.protections)
    check("%s: anti-collisione braccio SX attiva" % label, protections.get("self:LArm", True), str(protections))
    check("%s: anti-collisione braccio DX attiva" % label, protections.get("self:RArm", True), str(protections))
    life = str(state.life_state)
    if life != "disabled":
        paused = [k for k in ("BackgroundMovement", "ListeningMovement", "SpeakingMovement") if not state.abilities.get(k)]
        check("%s: movimenti autonomi ripristinati" % label, not paused, "ancora in pausa: %s" % paused)
        check("%s: respiro delle braccia ripristinato" % label, state.breath.get("Arms", True), str(state.breath))
    robot = getattr(ctrl, "robot", None)
    session = ctrl.session
    services = [getattr(ctrl, name) for name in ("motion", "tts", "memory", "autonomous_life")]
    same = all(getattr(s, "_session", session) is session for s in services if s is not None)
    check("%s: tutti i servizi appartengono alla sessione attuale" % label, same)
    check("%s: sessione attuale aperta" % label, session is not None and not getattr(session, "_closed", False))
    del robot


def scenario_manual_reconnect(ctrl):
    print("1) Riconnessione manuale durante un gesto")
    fake_qi.MAX_SIMULATED_SECONDS = 4.0
    thread, box = run_async(ctrl.run_frames_gesture, JOINTS, LONG_GESTURE, "Arms")
    time.sleep(0.8)
    check("1: anti-collisione spenta durante il gesto (premessa del test)",
          not robot_state().protections.get("self:LArm", True))
    ctrl.request_reconnect()
    thread.join(10)
    result = box.get("result")
    check("1: il gesto e' terminato correttamente", bool(result and result[0]), str(result or box.get("error")))
    check_final_state(ctrl, "1")


def scenario_configure_target(ctrl):
    print("2) Cambio robot durante un gesto")
    fake_qi.MAX_SIMULATED_SECONDS = 4.0
    thread, box = run_async(ctrl.run_frames_gesture, JOINTS, LONG_GESTURE, "Arms")
    time.sleep(0.8)
    ok, message = ctrl.configure_target(True, "127.0.0.1", 9559)
    check("2: cambio robot accettato", ok, message)
    thread.join(10)
    result = box.get("result")
    check("2: il gesto e' terminato correttamente", bool(result and result[0]), str(result or box.get("error")))
    check_final_state(ctrl, "2")


def scenario_offline(ctrl):
    print("3) Robot offline durante un gesto")
    fake_qi.MAX_SIMULATED_SECONDS = 4.0
    thread, box = run_async(ctrl.run_frames_gesture, JOINTS, LONG_GESTURE, "Arms")
    time.sleep(0.8)
    ctrl.simulate_disconnect(3.0)
    thread.join(10)
    result = box.get("result")
    check("3: il gesto interrotto viene segnalato come fallito", result is not None and not result[0], str(result))
    check_final_state(ctrl, "3")
    lines = [l for l in LOGS if "riconnessione" in str(l).lower() and "anti-collisione" in str(l).lower()]
    check("3: il ripristino dopo la riconnessione compare nel log", bool(lines))


def scenario_stress(ctrl):
    print("4) Carico: gesti, monitor, riconnessioni e braccia morbide in parallelo (6 s)")
    fake_qi.MAX_SIMULATED_SECONDS = 0.15
    errors = []
    stop = threading.Event()
    short = [{"angles": POSE_A, "dt": 0.1}, {"angles": POSE_B, "dt": 0.1, "no_arm_collision": True},
             {"angles": POSE_A, "dt": 0.1}]

    def guard(fn):
        def loop():
            while not stop.is_set():
                try:
                    fn()
                except Exception:
                    errors.append(traceback.format_exc())
                time.sleep(0.01)
        return loop

    actions = [
        lambda: ctrl.run_frames_gesture(JOINTS, short, "Arms"),
        lambda: ctrl.play_gesture("assente"),
        lambda: (ctrl.refresh_obstacles(), ctrl.refresh_protections(), ctrl.refresh_temperatures()),
        lambda: (ctrl.get_pose(JOINTS), ctrl.validate_frame_pose(JOINTS, POSE_A)),
        lambda: (ctrl.start_soft_hold("left"), time.sleep(0.05), ctrl.stop_soft_hold()),
        lambda: (time.sleep(0.4), ctrl.request_reconnect()),
        lambda: (time.sleep(1.3), ctrl.configure_target(True, "127.0.0.1", 9559)),
        lambda: ctrl.say("prova"),
    ]
    threads = [threading.Thread(target=guard(a)) for a in actions]
    for t in threads:
        t.daemon = True
        t.start()
    time.sleep(6.0)
    stop.set()
    for t in threads:
        t.join(10)
    check("4: nessuna eccezione non gestita nei thread", not errors, errors[0][-400:] if errors else "")
    stuck = [t for t in threads if t.is_alive()]
    check("4: nessun thread bloccato", not stuck)
    fake_qi.MAX_SIMULATED_SECONDS = 0.02
    ctrl.stop_soft_hold()
    check_final_state(ctrl, "4")


def main():
    fake_qi.MAX_SIMULATED_SECONDS = 0.02
    ctrl = make_controller()
    for scenario in (scenario_manual_reconnect, scenario_configure_target, scenario_offline, scenario_stress):
        try:
            scenario(ctrl)
        except Exception:
            FAILURES.append(scenario.__name__)
            traceback.print_exc()
        wait_until(lambda: ctrl.robot_connected, 6.0)
        time.sleep(0.5)
    ctrl.running = False
    closed = [l for l in LOGS if "Sessione chiusa" in str(l)]
    print("Righe di log con comandi su sessione chiusa: %d" % len(closed))
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITI %d controlli: %s" % (len(FAILURES), ", ".join(FAILURES))))
    sys.stdout.flush()
    os._exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
