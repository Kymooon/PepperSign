# -*- coding: utf-8 -*-
"""
Lavoro lento fuori dal thread della finestra, risultato applicato nel thread della finestra.

Tkinter e la sequenza dei frame vanno toccati solo dal thread della finestra.
Le chiamate al robot invece possono durare secondi e vanno in un thread
separato. Il thread separato non modifica nulla: mette nella coda della finestra
la funzione da eseguire con il risultato, e la finestra la esegue al giro
successivo di _tick, nello stesso ordine dei messaggi di log.

La coda e' la stessa del log: una stringa e' una riga di log, una funzione e'
lavoro da fare nel thread della finestra.
"""
from __future__ import absolute_import

import threading

from peppersign.compat import queue


class UiDispatcher(object):
    def __init__(self, log_cb):
        self.queue = queue.Queue()
        self._log_cb = log_cb          # funzione per gli errori (riga di log)

    def log(self, message):
        """Riga di log, da qualunque thread."""
        try:
            self.queue.put_nowait(message)
        except Exception:
            pass

    def call_in_ui(self, fn, *args):
        """Esegue fn(*args) nel thread della finestra, al prossimo giro di drain()."""
        self.queue.put_nowait(lambda: fn(*args))

    def run_async(self, fn, *args):
        """Esegue fn(*args) in un thread separato; un'eccezione finisce nel log."""
        def runner():
            try:
                fn(*args)
            except Exception as exc:
                self._log_cb("[GUI] Errore: %s" % str(exc))
        thread = threading.Thread(target=runner)
        thread.daemon = True
        thread.start()

    def run_then(self, work, apply_in_ui):
        """work() in un thread separato, poi apply_in_ui(risultato) nel thread della finestra."""
        def job():
            result = work()
            self.call_in_ui(apply_in_ui, result)
        self.run_async(job)

    def drain(self, append_log):
        """Da chiamare nel thread della finestra: scrive il log ed esegue il lavoro in coda."""
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                return
            if callable(item):
                try:
                    item()
                except Exception as exc:
                    append_log("[GUI] Errore: %s" % str(exc))
            else:
                try:
                    append_log(item)
                except Exception:
                    pass
