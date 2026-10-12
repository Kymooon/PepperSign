# -*- coding: utf-8 -*-
from __future__ import absolute_import

import copy
import os
import threading
import time

from peppersign.compat import queue, tk, tkFileDialog, tkMessageBox, ttk
from peppersign.gesture_store import DEFAULT_JOINTS
from peppersign.utils import ensure_dir, now_stamp, read_json, safe_unicode


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

    # ------------------------------------------------------------------
    # Layout: pannelli a schede (Stato / Comandi / Registrazione segni)
    # con il log sempre visibile nella parte bassa della finestra.
    # ------------------------------------------------------------------

    def _build(self):
        self.var_mode = tk.StringVar()
        self.var_gesture_count = tk.StringVar()
        self.var_autonomy = tk.StringVar()
        self.var_connection = tk.StringVar(value="NON CONNESSO")

        paned = tk.PanedWindow(self.root, orient="vertical", sashrelief="raised", sashwidth=6)
        paned.pack(fill="both", expand=True, padx=8, pady=6)

        top = tk.Frame(paned)
        paned.add(top, minsize=300)
        bottom = tk.Frame(paned)
        paned.add(bottom, minsize=100)

        tab_status, tab_commands, tab_recording, tab_safety = self._create_tabs(top, [
            "1) Stato robot",
            "2) Comandi",
            "3) Registrazione segni",
            "4) Sicurezza e motori",
        ])
        self._build_status_tab(tab_status)
        self._build_commands_tab(tab_commands)
        self._build_recording_tab(tab_recording)
        self._build_safety_tab(tab_safety)
        self._build_log(bottom)

        # Divisore iniziale: circa 72% schede, 28% log (regolabile trascinando)
        def place_sash():
            try:
                height = paned.winfo_height()
                if height > 200:
                    paned.sash_place(0, 0, int(height * 0.72))
            except Exception:
                pass
        self.root.after(300, place_sash)

    def _create_tabs(self, parent, titles):
        """Crea le schede (ttk.Notebook, oppure pulsanti se ttk non e' disponibile)."""
        frames = []
        if ttk:
            self.notebook = ttk.Notebook(parent)
            self.notebook.pack(fill="both", expand=True)
            for title in titles:
                frame = tk.Frame(self.notebook)
                self.notebook.add(frame, text="  %s  " % title)
                frames.append(frame)
            return frames

        self.notebook = None
        bar = tk.Frame(parent)
        bar.pack(fill="x")
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True)
        for title in titles:
            frame = tk.Frame(container)
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            frames.append(frame)
            tk.Button(bar, text=title, command=frame.tkraise).pack(side="left", padx=2, pady=2)
        frames[0].tkraise()
        return frames

    def _build_status_tab(self, tab):
        value_font = ("TkDefaultFont", 11, "bold")
        label_font = ("TkDefaultFont", 11)

        box_robot = tk.LabelFrame(tab, text="Robot", padx=10, pady=8)
        box_robot.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(box_robot, text="Connessione:", font=label_font).grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_connection = tk.Label(box_robot, textvariable=self.var_connection, font=value_font)
        self.lbl_connection.grid(row=0, column=1, sticky="w", padx=12, pady=2)
        row_conn = tk.Frame(box_robot)
        row_conn.grid(row=0, column=2, sticky="w", padx=12)
        tk.Button(row_conn, text="Riconnetti ora", command=self.on_reconnect).pack(side="left", padx=3)
        self.btn_simulate_disconnect = tk.Button(row_conn, text="Simula disconnessione (demo)", command=self.on_simulate_disconnect)
        self.btn_simulate_disconnect.pack(side="left", padx=3)

        rows = [
            ("Robot (IP:porta):", self.var_robot),
            ("Modalita':", self.var_mode),
            ("Autonomous Life:", self.var_life),
            ("Volume:", self.var_volume),
            ("Autonomia durante i gesti:", self.var_autonomy),
        ]
        for row, (label, var) in enumerate(rows, 1):
            tk.Label(box_robot, text=label, font=label_font).grid(row=row, column=0, sticky="w", pady=2)
            tk.Label(box_robot, textvariable=var, font=value_font).grid(row=row, column=1, sticky="w", padx=12, pady=2)

        # Scelta del robot: demo/reale e indirizzo, senza modificare il file .env
        self.var_target_mode = tk.StringVar(value="demo" if self.ctrl.fake_robot else "real")
        self.var_target_ip = tk.StringVar(value=safe_unicode(self.ctrl.robot_ip))
        self.var_target_port = tk.StringVar(value=safe_unicode(self.ctrl.robot_port))
        box_target = tk.LabelFrame(tab, text="Scegli robot", padx=10, pady=8)
        box_target.pack(fill="x", padx=10, pady=6)
        tk.Radiobutton(box_target, text="Robot reale (Pepper)", variable=self.var_target_mode, value="real",
                       font=label_font).grid(row=0, column=0, sticky="w", padx=(0, 16))
        tk.Radiobutton(box_target, text="Demo (robot simulato)", variable=self.var_target_mode, value="demo",
                       font=label_font).grid(row=0, column=1, columnspan=2, sticky="w")
        tk.Label(box_target, text="Indirizzo IP:", font=label_font).grid(row=1, column=0, sticky="w", pady=(6, 2))
        entry_ip = tk.Entry(box_target, textvariable=self.var_target_ip, width=20, font=label_font)
        entry_ip.grid(row=1, column=1, sticky="w", pady=(6, 2))
        entry_ip.bind("<Return>", lambda event: self.on_apply_target())
        tk.Label(box_target, text="Porta:", font=label_font).grid(row=1, column=2, sticky="w", padx=(16, 4), pady=(6, 2))
        tk.Entry(box_target, textvariable=self.var_target_port, width=7, font=label_font).grid(row=1, column=3, sticky="w", pady=(6, 2))
        tk.Button(box_target, text="Applica e connetti", command=self.on_apply_target).grid(row=1, column=4, sticky="w", padx=(16, 0), pady=(6, 2))
        tk.Label(box_target, text="Vale fino al riavvio del controller; i valori di partenza restano quelli del file .env.",
                 fg="grey30").grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

        box_webapp = tk.LabelFrame(tab, text="WebApp e comandi", padx=10, pady=8)
        box_webapp.pack(fill="x", padx=10, pady=6)
        tk.Label(box_webapp, text="WebApp:", font=label_font).grid(row=0, column=0, sticky="w", pady=2)
        tk.Label(box_webapp, textvariable=self.var_webapp, font=value_font).grid(row=0, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_webapp, text="Ultimo comando:", font=label_font).grid(row=1, column=0, sticky="w", pady=2)
        tk.Label(box_webapp, textvariable=self.var_last, font=value_font).grid(row=1, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_webapp, text="Ultimo errore:", font=label_font).grid(row=2, column=0, sticky="nw", pady=2)
        tk.Label(box_webapp, textvariable=self.var_error, font=label_font, fg="red",
                 wraplength=900, justify="left").grid(row=2, column=1, sticky="w", padx=12, pady=2)

        box_conf = tk.LabelFrame(tab, text="Configurazione", padx=10, pady=8)
        box_conf.pack(fill="x", padx=10, pady=6)
        info = [
            ("URL WebApp:", safe_unicode(self.config["webapp"].get("base_url", ""))),
            ("Cartella gesti:", safe_unicode(self.config["paths"].get("gesture_dir", ""))),
        ]
        for row, (label, value) in enumerate(info):
            tk.Label(box_conf, text=label, font=label_font).grid(row=row, column=0, sticky="w", pady=2)
            tk.Label(box_conf, text=value, font=label_font).grid(row=row, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_conf, text="Gesti caricati:", font=label_font).grid(row=len(info), column=0, sticky="w", pady=2)
        tk.Label(box_conf, textvariable=self.var_gesture_count, font=label_font).grid(row=len(info), column=1, sticky="w", padx=12, pady=2)

    def _build_safety_tab(self, tab):
        """Temperatura dei motori, ostacoli vicini alle braccia e protezioni di ALMotion."""
        value_font = ("TkDefaultFont", 11, "bold")
        label_font = ("TkDefaultFont", 11)
        left = tk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)
        tab = left

        # Temperatura dei motori: valori letti in background dal controller (ALMemory)
        box_temp = tk.LabelFrame(tab, text="Temperatura motori (C)", padx=10, pady=8)
        box_temp.pack(fill="x", padx=10, pady=6)
        self.temp_labels = {}
        rows = [("Spalla pitch", "ShoulderPitch"), ("Spalla roll", "ShoulderRoll"), ("Gomito yaw", "ElbowYaw"),
                ("Gomito roll", "ElbowRoll"), ("Polso yaw", "WristYaw"), ("Mano", "Hand")]
        tk.Label(box_temp, text="SX", font=value_font).grid(row=0, column=1, padx=12)
        tk.Label(box_temp, text="DX", font=value_font).grid(row=0, column=2, padx=12)
        for r, (label, suffix) in enumerate(rows, 1):
            tk.Label(box_temp, text=label, font=label_font).grid(row=r, column=0, sticky="w")
            for c, side in enumerate(("L", "R"), 1):
                var = tk.StringVar(value="-")
                lbl = tk.Label(box_temp, textvariable=var, font=label_font, width=6)
                lbl.grid(row=r, column=c)
                self.temp_labels[side + suffix] = (var, lbl)
        tk.Label(box_temp, text="Testa (yaw / pitch)", font=label_font).grid(row=len(rows) + 1, column=0, sticky="w")
        for c, joint in enumerate(("HeadYaw", "HeadPitch"), 1):
            var = tk.StringVar(value="-")
            lbl = tk.Label(box_temp, textvariable=var, font=label_font, width=6)
            lbl.grid(row=len(rows) + 1, column=c)
            self.temp_labels[joint] = (var, lbl)
        tk.Label(box_temp, text="Verde = normale, arancione = calda, rosso = molto calda (NAOqi riduce la forza: "
                                "fai Rest e una pausa). Aggiornata ogni ~3 s.",
                 fg="grey30", wraplength=600, justify="left").grid(row=0, column=3, rowspan=4, sticky="nw", padx=(30, 0))

        # Ostacoli vicini alle braccia (protezione anti-collisione esterna)
        box_obst = tk.LabelFrame(right, text="Ostacoli vicini alle braccia", padx=10, pady=8)
        box_obst.pack(fill="x", padx=10, pady=(10, 6))
        self.obstacle_vars = {}
        for r, (chain, label) in enumerate((("LArm", "Braccio SX"), ("RArm", "Braccio DX"))):
            tk.Label(box_obst, text=label, font=label_font).grid(row=r, column=0, sticky="w", pady=2)
            var_dist = tk.StringVar(value="-")
            lbl_dist = tk.Label(box_obst, textvariable=var_dist, font=value_font, width=30, anchor="w")
            lbl_dist.grid(row=r, column=1, sticky="w", padx=10)
            var_clip = tk.StringVar(value="")
            lbl_clip = tk.Label(box_obst, textvariable=var_clip, font=label_font, width=34, anchor="w")
            lbl_clip.grid(row=r, column=2, sticky="w")
            self.obstacle_vars[chain] = (var_dist, lbl_dist, var_clip, lbl_clip)
        row_obst = tk.Frame(box_obst)
        row_obst.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        tk.Button(row_obst, text="Azzera conteggi", command=self.on_reset_safety_counts).pack(side="left", padx=(0, 6))
        self.btn_demo_obstacle = tk.Button(row_obst, text="Simula ostacolo a destra (demo)", command=self.on_toggle_demo_obstacle)
        self.btn_demo_obstacle.pack(side="left")
        tk.Label(box_obst, text="Distanza tra l'ostacolo piu' vicino e la mano. Se il braccio viene rallentato "
                                "(rosso), allontana il robot dall'ostacolo o spostati tu: la protezione frena le braccia "
                                "anche nelle zone che i sensori non vedono.",
                 fg="grey30", wraplength=620, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # Protezioni di ALMotion
        box_prot = tk.LabelFrame(right, text="Protezioni del robot", padx=10, pady=8)
        box_prot.pack(fill="x", padx=10, pady=6)
        self.protection_vars = {}
        from peppersign.controller import PROTECTIONS
        for r, (key, label, _kind, _name, editable) in enumerate(PROTECTIONS):
            tk.Label(box_prot, text=label, font=label_font).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="-")
            lbl = tk.Label(box_prot, textvariable=var, font=value_font, width=12)
            lbl.grid(row=r, column=1, padx=10)
            if editable:
                tk.Button(box_prot, text="Disattiva", width=9,
                          command=lambda k=key: self.on_set_protection(k, False)).grid(row=r, column=2, padx=2)
                tk.Button(box_prot, text="Attiva", width=9,
                          command=lambda k=key: self.on_set_protection(k, True)).grid(row=r, column=3, padx=2)
            else:
                tk.Label(box_prot, text="(solo lettura: protegge i motori)", fg="grey30").grid(row=r, column=2, columnspan=2, sticky="w")
            self.protection_vars[key] = (var, lbl)
        row_prot = tk.Frame(box_prot)
        row_prot.grid(row=len(PROTECTIONS), column=0, columnspan=4, sticky="w", pady=(8, 0))
        tk.Button(row_prot, text="Ripristina tutte", command=self.on_restore_protections).pack(side="left", padx=(0, 6))
        tk.Button(row_prot, text="Aggiorna stato", command=self.on_refresh_protections).pack(side="left")
        tk.Label(box_prot, text="Le protezioni disattivate da qui vengono riattivate alla chiusura del pannello. "
                                "Disattiva l'anti-collisione esterna solo se nessuno e' a portata delle braccia; "
                                "senza anti-collisione con il corpo le braccia possono urtare tablet e testa.",
                 fg="dark red", wraplength=620, justify="left").grid(row=len(PROTECTIONS) + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def _build_commands_tab(self, tab):
        grid = tk.Frame(tab)
        grid.pack(fill="both", expand=True, padx=10, pady=10)

        box_tts = tk.LabelFrame(grid, text="Voce (TTS)")
        box_tts.grid(row=0, column=0, sticky="nwe", padx=(0, 10), pady=6)
        tk.Entry(box_tts, textvariable=self.var_say_text, width=30).pack(side="left", padx=8, pady=8)
        tk.Button(box_tts, text="Dì", width=6, command=self.on_say).pack(side="left", padx=6)
        tk.Button(box_tts, text="Dì animato", width=10, command=self.on_say_animated).pack(side="left", padx=6)

        box_util = tk.LabelFrame(grid, text="Robot")
        box_util.grid(row=1, column=0, sticky="nwe", padx=(0, 10), pady=6)
        tk.Button(box_util, text="WakeUp", width=10, command=self.on_wakeup).pack(side="left", padx=8, pady=8)
        tk.Button(box_util, text="Rest", width=10, command=self.on_rest).pack(side="left", padx=6, pady=8)
        tk.Button(box_util, text="Life ON", width=10, command=self.on_life_on).pack(side="left", padx=6, pady=8)
        tk.Button(box_util, text="Life OFF", width=10, command=self.on_life_off).pack(side="left", padx=6, pady=8)

        box_volume = tk.LabelFrame(grid, text="Volume")
        box_volume.grid(row=0, column=1, sticky="nwe", pady=6)
        tk.Label(box_volume, text="Uscita:").pack(side="left", padx=(8, 4), pady=8)
        tk.Label(box_volume, textvariable=self.var_volume, width=6).pack(side="left", padx=(0, 8), pady=8)
        tk.Button(box_volume, text="Vol -", width=8, command=self.on_volume_down).pack(side="left", padx=6, pady=8)
        tk.Button(box_volume, text="Vol +", width=8, command=self.on_volume_up).pack(side="left", padx=6, pady=8)

        box_map = tk.LabelFrame(grid, text="Esegui gesto (PLAY_GESTURE)")
        box_map.grid(row=1, column=1, sticky="nwe", pady=6)
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

        # Spazio riservato ai controlli futuri (es. STOP di emergenza, testa, tablet)
        self.frm_commands_extra = tk.Frame(grid)
        self.frm_commands_extra.grid(row=2, column=0, columnspan=2, sticky="nwe", pady=6)

    def _build_recording_tab(self, tab):
        box_cap = tk.Frame(tab)
        box_cap.pack(fill="both", expand=True, padx=6, pady=6)

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

        # Riprendere la registrazione da un frame: il robot va nella posa del frame
        # selezionato e le braccia diventano "morbide" (si muovono a mano ma non cadono)
        self.var_soft_after = tk.IntVar(value=1)
        self.var_soft_group = tk.StringVar(value="both")
        self.var_soft_stiffness = tk.StringVar(value="0.40")
        self.var_soft_state = tk.StringVar(value="Morbido: OFF")
        row2d = tk.Frame(box_cap)
        row2d.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(row2d, text="Vai al frame selezionato", width=20, command=self.on_go_to_frame).pack(side="left", padx=(0, 4))
        tk.Checkbutton(row2d, text="poi braccia morbide", variable=self.var_soft_after).pack(side="left", padx=(0, 12))
        tk.Label(row2d, text="Braccia morbide:").pack(side="left")
        for label, value in (("entrambe", "both"), ("SX", "left"), ("DX", "right")):
            tk.Radiobutton(row2d, text=label, variable=self.var_soft_group, value=value).pack(side="left")
        tk.Label(row2d, text="stiffness").pack(side="left", padx=(8, 2))
        tk.Spinbox(row2d, from_=0.10, to=0.80, increment=0.05, width=5, format="%.2f",
                   textvariable=self.var_soft_stiffness).pack(side="left")
        tk.Button(row2d, text="Morbido ON", width=11, command=self.on_soft_on).pack(side="left", padx=(8, 3))
        tk.Button(row2d, text="Morbido OFF", width=11, command=self.on_soft_off).pack(side="left", padx=3)
        tk.Label(row2d, textvariable=self.var_soft_state, fg="dark green").pack(side="left", padx=8)

        row3 = tk.Frame(box_cap)
        row3.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_list = tk.Frame(row3)
        left_list.pack(side="left", fill="both", expand=True)
        tk.Label(left_list, text="Frames catturati (ordine):").pack(anchor="w")
        list_scroll = tk.Scrollbar(left_list, orient="vertical")
        self.list_frames = tk.Listbox(left_list, height=10, yscrollcommand=list_scroll.set, exportselection=False)
        list_scroll.config(command=self.list_frames.yview)
        list_scroll.pack(side="right", fill="y")
        self.list_frames.pack(side="left", fill="both", expand=True)
        self.list_frames.bind("<<ListboxSelect>>", self.on_frame_select)

        # Colonna A: gestione frame e file
        col_a = tk.Frame(row3)
        col_a.pack(side="left", fill="y", padx=(10, 0))

        box_frames = tk.LabelFrame(col_a, text="Frame")
        box_frames.pack(fill="x", pady=(0, 3))
        row_move = tk.Frame(box_frames)
        row_move.pack(padx=4, pady=(4, 2))
        tk.Button(row_move, text="Sposta su", width=8, command=self.on_move_frame_up).pack(side="left", padx=(0, 2))
        tk.Button(row_move, text="Sposta giu", width=8, command=self.on_move_frame_down).pack(side="left", padx=(2, 0))
        tk.Button(box_frames, text="Rimuovi selezionato", width=18, command=self.on_remove_frame).pack(padx=4, pady=2)
        tk.Button(box_frames, text="Copia frame", width=18, command=self.on_copy_selected_frame).pack(padx=4, pady=2)
        tk.Button(box_frames, text="Clear", width=18, command=self.on_clear_frames).pack(padx=4, pady=(2, 4))

        box_file = tk.LabelFrame(col_a, text="File / test gesture")
        box_file.pack(fill="x", pady=(6, 3))
        tk.Button(box_file, text="Test gesture", width=18, command=self.on_test_frames).pack(padx=4, pady=(4, 2))
        tk.Button(box_file, text="Salva sequenza JSON", width=18, command=self.on_save_sequence).pack(padx=4, pady=2)
        tk.Button(box_file, text="Carica sequenza JSON", width=18, command=self.on_load_sequence).pack(padx=4, pady=2)
        tk.Button(box_file, text="Esporta gesture pronta", width=18, command=self.on_export_ready_gesture).pack(padx=4, pady=(2, 4))

        # Colonna B: modifica dei frame
        col_b = tk.Frame(row3)
        col_b.pack(side="left", fill="y", padx=(10, 0))

        box_edit = tk.LabelFrame(col_b, text="Tuning frame")
        box_edit.pack(fill="x", pady=(0, 3))

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

        # Colonna C: specchio e frame composito
        col_c = tk.Frame(row3)
        col_c.pack(side="left", fill="y", padx=(10, 0))

        box_mirror = tk.LabelFrame(col_c, text="Specchia frame")
        box_mirror.pack(fill="x", pady=(0, 3))
        tk.Button(box_mirror, text="SX -> DX", width=8, command=self.on_mirror_left_to_right).pack(side="left", padx=4, pady=4)
        tk.Button(box_mirror, text="DX -> SX", width=8, command=self.on_mirror_right_to_left).pack(side="left", padx=4, pady=4)

        box_composite = tk.LabelFrame(col_c, text="Frame composito")
        box_composite.pack(fill="x", pady=(6, 3))
        tk.Button(box_composite, text="Nuovo comp.", width=18, command=self.on_new_composite_frame).pack(padx=4, pady=(4, 2))
        row_comp_1 = tk.Frame(box_composite)
        row_comp_1.pack(fill="x", padx=4, pady=2)
        tk.Button(row_comp_1, text="Agg. SX", width=8, command=self.on_update_left_in_selected_frame).pack(side="left", padx=(0, 4))
        tk.Button(row_comp_1, text="Agg. DX", width=8, command=self.on_update_right_in_selected_frame).pack(side="left", padx=4)
        row_comp_2 = tk.Frame(box_composite)
        row_comp_2.pack(fill="x", padx=4, pady=(2, 4))
        tk.Button(row_comp_2, text="Agg. Testa", width=18, command=self.on_update_head_in_selected_frame).pack(side="left")

        box_coord = tk.LabelFrame(col_c, text="Frame da coordinate (beta)")
        box_coord.pack(fill="x", pady=(6, 3))
        tk.Button(box_coord, text="Apri...", width=18, command=self.on_open_pose_dialog).pack(padx=4, pady=4)

    def _build_log(self, parent):
        # Barra di stato sempre visibile (sopra il log, in tutte le schede)
        bar = tk.Frame(parent)
        bar.pack(fill="x", pady=(2, 2))
        tk.Label(bar, text="Robot:").pack(side="left")
        self.lbl_connection_bar = tk.Label(bar, textvariable=self.var_connection, font=("TkDefaultFont", 10, "bold"))
        self.lbl_connection_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="WebApp:").pack(side="left")
        tk.Label(bar, textvariable=self.var_webapp, font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Motori:").pack(side="left")
        self.var_temp_bar = tk.StringVar(value="-")
        self.lbl_temp_bar = tk.Label(bar, textvariable=self.var_temp_bar, font=("TkDefaultFont", 10, "bold"))
        self.lbl_temp_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Ostacoli:").pack(side="left")
        self.var_obst_bar = tk.StringVar(value="-")
        self.lbl_obst_bar = tk.Label(bar, textvariable=self.var_obst_bar, font=("TkDefaultFont", 10, "bold"))
        self.lbl_obst_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Log:").pack(side="left", padx=(20, 0))
        log_scroll = tk.Scrollbar(parent, orient="vertical")
        self.txt_log = tk.Text(parent, height=10, wrap="word", yscrollcommand=log_scroll.set)
        log_scroll.config(command=self.txt_log.yview)
        log_scroll.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)
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

    # ------------------------------------------------------------------
    # Riprendere da un frame, braccia morbide, ordine dei frame
    # ------------------------------------------------------------------

    def _soft_stiffness_value(self):
        try:
            value = float(self.var_soft_stiffness.get())
        except Exception:
            self.enqueue_log("[MORBIDO] Stiffness non valida, uso 0.40")
            value = 0.40
        value = max(0.10, min(value, 0.80))
        self.var_soft_stiffness.set("%.2f" % value)
        return value

    TEMP_COLORS = ("dark green", "dark orange", "red")

    def _update_safety(self):
        """Aggiorna ostacoli e protezioni dai valori in cache (nessuna chiamata al robot)."""
        now = time.time()
        obstacles = getattr(self.ctrl, "cached_obstacles", {}) or {}
        events = getattr(self.ctrl, "safety_events", {}) or {}
        worst = None
        for chain, (var_dist, lbl_dist, var_clip, lbl_clip) in getattr(self, "obstacle_vars", {}).items():
            obstacle = obstacles.get(chain)
            if obstacle is None:
                var_dist.set("non disponibile")
                lbl_dist.config(fg="grey40")
            elif obstacle.get("distance") is None:
                var_dist.set("nessun ostacolo vicino")
                lbl_dist.config(fg="dark green")
            else:
                distance = obstacle["distance"]
                var_dist.set("%.0f cm %s" % (100 * distance, obstacle.get("side", "")))
                lbl_dist.config(fg="red" if distance < 0.3 else ("dark orange" if distance < 0.6 else "dark green"))
                if worst is None or distance < worst[1]:
                    worst = (chain, distance)
            event = events.get(chain) or {}
            count, last = event.get("count", 0), event.get("last", 0.0)
            if count:
                ago = now - last
                var_clip.set("rallentato %d %s (ultima %s)" % (count, "volta" if count == 1 else "volte",
                                                              "ora" if ago < 2 else "%.0f s fa" % ago))
                lbl_clip.config(fg="red" if ago < 5 else "grey30")
            else:
                var_clip.set("mai rallentato")
                lbl_clip.config(fg="grey30")
        recent = [c for c, e in events.items() if e.get("count") and now - e.get("last", 0) < 5]
        if recent:
            self.var_obst_bar.set("RALLENTATO %s" % "/".join("SX" if c == "LArm" else "DX" for c in sorted(recent)))
            self.lbl_obst_bar.config(fg="red")
        elif worst is not None:
            self.var_obst_bar.set("%s %.0f cm" % ("SX" if worst[0] == "LArm" else "DX", 100 * worst[1]))
            self.lbl_obst_bar.config(fg="red" if worst[1] < 0.3 else ("dark orange" if worst[1] < 0.6 else "dark green"))
        else:
            self.var_obst_bar.set("nessuno" if obstacles else "n.d.")
            self.lbl_obst_bar.config(fg="dark green" if obstacles else "grey40")
        protections = getattr(self.ctrl, "cached_protections", {}) or {}
        for key, (var, lbl) in getattr(self, "protection_vars", {}).items():
            value = protections.get(key)
            if value is None:
                var.set("n.d." if not protections else "non disponibile")
                lbl.config(fg="grey40")
            else:
                var.set("ATTIVA" if value else "DISATTIVATA")
                lbl.config(fg="dark green" if value else "red")
        btn = getattr(self, "btn_demo_obstacle", None)
        if btn is not None:
            btn.config(state="normal" if self.ctrl.fake_robot else "disabled")

    def on_set_protection(self, key, enabled):
        if not enabled and tkMessageBox is not None:
            try:
                if not tkMessageBox.askyesno("Disattivare la protezione?",
                                             "La protezione verra' disattivata finche' non la riattivi o chiudi il pannello.\n"
                                             "Assicurati che nessuno sia a portata delle braccia del robot.\n\nProcedere?"):
                    return
            except Exception:
                pass

        def run():
            ok, message = self.ctrl.set_protection(key, enabled)
            self.enqueue_log("[SICUREZZA] %s" % safe_unicode(message))
        self._run_async(run)

    def on_restore_protections(self):
        def run():
            ok, message = self.ctrl.restore_protections()
            self.enqueue_log("[SICUREZZA] %s" % safe_unicode(message))
        self._run_async(run)

    def on_refresh_protections(self):
        def run():
            self.ctrl.refresh_protections()
            self.ctrl.refresh_obstacles()
            self.enqueue_log("[SICUREZZA] Stato delle protezioni aggiornato")
        self._run_async(run)

    def on_reset_safety_counts(self):
        self.ctrl.reset_safety_counts()
        self.enqueue_log("[SICUREZZA] Conteggi dei rallentamenti azzerati")

    def on_toggle_demo_obstacle(self):
        self._demo_obstacle = not getattr(self, "_demo_obstacle", False)
        ok, message = self.ctrl.simulate_obstacle([0.25, -0.35, 0.0] if self._demo_obstacle else None)
        self.enqueue_log("[DEMO] %s" % safe_unicode(message))
        if not ok:
            self._demo_obstacle = False

    def _update_temperatures(self):
        """Aggiorna l'indicatore delle temperature dai valori in cache (nessuna chiamata al robot)."""
        temps = getattr(self.ctrl, "cached_temperatures", {}) or {}
        hottest = None
        for joint, (var, lbl) in getattr(self, "temp_labels", {}).items():
            value = temps.get(joint)
            if not value:
                var.set("-")
                lbl.config(fg="grey40")
                continue
            temperature, status = value
            level = self.ctrl.temperature_level(temperature, status)
            var.set("%.0f" % temperature)
            lbl.config(fg=self.TEMP_COLORS[level])
            if hottest is None or temperature > hottest[1]:
                hottest = (joint, temperature, level)
        if hottest is None:
            self.var_temp_bar.set("n.d.")
            self.lbl_temp_bar.config(fg="grey40")
        else:
            self.var_temp_bar.set("max %.0f C (%s)" % (hottest[1], hottest[0]))
            self.lbl_temp_bar.config(fg=self.TEMP_COLORS[hottest[2]])

    def on_go_to_frame(self):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[POSA] Seleziona prima un frame nella lista.")
            return
        joints = list(self.capture_joints)
        angles = list(self.frames[index].get("angles", []))
        if len(angles) != len(joints):
            self.enqueue_log("[POSA] Il frame %d ha %d angoli, attesi %d: non posso usarlo." % (index + 1, len(angles), len(joints)))
            return
        soft_after = bool(self.var_soft_after.get())
        group = self.var_soft_group.get()
        stiffness = self._soft_stiffness_value()

        def run():
            ok, message = self.ctrl.go_to_pose(joints, angles)
            self.enqueue_log("[POSA] Frame %d -> %s" % (index + 1, safe_unicode(message)))
            if ok and soft_after:
                ok_soft, message_soft = self.ctrl.start_soft_hold(group, stiffness)
                self.enqueue_log("[MORBIDO] %s" % safe_unicode(message_soft))
        self.enqueue_log("[POSA] Movimento verso il frame %d..." % (index + 1))
        self._run_async(run)

    def on_soft_on(self):
        group = self.var_soft_group.get()
        stiffness = self._soft_stiffness_value()

        def run():
            ok, message = self.ctrl.start_soft_hold(group, stiffness)
            self.enqueue_log("[MORBIDO] %s" % safe_unicode(message))
        self._run_async(run)

    def on_soft_off(self):
        def run():
            ok, message = self.ctrl.stop_soft_hold(1.0)
            self.enqueue_log("[MORBIDO] %s" % safe_unicode(message))
        self._run_async(run)

    def _move_selected_frame(self, delta):
        index = self._get_selected_frame_index()
        if index is None:
            self.enqueue_log("[FRAME] Seleziona prima un frame da spostare.")
            return
        new_index = index + delta
        if new_index < 0 or new_index >= len(self.frames):
            return
        self.frames[index], self.frames[new_index] = self.frames[new_index], self.frames[index]
        self._refresh_frames_listbox()
        self._select_frame_index(new_index)
        try:
            self._load_selected_frame_to_editor()
        except Exception:
            pass
        self.enqueue_log("[FRAME] Frame %d spostato in posizione %d" % (index + 1, new_index + 1))

    def on_move_frame_up(self):
        self._move_selected_frame(-1)

    def on_move_frame_down(self):
        self._move_selected_frame(1)

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
            self.var_mode.set("DEMO - robot simulato" if self.ctrl.fake_robot else "Robot reale")
            self._update_title()
            btn = getattr(self, "btn_simulate_disconnect", None)
            if btn is not None:
                btn.config(state="normal" if self.ctrl.fake_robot else "disabled")
            self.var_gesture_count.set(str(len(self.gesture_store.keys())))
            self.var_autonomy.set(safe_unicode(self.config.get("robot_defaults", {}).get("gesture_autonomy", "pause")))
            self.var_webapp.set("OK" if self.ctrl.connected_to_webapp else "OFF")
            # Solo valori in cache (aggiornati da controller.monitor_loop):
            # nessuna chiamata al robot dal thread grafico.
            self.var_life.set(self.ctrl.cached_life_state)
            self.var_error.set(self.ctrl.last_error)
            volume = self.ctrl.cached_volume
            self.var_volume.set("%d%%" % int(volume) if volume is not None else "N/A")

            state = self.ctrl.connection_state
            self.var_connection.set(state)
            self._update_temperatures()
            self._update_safety()
            soft = self.ctrl.soft_hold_state()
            if soft:
                names = {"both": "entrambe", "left": "SX", "right": "DX"}
                self.var_soft_state.set("Morbido: ON (%s, %.2f)" % (names.get(soft[0], soft[0]), soft[1]))
            else:
                self.var_soft_state.set("Morbido: OFF")
            if self.ctrl.robot_connected:
                color = "dark green"
            elif state.startswith("CONNESSIONE"):
                color = "dark orange"
            else:
                color = "red"
            for label in (getattr(self, "lbl_connection", None), getattr(self, "lbl_connection_bar", None)):
                if label is not None:
                    label.config(fg=color)

            last_cmd = self.ctrl.last_cmd
            if last_cmd and isinstance(last_cmd, dict):
                self.var_last.set(str(last_cmd.get("action", "")))
            else:
                self.var_last.set("")
        except Exception:
            pass

        self.root.after(500, self._tick)

    def on_open_pose_dialog(self):
        """Finestra per creare un frame da punto del corpo + orientamento della mano (servizio Process)."""
        dialog = getattr(self, "_pose_dialog", None)
        if dialog is not None:
            try:
                dialog.win.lift()
                return
            except Exception:
                self._pose_dialog = None
        try:
            from peppersign.pose_dialog import PoseFromCoordinatesDialog
            self._pose_dialog = PoseFromCoordinatesDialog(self)
        except Exception as exc:
            self.enqueue_log("[COORD] Impossibile aprire la finestra: %s" % str(exc))

    def on_reconnect(self):
        self.enqueue_log("[ROBOT] Riconnessione in corso...")
        self.ctrl.request_reconnect()

    def on_apply_target(self):
        fake = self.var_target_mode.get() == "demo"
        ip = self.var_target_ip.get()
        port = self.var_target_port.get()

        def run():
            ok, message = self.ctrl.configure_target(fake, ip, port)
            self.enqueue_log("[ROBOT] %s" % safe_unicode(message))
            if not ok:
                self.ctrl.set_error(message)
        self._run_async(run)

    def _update_title(self):
        suffix = "  [DEMO - robot simulato]"
        base = getattr(self, "_base_title", None)
        if base is None:
            base = safe_unicode(self.config.get("ui", {}).get("window_title", "PepperSign")).replace(suffix, "")
            self._base_title = base
            self._shown_title = None
        title = base + (suffix if self.ctrl.fake_robot else "")
        if title != self._shown_title:
            self._shown_title = title
            try:
                self.root.title(title)
            except Exception:
                pass

    def on_simulate_disconnect(self):
        ok, message = self.ctrl.simulate_disconnect(15)
        self.enqueue_log("[DEMO] %s" % safe_unicode(message))

    def on_close(self):
        self.enqueue_log("[EXIT] Chiusura richiesta...")
        try:
            if self.ctrl.robot_connected:
                self.ctrl.restore_protections()     # riattiva le protezioni disattivate dal pannello
        except Exception:
            pass
        self.ctrl.running = False
        if self.config["ui"].get("rest_on_close", True) and self.ctrl.robot_connected:
            try:
                self.ctrl.rest()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()
