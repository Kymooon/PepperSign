# -*- coding: utf-8 -*-
"""
Test della sequenza modificata solo dal thread della finestra (problema 5 della revisione).

Uso (dalla cartella 1-Controll, serve un display anche Xvfb):  python2.7 tests/test_gui_threads.py .

La lettura della posa dal robot e' resa lenta (0.6 s); mentre e' in corso si
cambia la sequenza (frame rimosso, spostato, file caricato). Il risultato della
lettura deve finire sul frame giusto o essere scartato, mai su un altro frame,
e la lista dei frame deve essere modificata solo dal thread della finestra.
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import compat, fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign import gui as gui_module  # noqa: E402

fake_qi.MAX_SIMULATED_SECONDS = 0.02
FAILURES = []
MAIN = threading.current_thread()


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


class TrackedList(list):
    """Lista che registra da quale thread viene modificata."""
    foreign = []

    def _mark(self, what):
        if threading.current_thread() is not MAIN:
            TrackedList.foreign.append("%s da %s" % (what, threading.current_thread().name))

    def append(self, item):
        self._mark("append")
        list.append(self, item)

    def insert(self, index, item):
        self._mark("insert")
        list.insert(self, index, item)

    def pop(self, *args):
        self._mark("pop")
        return list.pop(self, *args)

    def __setitem__(self, index, value):
        self._mark("setitem")
        list.__setitem__(self, index, value)


def main():
    tmp = tempfile.mkdtemp(prefix="ps_thr_")
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    store = GestureStore(tmp, log_cb=None)
    ctrl = PepperController(config, gesture_store=store, log_cb=None)
    gui = gui_module.PepperGUI(ctrl, config, store)
    logs = []
    gui.enqueue_log = logs.append
    ctrl.connect()

    real_get_pose = ctrl.get_pose

    def slow_get_pose(joints):
        time.sleep(0.6)
        return real_get_pose(joints)
    ctrl.get_pose = slow_get_pose

    def pump(seconds=1.2):
        end = time.time() + seconds
        while time.time() < end:
            gui.root.update()
            gui._tick()
            time.sleep(0.03)

    joints = list(gui.capture_joints)
    pose = list(real_get_pose(joints)[1])
    left = joints.index("LShoulderPitch")

    def make_frames():
        first = {"angles": list(pose), "dt": 0.6, "nome": "primo"}
        second = {"angles": list(pose), "dt": 0.6, "nome": "secondo"}
        first["angles"][left] = 0.5
        second["angles"][left] = 0.9
        gui.frames = [first, second]
        gui._refresh_frames_listbox()
        return first, second

    print("1) Frame rimosso mentre si legge il braccio SX")
    first, second = make_frames()
    gui._select_frame_index(0)
    gui.on_update_left_in_selected_frame()
    gui.on_remove_frame()                     # tolgo proprio il frame da aggiornare
    pump()
    check("l'altro frame NON e' stato modificato", second["angles"][left] == 0.9 and not second.get("composite"),
          "LShoulderPitch=%r composite=%r" % (second["angles"][left], second.get("composite")))
    check("motivo nel log", any("non e' piu' nella sequenza" in m for m in logs), repr(logs[-3:]))

    print("2) Frame spostato mentre si legge il braccio SX")
    first, second = make_frames()
    gui._select_frame_index(0)
    gui.on_update_left_in_selected_frame()
    gui.on_move_frame_down()                  # il frame da aggiornare passa in posizione 2
    pump()
    check("aggiornato il frame giusto (ora in posizione 2)",
          first.get("composite") is True and gui.frames[1] is first, repr([f.get("nome") for f in gui.frames]))
    check("l'altro frame NON e' stato modificato", second["angles"][left] == 0.9 and not second.get("composite"))
    check("log con la posizione attuale", any("Frame 2 aggiornato: braccio SX" in m for m in logs), repr(logs[-3:]))

    print("3) File caricato mentre si cattura una posa (Dump Pose)")
    make_frames()
    small = joints[:4]
    path = os.path.join(tmp, "piccola.json")
    with open(path, "w") as handle:
        json.dump({"name": "piccola", "format": "frames_v1", "joints": small,
                   "frames": [{"angles": pose[:4], "dt": 0.6}]}, handle)
    compat.tkFileDialog.askopenfilename = lambda **kw: path
    gui.on_dump_pose()
    gui.on_load_sequence()
    pump()
    problems = [i + 1 for i, f in enumerate(gui.frames) if len(f.get("angles", [])) != len(gui.capture_joints)]
    check("nessun frame con un numero di angoli diverso dai giunti", not problems and len(gui.frames) == 1,
          "giunti=%d frame=%r" % (len(gui.capture_joints), [len(f["angles"]) for f in gui.frames]))

    print("4) La lista dei frame si modifica solo nel thread della finestra")
    gui.capture_joints = joints
    gui.frames = TrackedList()
    gui._refresh_frames_listbox()
    gui.on_dump_pose()
    gui.on_new_composite_frame()
    pump(2.0)
    gui._select_frame_index(0)
    gui.on_update_head_in_selected_frame()
    pump()
    check("frame catturati", len(gui.frames) == 2, repr(len(gui.frames)))
    check("nessuna modifica da un thread secondario", not TrackedList.foreign, repr(TrackedList.foreign))

    ctrl.running = False
    gui.root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITO (%d)" % len(FAILURES)))
    sys.stdout.flush()
    os._exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
