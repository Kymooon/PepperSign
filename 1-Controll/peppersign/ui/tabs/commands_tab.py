# -*- coding: utf-8 -*-
"""Scheda 2: voce, wakeUp/rest, Autonomous Life, volume, esecuzione dei gesti salvati."""
from __future__ import absolute_import

from peppersign.compat import tk, ttk
from peppersign.utils import safe_unicode


class CommandsTab(object):
    def __init__(self, gui, tab):
        self.gui = gui
        self.ctrl = gui.ctrl
        self._build(tab)

    def _build(self, tab):
        gui = self.gui
        grid = tk.Frame(tab)
        grid.pack(fill="both", expand=True, padx=10, pady=10)

        box_tts = tk.LabelFrame(grid, text="Voce")
        box_tts.grid(row=0, column=0, sticky="nwe", padx=(0, 10), pady=6)
        tk.Entry(box_tts, textvariable=gui.var_say_text, width=30).pack(side="left", padx=8, pady=8)
        tk.Button(box_tts, text="Dì", width=6, command=self.on_say).pack(side="left", padx=6)
        tk.Button(box_tts, text="Dì con gesti", width=12, command=self.on_say_animated).pack(side="left", padx=6)

        box_util = tk.LabelFrame(grid, text="Robot")
        box_util.grid(row=1, column=0, sticky="nwe", padx=(0, 10), pady=6)
        row_power = tk.Frame(box_util)
        row_power.pack(fill="x", pady=(4, 0))
        tk.Button(row_power, text="Sveglia", width=10, command=self.on_wakeup).pack(side="left", padx=8, pady=4)
        tk.Button(row_power, text="Riposo", width=10, command=self.on_rest).pack(side="left", padx=6, pady=4)
        row_life = tk.Frame(box_util)
        row_life.pack(fill="x", pady=(0, 4))
        tk.Button(row_life, text="Attiva vita autonoma", width=19, command=gui.on_life_on).pack(side="left", padx=8, pady=4)
        tk.Button(row_life, text="Disattiva vita autonoma", width=21, command=gui.on_life_off).pack(side="left", padx=6, pady=4)

        box_volume = tk.LabelFrame(grid, text="Volume")
        box_volume.grid(row=0, column=1, sticky="nwe", pady=6)
        tk.Label(box_volume, text="Uscita:").pack(side="left", padx=(8, 4), pady=8)
        tk.Label(box_volume, textvariable=gui.var_volume, width=6).pack(side="left", padx=(0, 8), pady=8)
        tk.Button(box_volume, text="Volume −", width=9, command=gui.on_volume_down).pack(side="left", padx=6, pady=8)
        tk.Button(box_volume, text="Volume +", width=9, command=gui.on_volume_up).pack(side="left", padx=6, pady=8)

        box_map = tk.LabelFrame(grid, text="Esegui gesto")
        box_map.grid(row=1, column=1, sticky="nwe", pady=6)
        keys = gui.gesture_store.keys() or [""]
        if ttk:
            self.combo_gesture = ttk.Combobox(box_map, textvariable=gui.var_gesture, values=keys, width=26, state="readonly")
            self.combo_gesture.pack(side="left", padx=8, pady=8)
        else:
            self.combo_gesture = None
            opt = tk.OptionMenu(box_map, gui.var_gesture, *keys)
            opt.config(width=22)
            opt.pack(side="left", padx=8, pady=8)
        tk.Button(box_map, text="Avvia", width=8, command=self.on_gesture).pack(side="left", padx=6)
        tk.Button(box_map, text="Ricarica gesti", width=13, command=self.on_reload_gestures).pack(side="left", padx=6)

        # Spazio riservato ai controlli futuri (es. STOP di emergenza, testa, tablet)
        self.frm_commands_extra = tk.Frame(grid)
        self.frm_commands_extra.grid(row=2, column=0, columnspan=2, sticky="nwe", pady=6)

    def refresh_gesture_default(self):
        keys = self.gui.gesture_store.keys()
        self.gui.var_gesture.set(keys[0] if keys else "")

    # ------------------------------------------------------------- pulsanti

    def on_reload_gestures(self):
        gui = self.gui
        loaded = gui.gesture_store.reload()
        keys = gui.gesture_store.keys() or [""]
        if self.combo_gesture is not None:
            self.combo_gesture["values"] = keys
        self.refresh_gesture_default()
        gui.enqueue_log("[GESTURES] Ricaricate %d gesture" % loaded)

    def on_say(self):
        gui = self.gui
        text = gui.var_say_text.get()

        def run():
            ok, message = self.ctrl.say(text)
            if not ok:
                gui.enqueue_log("[CMD] SAY fallito: %s" % safe_unicode(message))
        gui.run_async(run)
        gui.enqueue_log("[CMD] SAY: %s" % safe_unicode(text))

    def on_say_animated(self):
        gui = self.gui
        text = gui.var_say_text.get()

        def run():
            ok, message = self.ctrl.say_animated(text)
            gui.enqueue_log("[CMD] SAY_ANIMATED: %s -> %s" % (safe_unicode(text), safe_unicode(message)))
        gui.run_async(run)

    def on_gesture(self):
        gui = self.gui
        gesture_id = gui.var_gesture.get()

        def run():
            ok, message = self.ctrl.play_gesture(gesture_id)
            gui.enqueue_log("[CMD] PLAY_GESTURE %s -> %s" % (safe_unicode(gesture_id), safe_unicode(message)))
        gui.run_async(run)

    def on_wakeup(self):
        gui = self.gui

        def run():
            ok, message = self.ctrl.wakeup()
            if not ok:
                gui.enqueue_log("[CMD] WAKEUP fallito: %s" % safe_unicode(message))
        gui.run_async(run)
        gui.enqueue_log("[CMD] WAKEUP")

    def on_rest(self):
        gui = self.gui

        def run():
            ok, message = self.ctrl.rest()
            if not ok:
                gui.enqueue_log("[CMD] REST fallito: %s" % safe_unicode(message))
        gui.run_async(run)
        gui.enqueue_log("[CMD] REST")
