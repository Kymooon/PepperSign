# -*- coding: utf-8 -*-
from __future__ import absolute_import

import copy
import os
import threading

from peppersign.compat import queue, tk, tkFileDialog, ttk
from peppersign.gesture_store import DEFAULT_JOINTS
from peppersign.utils import ensure_dir, now_stamp, read_json, safe_unicode

import os
os.environ['TCL_LIBRARY'] = r'C:\Python27\tcl\tcl8.5'
os.environ['TK_LIBRARY'] = r'C:\Python27\tcl\tk8.5'

import Tkinter as tk


# Coppie usate per duplicare/specchiare la posa di un braccio sull'altro.
# Per la simmetria fisica di Pepper alcuni giunti devono cambiare segno.
LEFT_TO_RIGHT_ARM_MIRROR = [
    ("LShoulderPitch", "RShoulderPitch", 1.0),
    ("LShoulderRoll", "RShoulderRoll", -1.0),
    ("LElbowYaw", "RElbowYaw", -1.0),
    ("LElbowRoll", "RElbowRoll", -1.0),
    ("LWristYaw", "RWristYaw", -1.0),
    ("LHand", "RHand", 1.0),
]

RIGHT_TO_LEFT_ARM_MIRROR = [
    ("RShoulderPitch", "LShoulderPitch", 1.0),
    ("RShoulderRoll", "LShoulderRoll", -1.0),
    ("RElbowYaw", "LElbowYaw", -1.0),
    ("RElbowRoll", "LElbowRoll", -1.0),
    ("RWristYaw", "LWristYaw", -1.0),
    ("RHand", "LHand", 1.0),
]

# Gruppi usati per costruire un frame composito.
# Un frame composito permette di salvare nello stesso frame la posa del braccio
# sinistro, del braccio destro e della testa anche se vengono posizionati e
# acquisiti in momenti diversi.
LEFT_ARM_COMPONENT_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
]

RIGHT_ARM_COMPONENT_JOINTS = [
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

HEAD_COMPONENT_JOINTS = ["HeadYaw", "HeadPitch"]


class PepperGUI(object):
    def __init__(self, controller, config, gesture_store):
        self.ctrl = controller
        self.config = config
        self.gesture_store = gesture_store

        self.root = tk.Tk()
        self.root.title(config["ui"]["window_title"])
        self.root.geometry(config["ui"]["window_size"])

        self.log_queue = queue.Queue()

        self.var_robot = tk.StringVar()
        self.var_webapp = tk.StringVar()
        self.var_life = tk.StringVar()
        self.var_last = tk.StringVar()
        self.var_error = tk.StringVar()
        self.var_volume = tk.StringVar()
        self.var_volume.set("N/A")

        self.var_say_text = tk.StringVar()
        self.var_gesture = tk.StringVar()

        self.var_frame_dt = tk.StringVar()
        self.var_frame_dt.set("0.6")
        self.var_capture_name = tk.StringVar()
        self.var_capture_name.set("GESTO_" + now_stamp())
        self.capture_joints = list(DEFAULT_JOINTS)
        self._ensure_hand_capture_joints()
        self.frames = []

        # Variabili editor manuale frame: permettono di ritoccare dt e singoli
        # angoli dopo la cattura, senza modificare il JSON a mano.
        self.var_edit_dt = tk.StringVar()
        self.var_edit_joint = tk.StringVar()
        self.var_edit_angle = tk.StringVar()
        self.var_edit_step = tk.StringVar()
        self.var_edit_step.set("0.03")
        if self.capture_joints:
            self.var_edit_joint.set(self.capture_joints[0])

        self._refresh_gesture_default()
        self._build()
        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _ensure_hand_capture_joints(self):
        if "LHand" not in self.capture_joints:
            self.capture_joints.append("LHand")
        if "RHand" not in self.capture_joints:
            self.capture_joints.append("RHand")

    def _refresh_gesture_default(self):
        keys = self.gesture_store.keys()
        if keys:
            self.var_gesture.set(keys[0])
        else:
            self.var_gesture.set("")

    def enqueue_log(self, message):
        try:
            self.log_queue.put_nowait(message)
        except Exception:
            pass

    def _append_log(self, message):
        try:
            if isinstance(message, unicode):
                message = message.encode("utf-8")
        except Exception:
            pass
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", str(message) + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _run_async(self, fn, *args):
        def runner():
            try:
                fn(*args)
            except Exception as exc:
                self.enqueue_log("[GUI] Errore: %s" % str(exc))
        thread = threading.Thread(target=runner)
        thread.daemon = True
        thread.start()

    def _build(self):
        frm_status = tk.Frame(self.root)
        frm_status.pack(fill="x", padx=10, pady=8)

        tk.Label(frm_status, text="Robot:").grid(row=0, column=0, sticky="w")
        tk.Label(frm_status, textvariable=self.var_robot).grid(row=0, column=1, sticky="w", padx=6)

        tk.Label(frm_status, text="WebApp:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        tk.Label(frm_status, textvariable=self.var_webapp).grid(row=0, column=3, sticky="w", padx=6)

        tk.Label(frm_status, text="Autonomous Life:").grid(row=1, column=0, sticky="w")
        tk.Label(frm_status, textvariable=self.var_life).grid(row=1, column=1, sticky="w", padx=6)

        tk.Label(frm_status, text="Last cmd:").grid(row=1, column=2, sticky="w", padx=(20, 0))
        tk.Label(frm_status, textvariable=self.var_last).grid(row=1, column=3, sticky="w", padx=6)

        tk.Label(frm_status, text="Volume:").grid(row=2, column=0, sticky="w")
        tk.Label(frm_status, textvariable=self.var_volume).grid(row=2, column=1, sticky="w", padx=6)

        tk.Label(frm_status, text="Last error:").grid(row=3, column=0, sticky="w")
        tk.Label(frm_status, textvariable=self.var_error, fg="red").grid(row=3, column=1, columnspan=3, sticky="w", padx=6)

        frm_main = tk.Frame(self.root)
        frm_main.pack(fill="both", expand=True, padx=10, pady=5)

        frm_left = tk.Frame(frm_main)
        frm_left.pack(side="left", fill="y", expand=False)

        frm_mid = tk.Frame(frm_main)
        frm_mid.pack(side="left", fill="both", expand=True, padx=(10, 0))

        frm_right = tk.Frame(frm_main)
        frm_right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        box_tts = tk.LabelFrame(frm_left, text="1) TTS")
        box_tts.pack(fill="x", pady=6)

        tk.Entry(box_tts, textvariable=self.var_say_text, width=30).pack(side="left", padx=8, pady=8)
        tk.Button(box_tts, text="Dì", width=6, command=self.on_say).pack(side="left", padx=6)
        tk.Button(box_tts, text="Dì animato", width=10, command=self.on_say_animated).pack(side="left", padx=6)

        box_util = tk.LabelFrame(frm_left, text="2) Utility")
        box_util.pack(fill="x", pady=6)

        tk.Button(box_util, text="WakeUp", width=10, command=self.on_wakeup).pack(side="left", padx=8, pady=8)
        tk.Button(box_util, text="Rest", width=10, command=self.on_rest).pack(side="left", padx=6, pady=8)
        tk.Button(box_util, text="Life ON", width=10, command=self.on_life_on).pack(side="left", padx=6, pady=8)
        tk.Button(box_util, text="Life OFF", width=10, command=self.on_life_off).pack(side="left", padx=6, pady=8)

        box_volume = tk.LabelFrame(frm_left, text="3) Volume")
        box_volume.pack(fill="x", pady=6)

        tk.Label(box_volume, text="Uscita:").pack(side="left", padx=(8, 4), pady=8)
        tk.Label(box_volume, textvariable=self.var_volume, width=6).pack(side="left", padx=(0, 8), pady=8)
        tk.Button(box_volume, text="Vol -", width=8, command=self.on_volume_down).pack(side="left", padx=6, pady=8)
        tk.Button(box_volume, text="Vol +", width=8, command=self.on_volume_up).pack(side="left", padx=6, pady=8)

        box_map = tk.LabelFrame(frm_left, text="4) PLAY_GESTURE")
        box_map.pack(fill="x", pady=6)

        keys = self.gesture_store.keys() or [""]
        if ttk:
            self.combo_gesture = ttk.Combobox(box_map, textvariable=self.var_gesture, values=keys, width=30, state="readonly")
            self.combo_gesture.pack(side="left", padx=8, pady=8)
        else:
            self.combo_gesture = None
            opt = tk.OptionMenu(box_map, self.var_gesture, *keys)
            opt.config(width=26)
            opt.pack(side="left", padx=8, pady=8)

        tk.Button(box_map, text="Avvia", width=8, command=self.on_gesture).pack(side="left", padx=6)
        tk.Button(box_map, text="Ricarica", width=8, command=self.on_reload_gestures).pack(side="left", padx=6)

        box_cap = tk.LabelFrame(frm_mid, text="5) Cattura keyframe dal robot (Dump Pose)")
        box_cap.pack(fill="both", expand=True)

        row1 = tk.Frame(box_cap)
        row1.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(row1, text="Nome gesto:").pack(side="left")
        tk.Entry(row1, textvariable=self.var_capture_name, width=28).pack(side="left", padx=6)

        tk.Label(row1, text="dt frame (s):").pack(side="left", padx=(10, 0))
        tk.Entry(row1, textvariable=self.var_frame_dt, width=6).pack(side="left", padx=6)
        tk.Button(row1, text="Applica dt a tutti", command=self.on_apply_dt_all).pack(side="left", padx=6)

        row2 = tk.Frame(box_cap)
        row2.pack(fill="x", padx=8, pady=(0, 6))

        tk.Button(row2, text="Prepara reg.", width=12, command=self.on_prepare_recording).pack(side="left", padx=3)
        tk.Button(row2, text="Free Arms", width=10, command=self.on_free_arms).pack(side="left", padx=3)
        tk.Button(row2, text="Hold Arms", width=10, command=self.on_hold_arms).pack(side="left", padx=3)
        tk.Button(row2, text="Free Head", width=10, command=self.on_free_head).pack(side="left", padx=12)
        tk.Button(row2, text="Hold Head", width=10, command=self.on_hold_head).pack(side="left", padx=3)
        tk.Button(row2, text="Dump Pose (frame)", width=16, command=self.on_dump_pose).pack(side="left", padx=12)

        row2c = tk.Frame(box_cap)
        row2c.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(row2c, text="Braccio singolo:").pack(side="left", padx=(0, 8))
        tk.Button(row2c, text="Free SX", width=9, command=self.on_free_left_arm).pack(side="left", padx=3)
        tk.Button(row2c, text="Hold SX", width=9, command=self.on_hold_left_arm).pack(side="left", padx=3)
        tk.Button(row2c, text="Free DX", width=9, command=self.on_free_right_arm).pack(side="left", padx=(12, 3))
        tk.Button(row2c, text="Hold DX", width=9, command=self.on_hold_right_arm).pack(side="left", padx=3)
        tk.Button(row2c, text="Solo SX", width=9, command=self.on_move_only_left_arm).pack(side="left", padx=(12, 3))
        tk.Button(row2c, text="Solo DX", width=9, command=self.on_move_only_right_arm).pack(side="left", padx=3)

        row2b = tk.Frame(box_cap)
        row2b.pack(fill="x", padx=8, pady=(0, 6))

        tk.Label(row2b, text="Mani:").pack(side="left", padx=(0, 8))
        tk.Button(row2b, text="Apri SX", width=10, command=self.on_open_left_hand).pack(side="left", padx=3)
        tk.Button(row2b, text="Chiudi SX", width=10, command=self.on_close_left_hand).pack(side="left", padx=3)
        tk.Button(row2b, text="Apri DX", width=10, command=self.on_open_right_hand).pack(side="left", padx=(12, 3))
        tk.Button(row2b, text="Chiudi DX", width=10, command=self.on_close_right_hand).pack(side="left", padx=3)
        tk.Button(row2b, text="Apri entrambe", width=12, command=self.on_open_both_hands).pack(side="left", padx=(12, 3))
        tk.Button(row2b, text="Chiudi entrambe", width=13, command=self.on_close_both_hands).pack(side="left", padx=3)

        row3 = tk.Frame(box_cap)
        row3.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_list = tk.Frame(row3)
        left_list.pack(side="left", fill="both", expand=True)

        tk.Label(left_list, text="Frames catturati (ordine):").pack(anchor="w")
        self.list_frames = tk.Listbox(left_list, height=14)
        self.list_frames.pack(fill="both", expand=True)
        self.list_frames.bind("<<ListboxSelect>>", self.on_frame_select)

        right_btn = tk.Frame(row3)
        right_btn.pack(side="left", fill="y", padx=(10, 0))

        tk.Button(right_btn, text="Rimuovi selezionato", width=18, command=self.on_remove_frame).pack(pady=3)
        tk.Button(right_btn, text="Copia frame", width=18, command=self.on_copy_selected_frame).pack(pady=3)
        tk.Button(right_btn, text="Clear", width=18, command=self.on_clear_frames).pack(pady=3)

        # Pulsanti principali tenuti in alto per evitare che finiscano fuori dalla finestra.
        box_file = tk.LabelFrame(right_btn, text="File / test gesture")
        box_file.pack(fill="x", pady=(8, 3))
        tk.Button(box_file, text="Test gesture", width=18, command=self.on_test_frames).pack(padx=4, pady=(4, 2))
        tk.Button(box_file, text="Salva sequenza JSON", width=18, command=self.on_save_sequence).pack(padx=4, pady=2)
        tk.Button(box_file, text="Carica sequenza JSON", width=18, command=self.on_load_sequence).pack(padx=4, pady=2)
        tk.Button(box_file, text="Esporta gesture pronta", width=18, command=self.on_export_ready_gesture).pack(padx=4, pady=(2, 4))

        box_edit = tk.LabelFrame(right_btn, text="Tuning frame")
        box_edit.pack(fill="x", pady=(10, 3))

        tk.Label(box_edit, text="dt selez.:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        tk.Entry(box_edit, textvariable=self.var_edit_dt, width=7).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        tk.Button(box_edit, text="Applica", width=8, command=self.on_apply_selected_dt).grid(row=0, column=2, sticky="w", padx=4, pady=2)

        tk.Label(box_edit, text="Joint:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        if ttk:
            self.combo_edit_joint = ttk.Combobox(box_edit, textvariable=self.var_edit_joint, values=self.capture_joints, width=16, state="readonly")
            self.combo_edit_joint.grid(row=1, column=1, columnspan=2, sticky="w", padx=4, pady=2)
            self.combo_edit_joint.bind("<<ComboboxSelected>>", self.on_edit_joint_changed)
        else:
            self.combo_edit_joint = None
            self.opt_edit_joint = tk.OptionMenu(box_edit, self.var_edit_joint, *self.capture_joints)
            self.opt_edit_joint.config(width=14)
            self.opt_edit_joint.grid(row=1, column=1, columnspan=2, sticky="w", padx=4, pady=2)

        tk.Label(box_edit, text="Angolo:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        tk.Entry(box_edit, textvariable=self.var_edit_angle, width=10).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        tk.Button(box_edit, text="Applica", width=8, command=self.on_apply_selected_angle).grid(row=2, column=2, sticky="w", padx=4, pady=2)

        tk.Label(box_edit, text="step:").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        tk.Entry(box_edit, textvariable=self.var_edit_step, width=7).grid(row=3, column=1, sticky="w", padx=4, pady=2)

        row_nudge = tk.Frame(box_edit)
        row_nudge.grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=2)
        tk.Button(row_nudge, text="- step", width=8, command=self.on_nudge_selected_angle_minus).pack(side="left", padx=(0, 4))
        tk.Button(row_nudge, text="+ step", width=8, command=self.on_nudge_selected_angle_plus).pack(side="left", padx=4)

        tk.Button(box_edit, text="Valida frame", width=18, command=self.on_validate_selected_frame).grid(row=5, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 4))

        box_mirror = tk.LabelFrame(right_btn, text="Specchia frame")
        box_mirror.pack(fill="x", pady=(6, 3))
        tk.Button(box_mirror, text="SX -> DX", width=8, command=self.on_mirror_left_to_right).pack(side="left", padx=4, pady=4)
        tk.Button(box_mirror, text="DX -> SX", width=8, command=self.on_mirror_right_to_left).pack(side="left", padx=4, pady=4)

        box_composite = tk.LabelFrame(right_btn, text="Frame composito")
        box_composite.pack(fill="x", pady=(6, 3))
        tk.Button(box_composite, text="Nuovo comp.", width=18, command=self.on_new_composite_frame).pack(padx=4, pady=(4, 2))
        row_comp_1 = tk.Frame(box_composite)
        row_comp_1.pack(fill="x", padx=4, pady=2)
        tk.Button(row_comp_1, text="Agg. SX", width=8, command=self.on_update_left_in_selected_frame).pack(side="left", padx=(0, 4))
        tk.Button(row_comp_1, text="Agg. DX", width=8, command=self.on_update_right_in_selected_frame).pack(side="left", padx=4)
        row_comp_2 = tk.Frame(box_composite)
        row_comp_2.pack(fill="x", padx=4, pady=(2, 4))
        tk.Button(row_comp_2, text="Agg. Testa", width=18, command=self.on_update_head_in_selected_frame).pack(side="left")

        tk.Label(frm_right, text="Log:").pack(anchor="w")
        self.txt_log = tk.Text(frm_right, height=28, wrap="word")
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.insert("end", "Pannello avviato.\n")
        self.txt_log.config(state="disabled")

    def on_reload_gestures(self):
        loaded = self.gesture_store.reload()
        keys = self.gesture_store.keys() or [""]
        if self.combo_gesture is not None:
            self.combo_gesture["values"] = keys
        self._refresh_gesture_default()
        self.enqueue_log("[GESTURES] Ricaricate %d gesture" % loaded)

    def on_say(self):
        text = self.var_say_text.get()
        self._run_async(self.ctrl.say, text)
        self.enqueue_log("[CMD] SAY: %s" % safe_unicode(text))

    def on_say_animated(self):
        text = self.var_say_text.get()

        def run():
            ok, message = self.ctrl.say_animated(text)
            self.enqueue_log("[CMD] SAY_ANIMATED: %s -> %s" % (safe_unicode(text), safe_unicode(message)))
        self._run_async(run)

    def on_gesture(self):
        gesture_id = self.var_gesture.get()

        def run():
            ok, message = self.ctrl.play_gesture(gesture_id)
            self.enqueue_log("[CMD] PLAY_GESTURE %s -> %s" % (safe_unicode(gesture_id), safe_unicode(message)))
        self._run_async(run)

    def on_wakeup(self):
        self._run_async(self.ctrl.wakeup)
        self.enqueue_log("[CMD] WAKEUP")

    def on_rest(self):
        self._run_async(self.ctrl.rest)
        self.enqueue_log("[CMD] REST")

    def on_life_on(self):
        def run():
            ok, message = self.ctrl.set_autonomous_life(True)
            self.enqueue_log("[CMD] LIFE ON -> %s" % safe_unicode(message))
        self._run_async(run)

    def on_life_off(self):
        def run():
            ok, message = self.ctrl.set_autonomous_life(False)
            self.enqueue_log("[CMD] LIFE OFF -> %s" % safe_unicode(message))
        self._run_async(run)

    def on_volume_up(self):
        def run():
            ok, message = self.ctrl.volume_up()
            self.enqueue_log("[VOLUME] %s" % safe_unicode(message))
        self._run_async(run)

    def on_volume_down(self):
        def run():
            ok, message = self.ctrl.volume_down()
            self.enqueue_log("[VOLUME] %s" % safe_unicode(message))
        self._run_async(run)

    def _get_dt_value(self):
        try:
            dt = float(self.var_frame_dt.get().strip())
        except Exception:
            dt = 0.6
        if dt < 0.05:
            dt = 0.05
        if dt > 10.0:
            dt = 10.0
        return dt

    def _refresh_frames_listbox(self):
        self.list_frames.delete(0, "end")
        for index, frame in enumerate(self.frames):
            dt = frame.get("dt", 0.6)
            suffix = "   comp" if frame.get("composite") else ""
            self.list_frames.insert("end", "Frame %02d   dt=%.2fs%s" % (index + 1, float(dt) if dt else 0.0, suffix))

    def _get_selected_frame_index(self):
        try:
            selected = self.list_frames.curselection()
            if not selected:
                return None
            index = int(selected[0])
            if 0 <= index < len(self.frames):
                return index
        except Exception:
            pass
        return None

    def _refresh_joint_selector(self):
        joints = list(self.capture_joints or [])
        if not joints:
            return

        if self.var_edit_joint.get() not in joints:
            self.var_edit_joint.set(joints[0])

        try:
            if self.combo_edit_joint is not None:
                self.combo_edit_joint["values"] = joints
        except Exception:
            pass

        try:
            if hasattr(self, "opt_edit_joint"):
                menu = self.opt_edit_joint["menu"]
                menu.delete(0, "end")
                for joint in joints:
                    menu.add_command(label=joint, command=tk._setit(self.var_edit_joint, joint, self.on_edit_joint_changed))
        except Exception:
            pass

    def _load_selected_frame_to_editor(self):
        index = self._get_selected_frame_index()
        if index is None:
            return

        frame = self.frames[index]
        dt = frame.get("dt", 0.6)
        try:
            self.var_edit_dt.set("%.3f" % float(dt))
        except Exception:
            self.var_edit_dt.set(safe_unicode(dt))

        self._refresh_joint_selector()
        self._update_angle_entry_for_selected_joint()

    def _get_selected_joint_index(self):
        joint = safe_unicode(self.var_edit_joint.get()).strip()
        try:
            return self.capture_joints.index(joint)
        except Exception:
            return None

    def _update_angle_entry_for_selected_joint(self):
        frame_index = self._get_selected_frame_index()
        joint_index = self._get_selected_joint_index()
        if frame_index is None or joint_index is None:
            return

        angles = self.frames[frame_index].get("angles", [])
        if joint_index >= len(angles):
            self.var_edit_angle.set("")
            return

        try:
            self.var_edit_angle.set("%.6f" % float(angles[joint_index]))
        except Exception:
            self.var_edit_angle.set(safe_unicode(angles[joint_index]))

    def on_frame_select(self, event=None):
        self._load_selected_frame_to_editor()

    def on_edit_joint_changed(self, event=None):
        self._update_angle_entry_for_selected_joint()

    def on_apply_selected_dt(self):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[TUNING] Seleziona prima un frame.")
            return

        try:
            dt = float(self.var_edit_dt.get().strip())
        except Exception:
            self.enqueue_log("[TUNING] dt non valido.")
            return

        if dt < 0.05:
            dt = 0.05
        if dt > 10.0:
            dt = 10.0

        self.frames[index]["dt"] = dt
        self.var_frame_dt.set("%.3f" % dt)
        self._refresh_frames_listbox()
        try:
            self.list_frames.selection_set(index)
        except Exception:
            pass
        self._load_selected_frame_to_editor()
        self.enqueue_log("[TUNING] Frame %d: dt impostato a %.3f" % (index + 1, dt))

    def on_apply_selected_angle(self):
        index = self._get_selected_frame_index()
        joint_index = self._get_selected_joint_index()
        if index is None or joint_index is None:
            self.enqueue_log("[TUNING] Seleziona frame e joint.")
            return

        try:
            value = float(self.var_edit_angle.get().strip())
        except Exception:
            self.enqueue_log("[TUNING] angolo non valido.")
            return

        angles = list(self.frames[index].get("angles", []))
        while len(angles) < len(self.capture_joints):
            angles.append(0.0)
        angles[joint_index] = value

        is_valid, warnings, errors = self.ctrl.validate_frame_pose(self.capture_joints, angles)
        if not is_valid:
            self.enqueue_log("[TUNING] VALORE NON APPLICATO: frame non valido")
            for err in errors:
                self.enqueue_log("[TUNING] ERRORE: %s" % safe_unicode(err))
            return

        for warn in warnings:
            self.enqueue_log("[TUNING] WARN: %s" % safe_unicode(warn))

        self.frames[index]["angles"] = angles
        self._update_angle_entry_for_selected_joint()
        self.enqueue_log("[TUNING] Frame %d: %s = %.6f" % (index + 1, safe_unicode(self.capture_joints[joint_index]), value))

    def _get_edit_step(self):
        try:
            step = float(self.var_edit_step.get().strip())
        except Exception:
            step = 0.03
        if step <= 0:
            step = 0.03
        if step > 1.0:
            step = 1.0
        return step

    def _nudge_selected_angle(self, sign):
        try:
            current = float(self.var_edit_angle.get().strip())
        except Exception:
            self._update_angle_entry_for_selected_joint()
            try:
                current = float(self.var_edit_angle.get().strip())
            except Exception:
                self.enqueue_log("[TUNING] nessun angolo valido da modificare.")
                return

        step = self._get_edit_step()
        self.var_edit_angle.set("%.6f" % (current + sign * step))
        self.on_apply_selected_angle()

    def on_nudge_selected_angle_minus(self):
        self._nudge_selected_angle(-1.0)

    def on_nudge_selected_angle_plus(self):
        self._nudge_selected_angle(1.0)

    def _apply_arm_mirror_to_selected_frame(self, mirror_pairs, label):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[SPECCHIO] Seleziona prima un frame.")
            return

        angles = list(self.frames[index].get("angles", []))
        while len(angles) < len(self.capture_joints):
            angles.append(0.0)

        try:
            for source_joint, target_joint, sign in mirror_pairs:
                if source_joint not in self.capture_joints or target_joint not in self.capture_joints:
                    self.enqueue_log("[SPECCHIO] Joint mancante: %s o %s" % (safe_unicode(source_joint), safe_unicode(target_joint)))
                    return
                source_index = self.capture_joints.index(source_joint)
                target_index = self.capture_joints.index(target_joint)
                angles[target_index] = float(angles[source_index]) * float(sign)
        except Exception as exc:
            self.enqueue_log("[SPECCHIO] Errore durante lo specchio: %s" % str(exc))
            return

        is_valid, warnings, errors = self.ctrl.validate_frame_pose(self.capture_joints, angles)
        if not is_valid:
            self.enqueue_log("[SPECCHIO] Frame NON modificato: posa specchiata non valida")
            for err in errors:
                self.enqueue_log("[SPECCHIO] ERRORE: %s" % safe_unicode(err))
            return

        for warn in warnings:
            self.enqueue_log("[SPECCHIO] WARN: %s" % safe_unicode(warn))

        self.frames[index]["angles"] = angles
        self._refresh_frames_listbox()
        try:
            self.list_frames.selection_set(index)
        except Exception:
            pass
        self._load_selected_frame_to_editor()
        self.enqueue_log("[SPECCHIO] Frame %d aggiornato: %s" % (index + 1, label))

    def on_mirror_left_to_right(self):
        self._apply_arm_mirror_to_selected_frame(LEFT_TO_RIGHT_ARM_MIRROR, "SX copiato/specchiato su DX")

    def on_mirror_right_to_left(self):
        self._apply_arm_mirror_to_selected_frame(RIGHT_TO_LEFT_ARM_MIRROR, "DX copiato/specchiato su SX")

    def _select_frame_index(self, index):
        try:
            self.list_frames.selection_clear(0, "end")
            self.list_frames.selection_set(index)
            self.list_frames.activate(index)
            self.list_frames.see(index)
        except Exception:
            pass

    def _ensure_frame_angles_length(self, frame):
        angles = list(frame.get("angles", []))
        while len(angles) < len(self.capture_joints):
            angles.append(0.0)
        if len(angles) > len(self.capture_joints):
            angles = angles[:len(self.capture_joints)]
        frame["angles"] = angles
        return angles

    def _component_joints_available(self, component_joints):
        missing = []
        for joint in component_joints:
            if joint not in self.capture_joints:
                missing.append(joint)
        if missing:
            self.enqueue_log("[COMPOSITO] Joint mancanti nel frame: %s" % ", ".join([safe_unicode(x) for x in missing]))
            return False
        return True

    def on_new_composite_frame(self):
        dt = self._get_dt_value()
        joints = list(self.capture_joints)

        def run():
            ok, angles = self.ctrl.get_pose(joints)
            if not ok:
                self.enqueue_log("[COMPOSITO] Nuovo frame fallito: %s" % safe_unicode(angles))
                return

            is_valid, warnings, errors = self.ctrl.validate_frame_pose(joints, angles)
            if not is_valid:
                self.enqueue_log("[COMPOSITO] FRAME NON CREATO: posa iniziale non valida")
                for err in errors:
                    self.enqueue_log("[COMPOSITO] ERRORE: %s" % safe_unicode(err))
                return

            for warn in warnings:
                self.enqueue_log("[COMPOSITO] WARN: %s" % safe_unicode(warn))

            self.frames.append({"angles": list(angles), "dt": dt, "composite": True})
            new_index = len(self.frames) - 1
            self.enqueue_log("[COMPOSITO] Frame %d creato da posa attuale (dt=%.2f)" % (new_index + 1, dt))
            self.enqueue_log("[UI] aggiorno lista frame")
            self.enqueue_log("[UI] seleziona frame:%d" % new_index)

        self._run_async(run)

    def _update_selected_frame_component(self, component_joints, label):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[COMPOSITO] Seleziona prima un frame.")
            return

        if not self._component_joints_available(component_joints):
            return

        joints_to_read = list(component_joints)

        def run():
            ok, component_angles = self.ctrl.get_pose(joints_to_read)
            if not ok:
                self.enqueue_log("[COMPOSITO] Aggiornamento %s fallito: %s" % (safe_unicode(label), safe_unicode(component_angles)))
                return

            frame = self.frames[index]
            old_angles = self._ensure_frame_angles_length(frame)
            new_angles = list(old_angles)

            try:
                for joint_name, value in zip(joints_to_read, component_angles):
                    target_index = self.capture_joints.index(joint_name)
                    new_angles[target_index] = value
            except Exception as exc:
                self.enqueue_log("[COMPOSITO] Errore mapping %s: %s" % (safe_unicode(label), str(exc)))
                return

            is_valid, warnings, errors = self.ctrl.validate_frame_pose(self.capture_joints, new_angles)
            if not is_valid:
                self.enqueue_log("[COMPOSITO] %s NON applicato: frame risultante non valido" % safe_unicode(label))
                for err in errors:
                    self.enqueue_log("[COMPOSITO] ERRORE: %s" % safe_unicode(err))
                return

            for warn in warnings:
                self.enqueue_log("[COMPOSITO] WARN: %s" % safe_unicode(warn))

            frame["angles"] = new_angles
            frame["composite"] = True
            self.enqueue_log("[COMPOSITO] Frame %d aggiornato: %s" % (index + 1, safe_unicode(label)))
            self.enqueue_log("[UI] aggiorno lista frame")
            self.enqueue_log("[UI] seleziona frame:%d" % index)

        self._run_async(run)

    def on_update_left_in_selected_frame(self):
        self._update_selected_frame_component(LEFT_ARM_COMPONENT_JOINTS, "braccio SX")

    def on_update_right_in_selected_frame(self):
        self._update_selected_frame_component(RIGHT_ARM_COMPONENT_JOINTS, "braccio DX")

    def on_update_head_in_selected_frame(self):
        self._update_selected_frame_component(HEAD_COMPONENT_JOINTS, "testa")

    def on_validate_selected_frame(self):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[VALIDAZIONE] Seleziona prima un frame.")
            return

        angles = self.frames[index].get("angles", [])
        is_valid, warnings, errors = self.ctrl.validate_frame_pose(self.capture_joints, angles)
        if not is_valid:
            self.enqueue_log("[VALIDAZIONE] Frame %d NON valido" % (index + 1))
            for err in errors:
                self.enqueue_log("[VALIDAZIONE] ERRORE: %s" % safe_unicode(err))
            return

        if warnings:
            self.enqueue_log("[VALIDAZIONE] Frame %d valido con warning" % (index + 1))
            for warn in warnings:
                self.enqueue_log("[VALIDAZIONE] WARN: %s" % safe_unicode(warn))
        else:
            self.enqueue_log("[VALIDAZIONE] Frame %d valido" % (index + 1))

    def on_prepare_recording(self):
        def run():
            ok, message = self.ctrl.prepare_gesture_recording()
            if ok:
                self.enqueue_log("[REC] %s" % safe_unicode(message))
            else:
                self.enqueue_log("[REC] FAIL: %s" % safe_unicode(message))
        self._run_async(run)

    def on_free_arms(self):
        def run():
            ok, message = self.ctrl.free_arms()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_hold_arms(self):
        def run():
            ok, message = self.ctrl.hold_arms()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_free_left_arm(self):
        def run():
            ok, message = self.ctrl.free_left_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_hold_left_arm(self):
        def run():
            ok, message = self.ctrl.hold_left_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_free_right_arm(self):
        def run():
            ok, message = self.ctrl.free_right_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_hold_right_arm(self):
        def run():
            ok, message = self.ctrl.hold_right_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_move_only_left_arm(self):
        def run():
            ok, message = self.ctrl.move_only_left_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_move_only_right_arm(self):
        def run():
            ok, message = self.ctrl.move_only_right_arm()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_free_head(self):
        def run():
            ok, message = self.ctrl.free_head()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_hold_head(self):
        def run():
            ok, message = self.ctrl.hold_head()
            self.enqueue_log("[STIFF] %s" % safe_unicode(message))
        self._run_async(run)

    def on_open_left_hand(self):
        def run():
            ok, message = self.ctrl.open_hand("LHand")
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_close_left_hand(self):
        def run():
            ok, message = self.ctrl.close_hand("LHand")
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_open_right_hand(self):
        def run():
            ok, message = self.ctrl.open_hand("RHand")
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_close_right_hand(self):
        def run():
            ok, message = self.ctrl.close_hand("RHand")
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_open_both_hands(self):
        def run():
            ok, message = self.ctrl.open_both_hands()
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_close_both_hands(self):
        def run():
            ok, message = self.ctrl.close_both_hands()
            self.enqueue_log("[HAND] %s" % safe_unicode(message))
        self._run_async(run)

    def on_dump_pose(self):
        dt = self._get_dt_value()
        joints = list(self.capture_joints)

        def run():
            # Meccanismo originale: leggo una sola posa corrente dal robot.
            # L'unica aggiunta e' la validazione prima del salvataggio.
            ok, angles = self.ctrl.get_pose(joints)
            if not ok:
                self.enqueue_log("[DUMP] FAIL: %s" % safe_unicode(angles))
                return

            is_valid, warnings, errors = self.ctrl.validate_frame_pose(joints, angles)

            if not is_valid:
                self.enqueue_log("[VALIDAZIONE] FRAME NON SALVATO")
                for err in errors:
                    self.enqueue_log("[VALIDAZIONE] ERRORE: %s" % safe_unicode(err))
                return

            for warn in warnings:
                self.enqueue_log("[VALIDAZIONE] WARN: %s" % safe_unicode(warn))

            self.frames.append({"angles": angles, "dt": dt})
            self.enqueue_log("[DUMP] Frame %d catturato (dt=%.2f) - joints=%d" % (len(self.frames), dt, len(joints)))
            try:
                preview = ", ".join(["%.3f" % float(value) for value in angles[:4]])
                self.enqueue_log("[DUMP] Angoli preview: %s ..." % preview)
            except Exception:
                pass
            self.enqueue_log("[UI] aggiorno lista frame")
        self._run_async(run)

    def on_remove_frame(self):
        try:
            selected = self.list_frames.curselection()
            if not selected:
                return
            index = int(selected[0])
            if 0 <= index < len(self.frames):
                self.frames.pop(index)
                self.enqueue_log("[FRAME] Rimosso frame %d" % (index + 1))
                self._refresh_frames_listbox()
        except Exception:
            pass

    def on_copy_selected_frame(self):
        """
        Duplica il frame selezionato e lo aggiunge in fondo alla sequenza.
        Utile per ripetere pose o movimenti gia' registrati senza ricatturarli.
        """
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[FRAME] Seleziona prima un frame da copiare.")
            return

        try:
            new_frame = copy.deepcopy(self.frames[index])
        except Exception:
            # Fallback semplice: i frame contengono normalmente solo dict/list/numeri.
            old_frame = self.frames[index]
            new_frame = {
                "angles": list(old_frame.get("angles", [])),
                "dt": old_frame.get("dt", 0.6),
            }
            if old_frame.get("composite"):
                new_frame["composite"] = True

        # Mantengo eventuali metadati utili, ma aggiungo una traccia nel JSON.
        new_frame["copied_from_frame"] = index + 1

        angles = new_frame.get("angles", [])
        is_valid, warnings, errors = self.ctrl.validate_frame_pose(self.capture_joints, angles)
        if not is_valid:
            self.enqueue_log("[FRAME] Copia NON creata: il frame di origine non e' valido")
            for err in errors:
                self.enqueue_log("[FRAME] ERRORE: %s" % safe_unicode(err))
            return

        for warn in warnings:
            self.enqueue_log("[FRAME] WARN copia: %s" % safe_unicode(warn))

        self.frames.append(new_frame)
        new_index = len(self.frames) - 1
        self._refresh_frames_listbox()
        self._select_frame_index(new_index)
        self._load_selected_frame_to_editor()
        self.enqueue_log("[FRAME] Copiato frame %d come nuovo frame %d" % (index + 1, new_index + 1))

    def on_clear_frames(self):
        self.frames = []
        self._refresh_frames_listbox()
        self.var_edit_dt.set("")
        self.var_edit_angle.set("")
        self.enqueue_log("[FRAME] Clear completato")

    def on_apply_dt_all(self):
        dt = self._get_dt_value()
        for frame in self.frames:
            frame["dt"] = dt
        self._refresh_frames_listbox()
        self.enqueue_log("[FRAME] dt applicato a tutti: %.2f" % dt)

    def on_test_frames(self):
        joints = list(self.capture_joints)
        frames_copy = list(self.frames)

        def run():
            if not frames_copy:
                self.enqueue_log("[TEST] Nessun frame da eseguire.")
                return
            ok, message = self.ctrl.run_frames_gesture(joints, frames_copy)
            self.enqueue_log("[TEST] %s" % safe_unicode(message))
        self._run_async(run)

    def on_save_sequence(self):
        gesture_dir = self.config["paths"]["gesture_dir"]
        ensure_dir(gesture_dir)
        default_path = self.gesture_store.build_default_sequence_path(self.var_capture_name.get().strip() or "GESTO")

        path = tkFileDialog.asksaveasfilename(
            initialdir=gesture_dir,
            initialfile=os.path.basename(default_path),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            self.gesture_store.save_frames_sequence(path, self.var_capture_name.get().strip(), self.capture_joints, self.frames)
            self.enqueue_log("[SAVE] Sequenza salvata: %s" % path)
        except Exception as exc:
            self.enqueue_log("[SAVE] FAIL: %s" % str(exc))

    def on_load_sequence(self):
        gesture_dir = self.config["paths"]["gesture_dir"]
        ensure_dir(gesture_dir)
        path = tkFileDialog.askopenfilename(
            initialdir=gesture_dir,
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            data = read_json(path)
            if data.get("format") != "frames_v1":
                self.enqueue_log("[LOAD] Formato non supportato.")
                return

            self.var_capture_name.set(data.get("name", "GESTO_" + now_stamp()))
            self.capture_joints = data.get("joints", list(DEFAULT_JOINTS))
            self._ensure_hand_capture_joints()
            self.frames = data.get("frames", [])
            self._refresh_joint_selector()
            self._refresh_frames_listbox()
            self.var_edit_dt.set("")
            self.var_edit_angle.set("")
            self.enqueue_log("[LOAD] Sequenza caricata: %s (frames=%d)" % (path, len(self.frames)))
        except Exception as exc:
            self.enqueue_log("[LOAD] FAIL: %s" % str(exc))

    def on_export_ready_gesture(self):
        if not self.frames:
            self.enqueue_log("[EXPORT] Nessun frame.")
            return

        joints = list(self.capture_joints)
        frames_copy = list(self.frames)
        times_by_joint, angles_by_joint = self.ctrl.build_interpolation_from_frames(joints, frames_copy)

        gesture_dir = self.config["paths"]["gesture_dir"]
        ensure_dir(gesture_dir)
        default_path = self.gesture_store.build_default_ready_path(self.var_capture_name.get().strip() or "GESTO")

        path = tkFileDialog.asksaveasfilename(
            initialdir=gesture_dir,
            initialfile=os.path.basename(default_path),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            self.gesture_store.export_ready_gesture(
                path,
                self.var_capture_name.get().strip(),
                joints,
                times_by_joint,
                angles_by_joint,
            )
            self.enqueue_log("[EXPORT] Gesture pronta salvata: %s" % path)
            self.enqueue_log("[EXPORT] Usa come gesture_id: %s" % safe_unicode(self.var_capture_name.get().strip()).lower())
        except Exception as exc:
            self.enqueue_log("[EXPORT] FAIL: %s" % str(exc))

    def _tick(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                if message == "[UI] aggiorno lista frame":
                    self._refresh_frames_listbox()
                elif safe_unicode(message).startswith("[UI] seleziona frame:"):
                    try:
                        index = int(safe_unicode(message).split(":", 1)[1])
                        self._select_frame_index(index)
                        self._load_selected_frame_to_editor()
                    except Exception:
                        pass
                else:
                    self._append_log(message)
        except Exception:
            pass

        try:
            self.var_robot.set("%s:%d" % (self.ctrl.robot_ip, self.ctrl.robot_port))
            self.var_webapp.set("OK" if self.ctrl.connected_to_webapp else "OFF")
            self.var_life.set(self.ctrl.get_autonomous_life_state())
            self.var_error.set(self.ctrl.last_error)

            ok, volume_or_msg = self.ctrl.get_volume()
            if ok:
                self.var_volume.set("%d%%" % int(volume_or_msg))
            else:
                self.var_volume.set("N/A")

            last_cmd = self.ctrl.last_cmd
            if last_cmd and isinstance(last_cmd, dict):
                self.var_last.set(str(last_cmd.get("action", "")))
            else:
                self.var_last.set("")
        except Exception:
            pass

        self.root.after(500, self._tick)

    def on_close(self):
        self.enqueue_log("[EXIT] Chiusura richiesta...")
        self.ctrl.running = False
        if self.config["ui"].get("rest_on_close", True):
            try:
                self.ctrl.rest()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
