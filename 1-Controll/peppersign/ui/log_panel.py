# -*- coding: utf-8 -*-
"""Parte bassa della finestra: barra di stato (sempre visibile) e log."""
from __future__ import absolute_import

from peppersign.compat import tk

BAR_FONT = ("TkDefaultFont", 10, "bold")


class LogPanel(object):
    def __init__(self, gui, parent):
        # Barra di stato sempre visibile (sopra il log, in tutte le schede)
        bar = tk.Frame(parent)
        bar.pack(fill="x", pady=(2, 2))
        tk.Label(bar, text="Robot:").pack(side="left")
        self.lbl_connection_bar = tk.Label(bar, textvariable=gui.var_connection, font=BAR_FONT)
        self.lbl_connection_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="WebApp:").pack(side="left")
        tk.Label(bar, textvariable=gui.var_webapp, font=BAR_FONT).pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Motori:").pack(side="left")
        gui.var_temp_bar = tk.StringVar(value="-")
        self.lbl_temp_bar = tk.Label(bar, textvariable=gui.var_temp_bar, font=BAR_FONT)
        self.lbl_temp_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Ostacoli:").pack(side="left")
        gui.var_obst_bar = tk.StringVar(value="-")
        self.lbl_obst_bar = tk.Label(bar, textvariable=gui.var_obst_bar, font=BAR_FONT)
        self.lbl_obst_bar.pack(side="left", padx=(4, 20))
        tk.Label(bar, text="Log:").pack(side="left", padx=(20, 0))

        log_scroll = tk.Scrollbar(parent, orient="vertical")
        self.txt_log = tk.Text(parent, height=10, wrap="word", yscrollcommand=log_scroll.set)
        log_scroll.config(command=self.txt_log.yview)
        log_scroll.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)
        self.txt_log.insert("end", "Pannello avviato.\n")
        self.txt_log.config(state="disabled")

    def append(self, message):
        try:
            if isinstance(message, unicode):
                message = message.encode("utf-8")
        except Exception:
            pass
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", str(message) + "\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")
