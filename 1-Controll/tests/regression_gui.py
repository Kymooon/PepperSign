# -*- coding: utf-8 -*-
"""
Test della GUI Tkinter con il robot simulato: crea la finestra vera, preme i
pulsanti principali e registra log e frame. Uso: python2.7 gui_harness.py <Controll> <out.json>
"""
from __future__ import print_function

import json
import os
import re
import shutil
import sys
import tempfile
import time

ROOT = os.path.abspath(sys.argv[1])
OUT = sys.argv[2]
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402
fake_qi.MAX_SIMULATED_SECONDS = 0.02

from peppersign import compat  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign import gui as gui_module  # noqa: E402

tmp = tempfile.mkdtemp(prefix="ps_gui_")
SAVE_PATHS = [os.path.join(tmp, "seq.json")]
compat.tkFileDialog.asksaveasfilename = lambda **kw: SAVE_PATHS.pop(0)
compat.tkFileDialog.askopenfilename = lambda **kw: os.path.join(tmp, "seq.json")
gui_module.tkFileDialog = compat.tkFileDialog
gui_module.tkMessageBox.askyesno = lambda *a, **kw: True

config = build_runtime_config(None)
config["paths"]["gesture_dir"] = tmp
config["paths"]["save_dir"] = tmp
config["robot_defaults"]["gesture_pre_delay"] = 0.0
config["robot_defaults"]["gesture_post_delay"] = 0.0

store = GestureStore(tmp, log_cb=None)
store.reload()
ctrl = PepperController(config, gesture_store=store, log_cb=None)
gui = gui_module.PepperGUI(ctrl, config, store)
ctrl.log_cb = gui.enqueue_log
store.log_cb = gui.enqueue_log
ctrl.connect()


def pump(seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        gui.root.update()
        time.sleep(0.02)
    gui._tick()
    gui.root.update()


def press(name, *args):
    gui.enqueue_log("=== %s" % name)
    getattr(gui, name)(*args)
    pump()


gui.var_capture_name.set("Buon giorno")
for name in ("on_prepare_recording", "on_free_arms", "on_hold_arms", "on_free_left_arm", "on_hold_left_arm",
             "on_free_right_arm", "on_hold_right_arm", "on_move_only_left_arm", "on_move_only_right_arm",
             "on_free_head", "on_hold_head", "on_open_left_hand", "on_close_left_hand", "on_open_right_hand",
             "on_close_right_hand", "on_open_both_hands", "on_close_both_hands",
             "on_dump_pose", "on_dump_pose", "on_new_composite_frame"):
    press(name)
gui._select_frame_index(0)
press("on_update_left_in_selected_frame")
press("on_update_head_in_selected_frame")
press("on_validate_selected_frame")
press("on_mirror_left_to_right")
gui.var_edit_angle.set("0.2")
press("on_apply_selected_angle")
press("on_nudge_selected_angle_plus")
gui.var_edit_dt.set("0.9")
press("on_apply_selected_dt")
gui.var_frame_no_collision.set(1)
press("on_toggle_frame_no_collision")
press("on_copy_selected_frame")
press("on_move_frame_down")
press("on_test_frames")
press("on_go_to_frame")
press("on_soft_on")
press("on_soft_off")
press("on_save_sequence")
press("on_reload_gestures")
press("on_load_sequence")
gui.var_say_text.set("ciao")
press("on_say")
press("on_say_animated")
gui.var_gesture.set("buon_giorno")
press("on_gesture")
for name in ("on_wakeup", "on_rest", "on_life_off", "on_life_on", "on_volume_up", "on_volume_down",
             "on_refresh_protections", "on_restore_protections", "on_reset_safety_counts",
             "on_toggle_demo_obstacle", "on_toggle_demo_obstacle"):
    press(name)
press("on_set_protection", "self_Arms", False)
press("on_set_protection", "self_Arms", True)
press("on_open_pose_dialog")
gui.var_target_mode.set("demo")
gui.var_target_ip.set("127.0.0.1")
gui.var_target_port.set("9559")
press("on_apply_target")
press("on_remove_frame")
press("on_clear_frames")
pump(0.5)

status = dict((name, getattr(gui, name).get()) for name in sorted(vars(gui))
              if name.startswith("var_") and hasattr(getattr(gui, name), "get")
              and name not in ("var_capture_name",))
log_text = gui.txt_log.get("1.0", "end")
num = re.compile(r"\d+(\.\d+)?")
lines = [num.sub("#", line.replace(tmp, "<tmp>")) for line in log_text.splitlines()]
saved = {}
for name in ("seq.json",):
    path = os.path.join(tmp, name)
    if os.path.exists(path):
        data = json.load(open(path))
        data.pop("created_at", None)
        saved[name] = data
out = {"log": lines, "status": status, "frames": len(gui.frames), "saved": saved,
       "title": gui.root.title()}
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
print("OK GUI: %d righe di log" % len(lines))
ctrl.running = False
gui.root.destroy()
shutil.rmtree(tmp, ignore_errors=True)
os._exit(0)
