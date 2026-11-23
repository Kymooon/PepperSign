# -*- coding: utf-8 -*-
"""
Test del rifiuto dei frame e dei gesti non coerenti (problema 2 della revisione).

Uso (dalla cartella 1-Controll):  python2.7 tests/test_frames.py .
La parte sulla GUI viene eseguita solo se c'e' un display (anche Xvfb).

Un frame con angoli mancanti o in piu', valori non numerici o dt non validi, e un
gesto nel vecchio formato ready_v1 (non piu' supportato) devono essere RIFIUTATI: nessun valore
completato con zeri o tagliato e, soprattutto, nessun movimento del robot.
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign.robot.interpolation import (  # noqa: E402
    InvalidGesture, build_interpolation_from_frames, check_frames, check_gesture)

fake_qi.MAX_SIMULATED_SECONDS = 0.02
FAILURES = []
LOGS = []
J = ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand"]
POSE = [1.5, 0.15, -1.2, -0.5, 0.0, 0.6]


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


def frame(angles, **extra):
    out = {"angles": angles, "dt": 0.6}
    out.update(extra)
    return out


def motions():
    return len([l for l in LOGS if "ALMotion.angleInterpolation" in str(l) or "ALMotion.setAngles" in str(l)])


def pure_checks():
    print("1) Controllo dei frame (frames_v1)")
    check("sequenza valida", check_frames(J, [frame(POSE), frame(POSE, dt=1.2)]) == [])
    cases = [
        ("angolo mancante", [frame(POSE[:-1])], "5 angoli invece di 6"),
        ("angolo in piu'", [frame(POSE + [0.1])], "7 angoli invece di 6"),
        ("NaN", [frame([float("nan")] + POSE[1:])], "LShoulderPitch"),
        ("infinito", [frame([float("inf")] + POSE[1:])], "LShoulderPitch"),
        ("testo", [frame(["1.5"] + POSE[1:])], "LShoulderPitch"),
        ("vero/falso", [frame([True] + POSE[1:])], "LShoulderPitch"),
        ("None", [frame([None] + POSE[1:])], "LShoulderPitch"),
        ("intero enorme", [frame([10 ** 400] + POSE[1:])], "LShoulderPitch"),
        ("dt testo", [frame(POSE, dt="x")], "dt non valido"),
        ("dt zero", [frame(POSE, dt=0)], "dt deve essere maggiore di 0"),
        ("dt negativo", [frame(POSE, dt=-1.0)], "dt deve essere maggiore di 0"),
        ("frame non oggetto", [POSE], "non e' un oggetto"),
        ("frame senza angoli", [{"dt": 0.5}], "angoli mancanti"),
        ("nessun frame", [], "nessun frame"),
    ]
    for label, frames, fragment in cases:
        problems = check_frames(J, frames)
        check("rifiutato: %s" % label, problems and fragment in " ".join(problems), repr(problems))
    check("frame 2 indicato nel messaggio", "frame 2:" in " ".join(check_frames(J, [frame(POSE), frame(POSE[:3])])))
    check("rifiutato: giunti vuoti", check_frames([], [frame(POSE)]) != [])
    check("rifiutato: giunto ripetuto", "ripetuto" in " ".join(check_frames(J[:5] + ["LShoulderPitch"], [frame(POSE)])))
    check("dt assente = valido (default 0.6)", check_frames(J, [{"angles": POSE}]) == [])

    print("2) Nessun completamento con zeri")
    try:
        build_interpolation_from_frames(J, [frame(POSE[:2])], lambda joints, angles: angles)
        check("build_interpolation rifiuta il frame corto", False, "nessuna eccezione")
    except InvalidGesture as exc:
        check("build_interpolation rifiuta il frame corto", "2 angoli invece di 6" in str(exc), str(exc))

    print("3) Formato del gesto (solo frames_v1)")
    T = [[0.5, 1.0]] * len(J)
    A = [[0.1, 0.2]] * len(J)
    for label, payload in [
        ("ready_v1 con tracce valide", {"format": "ready_v1", "joints": J, "times": T, "angles": A}),
        ("tracce senza campo format", {"joints": J, "times": T, "angles": A}),
    ]:
        problems = check_gesture(payload)
        check("rifiutato: %s" % label, problems and "ready_v1 non piu' supportato" in problems[0], repr(problems))
    check("gesto senza frames rifiutato", check_gesture({"format": "frames_v1", "joints": J}) == ["mancano i frame (formato frames_v1)"])
    check("contenuto non JSON oggetto rifiutato", check_gesture([1, 2]) != [])
    check("gesto frames_v1 valido", check_gesture({"joints": J, "frames": [frame(POSE)]}) == [])


def controller_checks():
    print("4) Esecuzione: un gesto non valido non muove il robot")
    tmp = tempfile.mkdtemp(prefix="ps_frames_")
    gestures = {
        "corto.json": {"name": "corto", "format": "frames_v1", "joints": J, "frames": [frame(POSE), frame(POSE[:4])]},
        "tracce.json": {"name": "tracce", "format": "ready_v1", "joints": J,
                        "times": [[0.5, 1.0]] * len(J), "angles": [[0.1, 0.2]] * len(J)},
        "buono.json": {"name": "buono", "format": "frames_v1", "joints": J, "frames": [frame(POSE)]},
    }
    for name, payload in gestures.items():
        with open(os.path.join(tmp, name), "w") as handle:
            json.dump(payload, handle)
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    config["robot_defaults"]["gesture_pre_delay"] = 0.0
    config["robot_defaults"]["gesture_post_delay"] = 0.0
    store = GestureStore(tmp, log_cb=LOGS.append)
    store.reload()
    check("caricamento: corto.json segnalato", any("corto.json non valido" in str(l) for l in LOGS))
    check("caricamento: tracce.json segnalato", any("tracce.json non valido" in str(l) for l in LOGS))
    check("caricamento: buono.json non segnalato", not any("buono.json non valido" in str(l) for l in LOGS))
    ctrl = PepperController(config, gesture_store=store, log_cb=LOGS.append)
    ctrl.connect()

    for label, call in [
        ("frame corto da GUI/Test", lambda: ctrl.run_frames_gesture(J, [frame(POSE), frame(POSE[:4])])),
        ("frame con angolo in piu'", lambda: ctrl.run_frames_gesture(J, [frame(POSE + [0.3])])),
        ("frame con NaN", lambda: ctrl.run_frames_gesture(J, [frame([float("nan")] + POSE[1:])])),
        ("gesto salvato non valido (WebApp)", lambda: ctrl.play_gesture("corto")),
        ("gesto ready_v1 (formato rimosso, WebApp)", lambda: ctrl.play_gesture("tracce")),
        ("Vai alla posa con NaN", lambda: ctrl.go_to_pose(J, [float("nan")] + POSE[1:])),
    ]:
        before = motions()
        ok, message = call()
        check("%s: rifiutato" % label, not ok and "non valid" in message, message)
        check("%s: nessun movimento" % label, motions() == before, "%d movimenti" % (motions() - before))
    before = motions()
    ok, message = ctrl.play_gesture("buono")
    check("gesto valido eseguito", ok and motions() > before, message)
    result = ctrl.handle_command({"action": "PLAY_GESTURE", "gestureId": "corto", "id": "c1"})
    check("esito per il tablet con il motivo", result and not result[0] and "4 angoli invece di 6" in result[1], repr(result))
    return ctrl


def gui_checks(ctrl):
    if not os.environ.get("DISPLAY"):
        print("5) GUI: saltata (nessun display)")
        return
    print("5) GUI: Carica sequenza, modifiche, Salva ed Export")
    from peppersign import compat, gui as gui_module
    tmp = tempfile.mkdtemp(prefix="ps_frames_gui_")
    bad = os.path.join(tmp, "rotto.json")
    nohands = os.path.join(tmp, "senza_mani.json")
    J4 = J[:4]
    with open(bad, "w") as handle:
        json.dump({"name": "rotto", "format": "frames_v1", "joints": J, "frames": [frame(POSE), frame(POSE[:3])]}, handle)
    with open(nohands, "w") as handle:
        json.dump({"name": "senza mani", "format": "frames_v1", "joints": J4, "frames": [frame(POSE[:4])]}, handle)
    paths = []
    compat.tkFileDialog.askopenfilename = lambda **kw: paths.pop(0)
    compat.tkFileDialog.asksaveasfilename = lambda **kw: os.path.join(tmp, "uscita.json")
    gui_module.tkFileDialog = compat.tkFileDialog
    gui = gui_module.PepperGUI(ctrl, ctrl.config, ctrl.gesture_store)
    gui_logs = []
    gui.enqueue_log = gui_logs.append

    gui.frames = [frame(list(gui.ctrl.get_pose(gui.capture_joints)[1]))]
    original = json.dumps(gui.frames)
    paths.append(bad)
    gui.on_load_sequence()
    check("file rotto NON caricato", json.dumps(gui.frames) == original)
    check("motivo nel log", any("frame 2: 3 angoli invece di 6" in l for l in gui_logs), repr(gui_logs[-3:]))

    paths.append(nohands)
    gui.on_load_sequence()
    check("file senza mani caricato con i suoi giunti (mani non aggiunte)",
          gui.capture_joints == J4 and len(gui.frames) == 1, repr(gui.capture_joints))

    # frame incoerente in memoria (non dovrebbe capitare piu', ma resta protetto)
    gui.frames = [frame(POSE[:2])]
    gui._select_frame_index(0)
    gui.var_edit_joint.set(gui.capture_joints[0])
    gui.var_edit_angle.set("0.2")
    gui.on_apply_selected_angle()
    check("modifica di un angolo: nessun completamento con zeri", gui.frames[0]["angles"] == POSE[:2],
          repr(gui.frames[0]["angles"]))
    del gui_logs[:]
    check("pulsante Esporta gesto pronto rimosso", not hasattr(gui, "on_export_ready_gesture"))
    gui.on_save_sequence()
    check("Salva rifiutato", any("NON salvata" in l for l in gui_logs) and not os.path.exists(os.path.join(tmp, "uscita.json")))
    gui.root.destroy()


def main():
    pure_checks()
    ctrl = controller_checks()
    gui_checks(ctrl)
    ctrl.running = False
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITI %d controlli: %s" % (len(FAILURES), ", ".join(FAILURES))))
    sys.stdout.flush()
    os._exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
