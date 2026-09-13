import os
import sys
import time
import json
import queue
import re
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def fetch_health(url: str, timeout=0.6):
    """Ritorna (ok_bool, health_dict_or_None)."""
    try:
        with urlopen(url, timeout=timeout) as r:
            if not (200 <= r.status < 300):
                return False, None
            data = r.read().decode("utf-8", errors="ignore")
            try:
                return True, json.loads(data)
            except Exception:
                return True, None
    except (URLError, HTTPError, TimeoutError):
        return False, None
    except Exception:
        return False, None


# =============================
# SERVIZI: 1 processo + 3 interni
# =============================
SERVICES = [
    {
        "type": "process",
        "name": "PepperSign Backend (run.py)",
        "cmd": [sys.executable, os.path.join(BASE_DIR, "run.py")],
        "workdir": BASE_DIR,
        "health_url": "http://127.0.0.1:5000/health",
        "env": {
            # "FFMPEG_BIN": r"C:\ffmpeg\bin\ffmpeg.exe",
            "GPU_CONCURRENCY": "1",
            "PEPPERSIGN_PORT": "5000",
        },
        "autostart": True
    },
    {
        "type": "internal",
        "name": "DWpose (interno)",
        "depends_on": 0,                 # dipende dal backend
        "health_key": "dwpose_loaded",   # verde se True
    },
    {
        "type": "internal",
        "name": "Whisper ASR (interno)",
        "depends_on": 0,
        "health_key": "asr_engine",      # verde se != dummy
    },
    {
        "type": "internal",
        "name": "TRY (interno)",
        "depends_on": 0,
        "health_key": "try_sessions",    # verde se backend ok; mostra conteggio
    },
]


class ServiceState:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.log_queue = queue.Queue()
        self.reader_thread = None


class ControlPanel(tk.Tk):
    def __init__(self, services_cfg):
        super().__init__()
        self.title("PepperSign - Control Panel (Local)")
        self.geometry("1100x680")

        self.services = [ServiceState(c) for c in services_cfg]
        self.last_health_ok = False
        self.last_health_json = None

        self._build_ui()
        self.after(200, self._autostart)

        self._poll_status_loop()
        self._poll_logs_loop()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Servizi", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Stop ALL", command=self.stop_all).grid(row=0, column=1, sticky="e")

        mid = ttk.Frame(self, padding=(10, 0, 10, 10))
        mid.grid(row=1, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(1, weight=1)

        # tabella servizi
        self.services_frame = ttk.Frame(mid)
        self.services_frame.grid(row=0, column=0, sticky="ew")
        self._build_services_table()

        # log viewer
        log_card = ttk.Frame(mid)
        log_card.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)

        log_header = ttk.Frame(log_card)
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)

        ttk.Label(log_header, text="Terminale / Log", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_header, text="Auto-scroll", variable=self.autoscroll).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Button(log_header, text="Clear", command=self.clear_log).grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.log_text = tk.Text(log_card, wrap="none", height=20)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(log_card, orient="vertical", command=self.log_text.yview)
        yscroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=yscroll.set)

    def _build_services_table(self):
        header = ttk.Frame(self.services_frame)
        header.grid(row=0, column=0, sticky="ew")

        # colonne: nome | lamp | stato | azioni
        ttk.Label(header, text="Servizio", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=6, sticky="w")
        ttk.Label(header, text="Lucina", font=("Segoe UI", 10, "bold")).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(header, text="Stato", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, padx=6, sticky="w")
        ttk.Label(header, text="Azioni", font=("Segoe UI", 10, "bold")).grid(row=0, column=3, padx=6, sticky="w")

        body = ttk.Frame(self.services_frame)
        body.grid(row=1, column=0, sticky="ew")

        self.rows = []  # (canvas, lamp_id, status_lbl, btns_frame or None)

        for idx, svc in enumerate(self.services):
            row = ttk.Frame(body)
            row.grid(row=idx, column=0, sticky="ew", pady=4)
            row.columnconfigure(0, weight=1)

            ttk.Label(row, text=svc.cfg["name"]).grid(row=0, column=0, sticky="w", padx=6)

            c = tk.Canvas(row, width=22, height=22, highlightthickness=0)
            c.grid(row=0, column=1, padx=6)
            lamp = c.create_oval(4, 4, 18, 18, fill="#aa0000", outline="")

            status_lbl = ttk.Label(row, text="STOPPED")
            status_lbl.grid(row=0, column=2, sticky="w", padx=6)

            btns = None
            if svc.cfg["type"] == "process":
                btns = ttk.Frame(row)
                btns.grid(row=0, column=3, sticky="e", padx=6)
                ttk.Button(btns, text="Start", command=lambda i=idx: self.start_service(i)).grid(row=0, column=0, padx=4)
                ttk.Button(btns, text="Stop", command=lambda i=idx: self.stop_service(i)).grid(row=0, column=1, padx=4)
                ttk.Button(btns, text="Restart", command=lambda i=idx: self.restart_service(i)).grid(row=0, column=2, padx=4)
            else:
                ttk.Label(row, text="—").grid(row=0, column=3, sticky="e", padx=12)

            self.rows.append((c, lamp, status_lbl, btns))

    def _autostart(self):
        for i, svc in enumerate(self.services):
            if svc.cfg.get("type") == "process" and svc.cfg.get("autostart"):
                self.start_service(i)

    def log(self, line: str):
        self.log_text.insert("end", line + "\n")
        if self.autoscroll.get():
            self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    # ----------------------------
    # Process control (solo per servizi type=process)
    # ----------------------------
    def start_service(self, i: int):
        svc = self.services[i]
        if svc.cfg["type"] != "process":
            return

        if svc.proc and svc.proc.poll() is None:
            return

        env = os.environ.copy()
        env.update(svc.cfg.get("env", {}))

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            svc.proc = subprocess.Popen(
                svc.cfg["cmd"],
                cwd=svc.cfg.get("workdir", None),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=creationflags
            )

        except Exception as e:
            self.log(f"[GUI] ERRORE avvio {svc.cfg['name']}: {e}")
            return

        self.log(f"[GUI] START -> {svc.cfg['name']} (pid={svc.proc.pid})")

        def reader():
            try:
                for line in svc.proc.stdout:
                    clean = ANSI_RE.sub("", line.rstrip())
                    svc.log_queue.put(f"[{svc.cfg['name']}] {clean}")
            except Exception as e:
                svc.log_queue.put(f"[{svc.cfg['name']}] [log-reader error] {e}")

        svc.reader_thread = threading.Thread(target=reader, daemon=True)
        svc.reader_thread.start()

    def stop_service(self, i: int):
        svc = self.services[i]
        if svc.cfg["type"] != "process":
            return

        if not svc.proc or svc.proc.poll() is not None:
            return

        self.log(f"[GUI] STOP -> {svc.cfg['name']}")
        try:
            svc.proc.terminate()
        except Exception:
            pass

        for _ in range(20):
            if svc.proc.poll() is not None:
                break
            time.sleep(0.1)

        if svc.proc.poll() is None:
            self.log(f"[GUI] KILL -> {svc.cfg['name']}")
            try:
                svc.proc.kill()
            except Exception:
                pass

    def restart_service(self, i: int):
        self.stop_service(i)
        time.sleep(0.2)
        self.start_service(i)

    def stop_all(self):
        for i in range(len(self.services)):
            if self.services[i].cfg["type"] == "process":
                self.stop_service(i)

    # ----------------------------
    # Status refresh loops
    # ----------------------------
    def _poll_status_loop(self):
        # 1) aggiorna health del backend (indice 0)
        backend = self.services[0]
        backend_alive = bool(backend.proc and backend.proc.poll() is None)
        if backend_alive:
            ok, hjson = fetch_health(backend.cfg["health_url"], timeout=0.5)
            self.last_health_ok = ok
            self.last_health_json = hjson if ok else None
        else:
            self.last_health_ok = False
            self.last_health_json = None

        # 2) aggiorna riga backend (lamp + testo)
        c, lamp, lbl, _ = self.rows[0]
        if not backend_alive:
            c.itemconfig(lamp, fill="#aa0000")
            lbl.config(text="STOPPED")
        else:
            if self.last_health_ok:
                c.itemconfig(lamp, fill="#00aa00")
                lbl.config(text="RUNNING (healthy)")
            else:
                c.itemconfig(lamp, fill="#d4aa00")
                lbl.config(text="RUNNING (no health)")

        # 3) aggiorna servizi interni basati su /health
        for idx in range(1, len(self.services)):
            svc = self.services[idx].cfg
            c, lamp, lbl, _ = self.rows[idx]

            if not backend_alive:
                c.itemconfig(lamp, fill="#aa0000")
                lbl.config(text="OFF (backend stopped)")
                continue

            if not self.last_health_ok or not isinstance(self.last_health_json, dict):
                c.itemconfig(lamp, fill="#d4aa00")
                lbl.config(text="UNKNOWN (health n/a)")
                continue

            key = svc.get("health_key")
            val = self.last_health_json.get(key)

            if svc["name"].startswith("DWpose"):
                ok = bool(val)
                c.itemconfig(lamp, fill="#00aa00" if ok else "#d4aa00")
                lbl.config(text="LOADED" if ok else "NOT LOADED")

            elif svc["name"].startswith("Whisper"):
                # verde se engine != dummy
                engine = str(val or "")
                ok = engine and engine != "dummy"
                c.itemconfig(lamp, fill="#00aa00" if ok else "#d4aa00")
                lbl.config(text=f"ENGINE: {engine or 'unknown'}")

            elif svc["name"].startswith("TRY"):
                # sempre ok se health ok; mostra conteggio
                try:
                    n = int(val or 0)
                except Exception:
                    n = 0
                c.itemconfig(lamp, fill="#00aa00")
                lbl.config(text=f"READY (sessions={n})")

        # ogni 3 secondi
        self.after(3000, self._poll_status_loop)

    def _poll_logs_loop(self):
        for svc in self.services:
            if svc.cfg.get("type") == "process":
                while True:
                    try:
                        line = svc.log_queue.get_nowait()
                    except queue.Empty:
                        break
                    self.log(line)
        self.after(100, self._poll_logs_loop)

    def on_close(self):
        self.stop_all()
        self.destroy()


if __name__ == "__main__":
    app = ControlPanel(SERVICES)
    app.mainloop()
