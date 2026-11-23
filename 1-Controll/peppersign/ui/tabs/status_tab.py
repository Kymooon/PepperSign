# -*- coding: utf-8 -*-
"""Scheda 1: stato del robot, scelta del robot (demo/reale), WebApp, configurazione."""
from __future__ import absolute_import

from peppersign.compat import tk
from peppersign.ui.tabs import LABEL_FONT, VALUE_FONT
from peppersign.utils import safe_unicode


class StatusTab(object):
    def __init__(self, gui, tab):
        self.gui = gui
        self.ctrl = gui.ctrl
        self._build(tab)

    def _build(self, tab):
        gui, ctrl, config = self.gui, self.ctrl, self.gui.config
        value_font, label_font = VALUE_FONT, LABEL_FONT

        box_robot = tk.LabelFrame(tab, text="Robot", padx=10, pady=8)
        box_robot.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(box_robot, text="Connessione:", font=label_font).grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_connection = tk.Label(box_robot, textvariable=gui.var_connection, font=value_font)
        self.lbl_connection.grid(row=0, column=1, sticky="w", padx=12, pady=2)
        row_conn = tk.Frame(box_robot)
        row_conn.grid(row=0, column=2, sticky="w", padx=12)
        tk.Button(row_conn, text="Riconnetti ora", command=self.on_reconnect).pack(side="left", padx=3)
        self.btn_simulate_disconnect = tk.Button(row_conn, text="Simula disconnessione (demo)",
                                                 command=self.on_simulate_disconnect)
        self.btn_simulate_disconnect.pack(side="left", padx=3)

        rows = [
            ("Robot (IP:porta):", gui.var_robot),
            ("Modalità:", gui.var_mode),
            ("Vita autonoma:", gui.var_life),
            ("Volume:", gui.var_volume),
            ("Autonomia durante i gesti:", gui.var_autonomy),
        ]
        for row, (label, var) in enumerate(rows, 1):
            tk.Label(box_robot, text=label, font=label_font).grid(row=row, column=0, sticky="w", pady=2)
            tk.Label(box_robot, textvariable=var, font=value_font).grid(row=row, column=1, sticky="w", padx=12, pady=2)

        # Scelta del robot: demo/reale e indirizzo, senza modificare il file .env
        gui.var_target_mode = tk.StringVar(value="demo" if ctrl.fake_robot else "real")
        gui.var_target_ip = tk.StringVar(value=safe_unicode(ctrl.robot_ip))
        gui.var_target_port = tk.StringVar(value=safe_unicode(ctrl.robot_port))
        box_target = tk.LabelFrame(tab, text="Scegli robot", padx=10, pady=8)
        box_target.pack(fill="x", padx=10, pady=6)
        tk.Radiobutton(box_target, text="Robot reale (Pepper)", variable=gui.var_target_mode, value="real",
                       font=label_font).grid(row=0, column=0, sticky="w", padx=(0, 16))
        tk.Radiobutton(box_target, text="Demo (robot simulato)", variable=gui.var_target_mode, value="demo",
                       font=label_font).grid(row=0, column=1, columnspan=2, sticky="w")
        tk.Label(box_target, text="Indirizzo IP:", font=label_font).grid(row=1, column=0, sticky="w", pady=(6, 2))
        entry_ip = tk.Entry(box_target, textvariable=gui.var_target_ip, width=20, font=label_font)
        entry_ip.grid(row=1, column=1, sticky="w", pady=(6, 2))
        entry_ip.bind("<Return>", lambda event: self.on_apply_target())
        tk.Label(box_target, text="Porta:", font=label_font).grid(row=1, column=2, sticky="w", padx=(16, 4), pady=(6, 2))
        tk.Entry(box_target, textvariable=gui.var_target_port, width=7, font=label_font).grid(
            row=1, column=3, sticky="w", pady=(6, 2))
        tk.Button(box_target, text="Applica e connetti", command=self.on_apply_target).grid(
            row=1, column=4, sticky="w", padx=(16, 0), pady=(6, 2))
        tk.Label(box_target, text="Vale fino al riavvio del controller; i valori di partenza restano quelli del file .env.",
                 fg="grey30").grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

        box_webapp = tk.LabelFrame(tab, text="WebApp e comandi", padx=10, pady=8)
        box_webapp.pack(fill="x", padx=10, pady=6)
        tk.Label(box_webapp, text="WebApp:", font=label_font).grid(row=0, column=0, sticky="w", pady=2)
        tk.Label(box_webapp, textvariable=gui.var_webapp, font=value_font).grid(row=0, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_webapp, text="Ultimo comando:", font=label_font).grid(row=1, column=0, sticky="w", pady=2)
        tk.Label(box_webapp, textvariable=gui.var_last, font=value_font).grid(row=1, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_webapp, text="Ultimo errore:", font=label_font).grid(row=2, column=0, sticky="nw", pady=2)
        tk.Label(box_webapp, textvariable=gui.var_error, font=label_font, fg="red",
                 wraplength=900, justify="left").grid(row=2, column=1, sticky="w", padx=12, pady=2)

        box_conf = tk.LabelFrame(tab, text="Configurazione", padx=10, pady=8)
        box_conf.pack(fill="x", padx=10, pady=6)
        info = [
            ("URL WebApp:", safe_unicode(config["webapp"].get("base_url", ""))),
            ("Cartella gesti:", safe_unicode(config["paths"].get("gesture_dir", ""))),
        ]
        for row, (label, value) in enumerate(info):
            tk.Label(box_conf, text=label, font=label_font).grid(row=row, column=0, sticky="w", pady=2)
            tk.Label(box_conf, text=value, font=label_font).grid(row=row, column=1, sticky="w", padx=12, pady=2)
        tk.Label(box_conf, text="Gesti caricati:", font=label_font).grid(row=len(info), column=0, sticky="w", pady=2)
        tk.Label(box_conf, textvariable=gui.var_gesture_count, font=label_font).grid(
            row=len(info), column=1, sticky="w", padx=12, pady=2)

    # ------------------------------------------------------------- pulsanti

    def on_reconnect(self):
        self.gui.enqueue_log("[ROBOT] Riconnessione in corso...")
        self.ctrl.request_reconnect()

    def on_apply_target(self):
        gui = self.gui
        fake = gui.var_target_mode.get() == "demo"
        ip = gui.var_target_ip.get()
        port = gui.var_target_port.get()

        def run():
            ok, message = self.ctrl.configure_target(fake, ip, port)
            gui.enqueue_log("[ROBOT] %s" % safe_unicode(message))
            if not ok:
                self.ctrl.set_error(message)
        gui.run_async(run)

    def on_simulate_disconnect(self):
        ok, message = self.ctrl.simulate_disconnect(15)
        self.gui.enqueue_log("[DEMO] %s" % safe_unicode(message))

    # --------------------------------------------------------- aggiornamento

    def refresh(self):
        """Solo valori in cache del controller: nessuna chiamata al robot dal thread della finestra."""
        gui, ctrl = self.gui, self.ctrl
        gui.var_robot.set("%s:%d" % (ctrl.robot_ip, ctrl.robot_port))
        gui.var_mode.set("DEMO - robot simulato" if ctrl.fake_robot else "Robot reale")
        self.btn_simulate_disconnect.config(state="normal" if ctrl.fake_robot else "disabled")
        gui.var_gesture_count.set(str(len(gui.gesture_store.keys())))
        gui.var_autonomy.set(safe_unicode(gui.config.get("robot_defaults", {}).get("gesture_autonomy", "pause")))
        gui.var_webapp.set("OK" if ctrl.connected_to_webapp else "OFF")
        gui.var_life.set(ctrl.cached_life_state)
        gui.var_error.set(ctrl.last_error)
        volume = ctrl.cached_volume
        gui.var_volume.set("%d%%" % int(volume) if volume is not None else "N/A")

        state = ctrl.connection_state
        gui.var_connection.set(state)
        if ctrl.robot_connected:
            color = "dark green"
        elif state.startswith("CONNESSIONE"):
            color = "dark orange"
        else:
            color = "red"
        self.lbl_connection.config(fg=color)
        gui.log_panel.lbl_connection_bar.config(fg=color)

        last_cmd = ctrl.last_cmd
        if last_cmd and isinstance(last_cmd, dict):
            gui.var_last.set(str(last_cmd.get("action", "")))
        else:
            gui.var_last.set("")
