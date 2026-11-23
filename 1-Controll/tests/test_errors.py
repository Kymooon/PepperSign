# -*- coding: utf-8 -*-
"""
Test della gestione degli errori (problema 9 della revisione), con il robot simulato.

Uso (dalla cartella 1-Controll):  python2.7 tests/test_errors.py .

Fa fallire apposta alcune parti del robot simulato e controlla che:
  - l'errore compaia nel log invece di sparire;
  - un errore che si ripete (es. a ogni lettura del monitor) compaia una volta
    sola nella finestra di limitazione, non a raffica;
  - un'API opzionale mancante venga segnalata una sola volta;
  - i metodi pubblici restituiscano (ok, messaggio) o (ok, dati, messaggio).
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import json
import os
import sys
import tempfile
import threading
import time
import BaseHTTPServer

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign.robot.interpolation import frame_dt  # noqa: E402
from peppersign.robot.joints import is_valid_number  # noqa: E402

fake_qi.MAX_SIMULATED_SECONDS = 0.02
FAILURES = []
LOGS = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


def count(fragment):
    return len([l for l in LOGS if fragment in str(l)])


def broken(*args, **kwargs):
    raise RuntimeError("guasto simulato")


def main():
    tmp = tempfile.mkdtemp(prefix="ps_errors_")
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    config["robot_defaults"]["gesture_pre_delay"] = 0.0
    config["robot_defaults"]["gesture_post_delay"] = 0.0
    ctrl = PepperController(config, gesture_store=GestureStore(tmp, log_cb=LOGS.append), log_cb=LOGS.append)
    ctrl.connect()
    joints = ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand"]

    print("1) Ritorni uniformi")
    for name, args in (("say", ("ciao",)), ("say", ("",)), ("wakeup", ()), ("rest", ()),
                       ("say_animated", ("ciao",)), ("set_volume", (40,)), ("free_arms", ()),
                       ("hold_arms", ()), ("play_gesture", ("assente",)), ("go_to_pose", (joints, [0.0]))):
        result = getattr(ctrl, name)(*args)
        check("%s%r -> (ok, messaggio)" % (name, args),
              isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool), repr(result))
    result = ctrl.get_pose(joints)
    check("get_pose -> (ok, angoli, messaggio)", isinstance(result, tuple) and len(result) == 3 and result[0]
          and len(result[1]) == len(joints), repr(result))

    print("2) Errore ripetuto del monitor: nel log una volta sola")
    ctrl.monitor.hooks["refresh_obstacles"] = broken     # lettura degli ostacoli che fallisce sempre
    monitor = threading.Thread(target=ctrl.monitor_loop)
    monitor.daemon = True
    monitor.start()
    time.sleep(3.5)            # 3-4 letture degli ostacoli
    n = count("[MONITOR] Lettura di ostacoli non riuscita")
    check("errore delle letture degli ostacoli nel log", n >= 1, "righe: %d" % n)
    check("errore ripetuto scritto una sola volta (limitazione)", n == 1, "righe: %d" % n)

    print("3) Temperature non leggibili")
    ctrl.robot.memory._service.getListData = broken
    ctrl.refresh_temperatures()
    ctrl.refresh_temperatures()
    n = count("[TEMPERATURA] Temperature dei motori non leggibili")
    check("errore delle temperature nel log una volta", n == 1, "righe: %d" % n)

    print("4) API opzionale mancante: segnalata una volta")
    ctrl.robot.motion._service.isCollision = broken
    frames = [{"angles": [0.5, 0.3, -1.0, -0.6, 0.0, 0.5], "dt": 0.2, "no_arm_collision": True},
              {"angles": [1.5, 0.15, -1.2, -0.5, 0.0, 0.6], "dt": 0.2}]
    for _ in range(3):
        ok, message = ctrl.run_frames_gesture(joints, frames, collision_chain="Arms")
    check("gesto eseguito anche senza isCollision", ok, message)
    n = count("ALMotion.isCollision non disponibile")
    check("isCollision mancante segnalato una sola volta", n == 1, "righe: %d" % n)

    print("5) Limiti di un giunto non disponibili")
    original = ctrl.robot.motion._service.getLimits

    def limits(name):
        if name == "LWristYaw":
            raise RuntimeError("giunto sconosciuto")
        return original(name)
    ctrl.robot.motion._service.getLimits = limits
    ctrl.limits.reset()
    ctrl.validate_frame_pose(joints, [1.5, 0.15, -1.2, -0.5, 0.0, 0.6])
    ctrl.validate_frame_pose(joints, [1.5, 0.15, -1.2, -0.5, 0.0, 0.6])
    n = count("[LIMITI] Limiti di LWristYaw non disponibili")
    check("limiti mancanti segnalati una volta", n == 1, "righe: %d" % n)

    print("6) Braccia morbide: errore del ciclo nel log")
    ctrl.start_soft_hold("left")
    original_get_angles = ctrl.robot.motion._service.getAngles
    ctrl.robot.motion._service.getAngles = broken
    time.sleep(0.5)
    ctrl.stop_soft_hold(final_stiffness=None)
    n = count("[MORBIDO] Il braccio non segue la mano dell'operatore")
    check("errore del ciclo delle braccia morbide nel log una volta", n == 1, "righe: %d" % n)

    print("7) Numeri enormi nei file dei gesti (interi oltre il limite dei float)")
    huge = 10 ** 400
    check("is_valid_number(10**400) -> False", is_valid_number(huge) is False)
    check("frame_dt con dt enorme -> 0.6 (valore di default)", frame_dt({"dt": huge}) == 0.6)
    ok, warnings, errors = ctrl.validate_frame_pose(joints, [huge, 0.15, -1.2, -0.5, 0.0, 0.6])
    check("validate_frame_pose segnala il valore non valido", not ok and errors, repr(errors))
    ctrl.robot.motion._service.getAngles = original_get_angles
    try:
        # dal punto 2 (09/11): un dt non valido rende il gesto non valido -> rifiutato, senza eccezioni
        result = ctrl.run_frames_gesture(joints, [{"angles": [1.5, 0.15, -1.2, -0.5, 0.0, 0.6], "dt": huge}])
        check("gesto con dt enorme rifiutato senza eccezioni", not result[0] and "dt non valido" in result[1], repr(result))
    except Exception as exc:
        check("gesto con dt enorme rifiutato senza eccezioni", False, repr(exc))

    print("8) Avviso 'solo la prima volta' con la sessione caduta")
    before = len(LOGS)
    ctrl.robot.close()
    ctrl.robot.warn_once("prova_api", "[PROVA] API di prova non disponibile")
    lines = [l for l in LOGS[before:] if "[PROVA]" in str(l)]
    check("con la sessione chiusa il messaggio dice che la sessione non e' attiva",
          len(lines) == 1 and "sessione con il robot non attiva" in lines[0], repr(lines))
    ctrl.connect()
    ctrl.robot.warn_once("prova_api", "[PROVA] API di prova non disponibile")
    ctrl.robot.warn_once("prova_api", "[PROVA] API di prova non disponibile")
    lines = [l for l in LOGS[before:] if l == "[PROVA] API di prova non disponibile"]
    check("con la sessione attiva l'avviso compare (una volta sola)", len(lines) == 1, repr(lines))

    print("9) Esito rifiutato dalla WebApp (comando sconosciuto dopo un riavvio)")

    class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.getheader("content-length") or 0))
            body = json.dumps({"ok": False, "id": "c1", "error": "Comando sconosciuto"})
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = BaseHTTPServer.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.handle_request).start()
    ctrl.config["webapp"]["result_url"] = "http://127.0.0.1:%d/api/pepper/result" % server.server_address[1]
    ctrl.webapp.report_result({"id": "c1"}, True, "detto")
    n = count("La WebApp non ha registrato l'esito del comando c1: Comando sconosciuto")
    check("esito rifiutato scritto nel log", n == 1, "righe: %d" % n)
    server.server_close()

    print("10) Servizio di un movimento autonomo che fallisce a ogni gesto")
    ctrl.robot.autonomous_life._service.setAutonomousAbilityEnabled = broken
    ctrl.robot.background_movement._service.setEnabled = broken
    for _ in range(4):
        ctrl.autonomy.set_ability_enabled("BackgroundMovement", "background_movement", False)
    n = count("[AUTONOMY] BackgroundMovement non modificabile")
    check("errore ripetuto scritto una sola volta", n == 1, "righe: %d" % n)

    ctrl.running = False
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITI %d controlli: %s" % (len(FAILURES), ", ".join(FAILURES))))
    sys.stdout.flush()
    os._exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
