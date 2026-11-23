# -*- coding: utf-8 -*-
"""Scheda 4: temperatura dei motori, ostacoli vicini alle braccia, protezioni di ALMotion."""
from __future__ import absolute_import

import time

from peppersign.compat import tk, tkMessageBox
from peppersign.robot.safety import PROTECTIONS
from peppersign.ui.tabs import LABEL_FONT, VALUE_FONT
from peppersign.utils import safe_unicode

TEMP_COLORS = ("dark green", "dark orange", "red")


def _distance_color(distance):
    return "red" if distance < 0.3 else ("dark orange" if distance < 0.6 else "dark green")


class SafetyTab(object):
    def __init__(self, gui, tab):
        self.gui = gui
        self.ctrl = gui.ctrl
        self._demo_obstacle = False
        self._build(tab)

    def _build(self, tab):
        value_font, label_font = VALUE_FONT, LABEL_FONT
        left = tk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(tab)
        right.pack(side="left", fill="both", expand=True)

        # Temperatura dei motori: valori letti in background dal controller (ALMemory)
        box_temp = tk.LabelFrame(left, text="Temperatura motori (°C)", padx=10, pady=8)
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
                                "premi Riposo e fai una pausa). Aggiornata ogni ~3 s.",
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
        self.btn_demo_obstacle = tk.Button(row_obst, text="Simula ostacolo a destra (demo)",
                                           command=self.on_toggle_demo_obstacle)
        self.btn_demo_obstacle.pack(side="left")
        tk.Label(box_obst, text="Distanza tra l'ostacolo più vicino e la mano. Se il braccio viene rallentato "
                                "(rosso), allontana il robot dall'ostacolo o spostati tu: la protezione frena le braccia "
                                "anche nelle zone che i sensori non vedono.",
                 fg="grey30", wraplength=620, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # Protezioni di ALMotion
        box_prot = tk.LabelFrame(right, text="Protezioni del robot", padx=10, pady=8)
        box_prot.pack(fill="x", padx=10, pady=6)
        self.protection_vars = {}
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
                tk.Label(box_prot, text="(solo lettura: protegge i motori)", fg="grey30").grid(
                    row=r, column=2, columnspan=2, sticky="w")
            self.protection_vars[key] = (var, lbl)
        row_prot = tk.Frame(box_prot)
        row_prot.grid(row=len(PROTECTIONS), column=0, columnspan=4, sticky="w", pady=(8, 0))
        tk.Button(row_prot, text="Ripristina tutte", command=self.on_restore_protections).pack(side="left", padx=(0, 6))
        tk.Button(row_prot, text="Aggiorna stato", command=self.on_refresh_protections).pack(side="left")
        tk.Label(box_prot, text="Le protezioni disattivate da qui vengono riattivate alla chiusura del pannello. "
                                "Disattiva l'anti-collisione esterna solo se nessuno è a portata delle braccia; "
                                "senza anti-collisione con il corpo le braccia possono urtare tablet e testa.",
                 fg="dark red", wraplength=620, justify="left").grid(
            row=len(PROTECTIONS) + 1, column=0, columnspan=4, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------- pulsanti

    def on_set_protection(self, key, enabled):
        gui = self.gui
        if not enabled and tkMessageBox is not None:
            try:
                if not tkMessageBox.askyesno("Disattivare la protezione?",
                                             "La protezione verrà disattivata finché non la riattivi o chiudi il pannello.\n"
                                             "Assicurati che nessuno sia a portata delle braccia del robot.\n\nProcedere?"):
                    return
            except Exception:
                pass

        def run():
            ok, message = self.ctrl.set_protection(key, enabled)
            gui.enqueue_log("[SICUREZZA] %s" % safe_unicode(message))
        gui.run_async(run)

    def on_restore_protections(self):
        gui = self.gui

        def run():
            ok, message = self.ctrl.restore_protections()
            gui.enqueue_log("[SICUREZZA] %s" % safe_unicode(message))
        gui.run_async(run)

    def on_refresh_protections(self):
        gui = self.gui

        def run():
            self.ctrl.refresh_protections()
            self.ctrl.refresh_obstacles()
            gui.enqueue_log("[SICUREZZA] Stato delle protezioni aggiornato")
        gui.run_async(run)

    def on_reset_safety_counts(self):
        self.ctrl.reset_safety_counts()
        self.gui.enqueue_log("[SICUREZZA] Conteggi dei rallentamenti azzerati")

    def on_toggle_demo_obstacle(self):
        self._demo_obstacle = not self._demo_obstacle
        ok, message = self.ctrl.simulate_obstacle([0.25, -0.35, 0.0] if self._demo_obstacle else None)
        self.gui.enqueue_log("[DEMO] %s" % safe_unicode(message))
        if not ok:
            self._demo_obstacle = False

    # --------------------------------------------------------- aggiornamento

    def refresh(self):
        """Valori in cache del controller (nessuna chiamata al robot)."""
        self._update_temperatures()
        self._update_safety()

    def _update_temperatures(self):
        gui = self.gui
        temps = getattr(self.ctrl, "cached_temperatures", {}) or {}
        hottest = None
        for joint, (var, lbl) in self.temp_labels.items():
            value = temps.get(joint)
            if not value:
                var.set("-")
                lbl.config(fg="grey40")
                continue
            temperature, status = value
            level = self.ctrl.temperature_level(temperature, status)
            var.set("%.0f" % temperature)
            lbl.config(fg=TEMP_COLORS[level])
            if hottest is None or temperature > hottest[1]:
                hottest = (joint, temperature, level)
        if hottest is None:
            gui.var_temp_bar.set("n.d.")
            gui.log_panel.lbl_temp_bar.config(fg="grey40")
        else:
            gui.var_temp_bar.set("max %.0f C (%s)" % (hottest[1], hottest[0]))
            gui.log_panel.lbl_temp_bar.config(fg=TEMP_COLORS[hottest[2]])

    def _update_safety(self):
        gui = self.gui
        now = time.time()
        obstacles = getattr(self.ctrl, "cached_obstacles", {}) or {}
        events = getattr(self.ctrl, "safety_events", {}) or {}
        worst = None
        for chain, (var_dist, lbl_dist, var_clip, lbl_clip) in self.obstacle_vars.items():
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
                lbl_dist.config(fg=_distance_color(distance))
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
        bar = gui.log_panel.lbl_obst_bar
        recent = [c for c, e in events.items() if e.get("count") and now - e.get("last", 0) < 5]
        if recent:
            gui.var_obst_bar.set("RALLENTATO %s" % "/".join("SX" if c == "LArm" else "DX" for c in sorted(recent)))
            bar.config(fg="red")
        elif worst is not None:
            gui.var_obst_bar.set("%s %.0f cm" % ("SX" if worst[0] == "LArm" else "DX", 100 * worst[1]))
            bar.config(fg=_distance_color(worst[1]))
        else:
            gui.var_obst_bar.set("nessuno" if obstacles else "n.d.")
            bar.config(fg="dark green" if obstacles else "grey40")
        protections = getattr(self.ctrl, "cached_protections", {}) or {}
        for key, (var, lbl) in self.protection_vars.items():
            value = protections.get(key)
            if value is None:
                var.set("n.d." if not protections else "non disponibile")
                lbl.config(fg="grey40")
            else:
                var.set("ATTIVA" if value else "DISATTIVATA")
                lbl.config(fg="dark green" if value else "red")
        self.btn_demo_obstacle.config(state="normal" if self.ctrl.fake_robot else "disabled")
