# -*- coding: utf-8 -*-
"""
Finestra "Frame da coordinate (beta)" della scheda Registrazione segni.

Si sceglie un punto del corpo di Pepper (mento, petto, fronte...), uno
spostamento in cm, la direzione del palmo e delle dita e l'apertura della mano;
il servizio Process (/retarget/pose, cinematica inversa sul modello URDF di
Pepper) calcola gli angoli del braccio e la finestra li aggiunge alla sequenza
come un normale frame, modificabile come quelli registrati con Dump Pose.

Il calcolo avviene nel container Process (Python 3 + numpy); qui si fa solo
la richiesta HTTP, in un thread separato per non bloccare la finestra.
"""
from __future__ import absolute_import

import threading

from peppersign.compat import queue, tk, ttk
from peppersign.http_utils import http_get_json, http_post_json
from peppersign.utils import safe_unicode

FREE = "(libero)"
SUGGESTED = "(suggerito)"
DEFAULT_DIRECTIONS = ["avanti", "indietro", "su", "giu", "dentro", "fuori",
                      "avanti+su", "avanti+giu", "avanti+dentro", "avanti+fuori",
                      "su+dentro", "su+fuori", "giu+dentro", "indietro+su"]
ARM_SUFFIXES = ["ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw", "Hand"]


def _degrees(value):
    return float(value) * 57.29577951308232


class PoseFromCoordinatesDialog(object):
    def __init__(self, gui):
        self.gui = gui
        self.ctrl = gui.ctrl
        process_cfg = gui.config.get("process", {})
        self.base_url = safe_unicode(process_cfg.get("url", "http://127.0.0.1:5000")).rstrip("/")
        self.timeout = float(process_cfg.get("timeout", 20))
        self.results = queue.Queue()
        self.landmarks = []
        self.last_result = None
        self.busy = False

        self.win = tk.Toplevel(gui.root)
        self.win.title("Frame da coordinate (beta)")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self.var_side = tk.StringVar(value="R")
        self.var_mirror = tk.IntVar(value=0)
        self.var_landmark = tk.StringVar()
        self.var_forward = tk.StringVar(value="0")
        self.var_up = tk.StringVar(value="0")
        self.var_out = tk.StringVar(value="0")
        self.var_palm = tk.StringVar(value=SUGGESTED)
        self.var_fingers = tk.StringVar(value=SUGGESTED)
        self.var_hand = tk.DoubleVar(value=0.6)
        self.var_keep_hand = tk.IntVar(value=1)
        self.var_dt = tk.StringVar(value="1.0")
        self.var_status = tk.StringVar(value="Carico i punti del corpo dal servizio Process...")

        self._build()
        self._poll()
        self._request_async("landmarks", self._fetch_landmarks)

    # ------------------------------------------------------------------ layout

    def _choice(self, parent, var, values, width):
        if ttk:
            widget = ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly")
        else:
            widget = tk.OptionMenu(parent, var, *(values or [""]))
            widget.config(width=width)
        return widget

    def _set_choices(self, widget, var, values):
        if ttk and hasattr(widget, "configure") and widget.__class__.__name__ == "Combobox":
            widget.configure(values=values)
            return
        try:
            menu = widget["menu"]
            menu.delete(0, "end")
            for value in values:
                menu.add_command(label=value, command=lambda v=value: var.set(v))
        except Exception:
            pass

    def _build(self):
        pad = {"padx": 6, "pady": 4}
        frm = tk.Frame(self.win)
        frm.pack(fill="both", expand=True, padx=10, pady=8)

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Braccio del robot:").pack(side="left")
        tk.Radiobutton(row, text="Destro", variable=self.var_side, value="R").pack(side="left", padx=4)
        tk.Radiobutton(row, text="Sinistro", variable=self.var_side, value="L").pack(side="left", padx=4)
        tk.Checkbutton(row, text="Copia speculare sull'altro braccio", variable=self.var_mirror).pack(side="left", padx=16)

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Punto del corpo:").pack(side="left")
        self.cmb_landmark = self._choice(row, self.var_landmark, [], 44)
        self.cmb_landmark.pack(side="left", padx=6)

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Spostamento (cm):").pack(side="left")
        for label, var in (("avanti", self.var_forward), ("su", self.var_up), ("verso l'esterno", self.var_out)):
            tk.Label(row, text=label).pack(side="left", padx=(10, 2))
            tk.Spinbox(row, from_=-30, to=30, increment=1, width=5, textvariable=var).pack(side="left")

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        directions = [SUGGESTED, FREE] + DEFAULT_DIRECTIONS
        tk.Label(row, text="Palmo verso:").pack(side="left")
        self.cmb_palm = self._choice(row, self.var_palm, directions, 14)
        self.cmb_palm.pack(side="left", padx=6)
        tk.Label(row, text="Dita verso:").pack(side="left", padx=(16, 0))
        self.cmb_fingers = self._choice(row, self.var_fingers, directions, 14)
        self.cmb_fingers.pack(side="left", padx=6)
        tk.Label(row, text="(dal punto di vista del robot; dentro = verso il centro del corpo)",
                 fg="grey30").pack(side="left", padx=8)

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Label(row, text="Apertura mano:").pack(side="left")
        tk.Scale(row, from_=0.0, to=1.0, resolution=0.05, orient="horizontal", length=160,
                 variable=self.var_hand).pack(side="left", padx=6)
        tk.Checkbutton(row, text="lascia come nel frame di partenza", variable=self.var_keep_hand).pack(side="left")
        tk.Label(row, text="dt (s):").pack(side="left", padx=(20, 2))
        tk.Entry(row, textvariable=self.var_dt, width=6).pack(side="left")

        self.lbl_base = tk.Label(frm, text="", fg="grey30", anchor="w", justify="left")
        self.lbl_base.pack(fill="x", **pad)

        row = tk.Frame(frm)
        row.pack(fill="x", **pad)
        tk.Button(row, text="Calcola", width=12, command=self.on_compute).pack(side="left", padx=3)
        tk.Button(row, text="Prova sul robot", width=14, command=self.on_try).pack(side="left", padx=3)
        tk.Button(row, text="Aggiungi frame", width=14, command=self.on_add).pack(side="left", padx=3)
        tk.Button(row, text="Chiudi", width=10, command=self.close).pack(side="right", padx=3)

        tk.Label(frm, textvariable=self.var_status, anchor="w", justify="left", wraplength=760).pack(fill="x", **pad)
        self.txt_result = tk.Text(frm, height=9, width=96, wrap="word")
        self.txt_result.pack(fill="both", expand=True, **pad)
        self.txt_result.config(state="disabled")
        self._update_base_label()

    # ------------------------------------------------------------- utilita'

    def _show(self, text):
        self.txt_result.config(state="normal")
        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("end", text)
        self.txt_result.config(state="disabled")

    def _base_frame_index(self):
        index = self.gui._get_selected_frame_index()
        if index is None and self.gui.frames:
            index = len(self.gui.frames) - 1
        return index

    def _base_angles(self):
        """Angoli {giunto: valore} del frame di partenza (selezionato o ultimo), o None."""
        index = self._base_frame_index()
        if index is None:
            return None
        frame = self.gui.frames[index]
        return dict(zip(self.gui.capture_joints, frame.get("angles", [])))

    def _update_base_label(self):
        index = self._base_frame_index()
        if index is None:
            text = "Partenza: posa di riposo (nessun frame nella sequenza). Il nuovo frame va in coda."
        elif self.gui._get_selected_frame_index() is not None:
            text = "Partenza: frame %d selezionato. Il nuovo frame viene inserito subito dopo." % (index + 1)
        else:
            text = "Partenza: ultimo frame (%d). Il nuovo frame va in coda." % (index + 1)
        self.lbl_base.config(text=text)

    def _landmark_id(self):
        label = self.var_landmark.get()
        for item in self.landmarks:
            if item.get("label") == label:
                return item
        return None

    def _direction(self, value, suggested):
        value = safe_unicode(value).strip()
        if value == SUGGESTED:
            return suggested
        if value in (FREE, ""):
            return None
        return value

    def _payload(self):
        landmark = self._landmark_id()
        if landmark is None:
            raise ValueError("Scegli un punto del corpo")
        try:
            offset = {"avanti": float(self.var_forward.get()), "su": float(self.var_up.get()),
                      "esterno": float(self.var_out.get())}
            dt = float(self.var_dt.get())
        except ValueError:
            raise ValueError("Spostamenti e dt devono essere numeri")
        if dt <= 0:
            raise ValueError("dt deve essere maggiore di 0")
        payload = {
            "side": self.var_side.get(),
            "landmark": landmark["id"],
            "offset_cm": offset,
            "palm": self._direction(self.var_palm.get(), landmark.get("palm")),
            "fingers": self._direction(self.var_fingers.get(), landmark.get("fingers")),
            "hand": None if self.var_keep_hand.get() else float(self.var_hand.get()),
            "mirror": bool(self.var_mirror.get()),
            "dt": dt,
        }
        base = self._base_angles()
        if base:
            payload["base"] = base
        return payload

    # ------------------------------------------------------- richieste HTTP

    def _request_async(self, kind, fn, *args):
        if self.busy:
            return
        self.busy = True

        def runner():
            try:
                self.results.put((kind, True, fn(*args)))
            except Exception as exc:
                self.results.put((kind, False, exc))
        thread = threading.Thread(target=runner)
        thread.daemon = True
        thread.start()

    def _fetch_landmarks(self):
        return http_get_json(self.base_url + "/retarget/landmarks", timeout=self.timeout)

    def _compute(self, payload):
        return http_post_json(self.base_url + "/retarget/pose", payload, timeout=self.timeout)

    def _poll(self):
        try:
            while True:
                kind, ok, value = self.results.get_nowait()
                self.busy = False
                self._handle_result(kind, ok, value)
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self._update_base_label()
            self.win.after(150, self._poll)
        except Exception:
            pass

    def _handle_result(self, kind, ok, value):
        if not ok:
            self.var_status.set("Servizio Process non raggiungibile (%s): %s. Controlla che il container "
                                "'process' sia avviato." % (self.base_url, safe_unicode(value)))
            return
        if kind == "landmarks":
            self.landmarks = value.get("landmarks", [])
            labels = [item.get("label", item.get("id")) for item in self.landmarks]
            directions = [SUGGESTED, FREE] + list(value.get("directions") or DEFAULT_DIRECTIONS)
            self._set_choices(self.cmb_landmark, self.var_landmark, labels)
            self._set_choices(self.cmb_palm, self.var_palm, directions)
            self._set_choices(self.cmb_fingers, self.var_fingers, directions)
            if labels and not self.var_landmark.get():
                self.var_landmark.set(labels[0])
            self.var_status.set("Pronto: %d punti del corpo. Scegli e premi Calcola." % len(labels))
            return
        if not value.get("ok"):
            self.var_status.set("Calcolo non riuscito: %s" % safe_unicode(value.get("error", "?")))
            return
        self.last_result = value
        value["offset_cm"] = getattr(self, "_last_offset", {})
        self._show(self._describe(value))
        action = kind.split(":", 1)[1] if ":" in kind else ""
        if action == "try":
            self._try_on_robot(value)
        elif action == "add":
            self._add_frame(value)
        else:
            self.var_status.set("Calcolato. Puoi provarlo sul robot o aggiungerlo alla sequenza.")

    def _describe(self, result):
        side = self.var_side.get()
        angles = result.get("angles", {})
        lines = []
        point = result.get("point")
        if point:
            lines.append("Centro della mano richiesto (torso, m): x %.3f  y %.3f  z %.3f" % tuple(point))
        parts = []
        if result.get("error_position_cm") is not None:
            parts.append("posizione %.1f cm" % result["error_position_cm"])
        if result.get("error_palm_deg") is not None:
            parts.append("palmo %.0f gradi" % result["error_palm_deg"])
        if result.get("error_fingers_deg") is not None:
            parts.append("dita %.0f gradi" % result["error_fingers_deg"])
        if parts:
            lines.append("Scarto dalla richiesta: " + ", ".join(parts))
        values = []
        for suffix in ARM_SUFFIXES:
            value = float(angles.get(side + suffix, 0.0))
            if suffix == "Hand":
                values.append("%s %.0f%%" % (suffix, 100 * value))
            else:
                values.append("%s %.0f gradi" % (suffix, _degrees(value)))
        lines.append("Braccio %s: %s" % ("destro" if side == "R" else "sinistro", ", ".join(values)))
        for warning in result.get("warnings", []):
            lines.append("AVVISO: " + safe_unicode(warning))
        if not result.get("warnings"):
            lines.append("Nessun avviso: posa raggiungibile.")
        return "\n".join(lines)

    # -------------------------------------------------------------- azioni

    def _start(self, action):
        try:
            payload = self._payload()
        except ValueError as exc:
            self.var_status.set(safe_unicode(exc))
            return
        if self.busy:
            self.var_status.set("Attendi: calcolo in corso...")
            return
        self.var_status.set("Calcolo in corso...")
        self._last_offset = payload["offset_cm"]
        self._request_async("pose:" + action, self._compute, payload)

    def on_compute(self):
        self._start("")

    def on_try(self):
        self._start("try")

    def on_add(self):
        self._start("add")

    def _frame_for_gui(self, result):
        """Frame nel formato della GUI (giunti della sequenza corrente)."""
        angles = result.get("angles", {})
        base = self._base_angles() or {}
        values = []
        for joint in self.gui.capture_joints:
            if joint in angles:
                values.append(float(angles[joint]))
            elif joint in base:
                values.append(float(base[joint]))
            else:
                raise ValueError("Giunto %s non presente nel risultato" % joint)
        frame = {"angles": values, "dt": float(result.get("frame", {}).get("dt", self.var_dt.get())),
                 "source": "coordinate_beta",
                 "coordinate": {"side": self.var_side.get(), "landmark": (self._landmark_id() or {}).get("id"),
                                "offset_cm": dict((k, v) for k, v in (result.get("offset_cm") or {}).items()),
                                "palm": self.var_palm.get(), "fingers": self.var_fingers.get(),
                                "mirror": bool(self.var_mirror.get())}}
        if result.get("warnings"):
            frame["warning"] = "; ".join(safe_unicode(w) for w in result["warnings"])
        return frame

    def _try_on_robot(self, result):
        try:
            frame = self._frame_for_gui(result)
        except ValueError as exc:
            self.var_status.set(safe_unicode(exc))
            return
        frame["dt"] = max(float(frame["dt"]), 1.0)      # prova lenta, dalla posa attuale
        joints = list(self.gui.capture_joints)
        self.var_status.set("Movimento del robot verso la posa calcolata...")

        def run():
            ok, message = self.ctrl.run_frames_gesture(joints, [frame])
            self.gui.enqueue_log("[COORD] Prova sul robot -> %s" % safe_unicode(message))
        self.gui._run_async(run)

    def _add_frame(self, result):
        try:
            frame = self._frame_for_gui(result)
        except ValueError as exc:
            self.var_status.set(safe_unicode(exc))
            return
        selected = self.gui._get_selected_frame_index()
        if selected is None:
            self.gui.frames.append(frame)
            index = len(self.gui.frames) - 1
        else:
            index = selected + 1
            self.gui.frames.insert(index, frame)
        self.gui.enqueue_log("[COORD] Frame %d aggiunto da coordinate (%s)%s" % (
            index + 1, (self._landmark_id() or {}).get("label", "?"),
            " - " + frame["warning"] if frame.get("warning") else ""))
        self.gui.enqueue_log("[UI] aggiorno lista frame")
        self.gui.enqueue_log("[UI] seleziona frame:%d" % index)
        self.var_status.set("Frame %d aggiunto alla sequenza." % (index + 1))

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        self.gui._pose_dialog = None
