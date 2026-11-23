# -*- coding: utf-8 -*-
"""
Scheda 3: registrazione dei segni.

Solo widget e pulsanti: i dati e le operazioni sulla sequenza sono in
ui.sequence.SequenceModel. Le letture della posa dal robot avvengono in un thread
separato; il risultato viene applicato alla sequenza nel thread della finestra
(gui.run_then), cosi' la sequenza non e' mai modificata da due thread insieme.
"""
from __future__ import absolute_import

import copy
import os

from peppersign.compat import tk, tkFileDialog, ttk
from peppersign.gesture_store import DEFAULT_JOINTS
from peppersign.robot.collision import ARM_COLLISION_CHAINS
from peppersign.robot.interpolation import NO_ARM_COLLISION_KEY
from peppersign.ui.sequence import (DEFAULT_DT, HEAD_COMPONENT_JOINTS, LEFT_ARM_COMPONENT_JOINTS,
                                    LEFT_TO_RIGHT_ARM_MIRROR, RIGHT_ARM_COMPONENT_JOINTS,
                                    RIGHT_TO_LEFT_ARM_MIRROR, AngleCountMismatch, InvalidSequenceFile,
                                    MissingJoints, SequenceChanged, SequenceModel, UnsupportedFormat,
                                    clamp_dt, with_hands)
from peppersign.utils import ensure_dir, now_stamp, safe_unicode

JSON_FILETYPES = [("JSON", "*.json"), ("All files", "*.*")]
SOFT_GROUP_NAMES = {"both": "entrambe", "left": "SX", "right": "DX"}


class RecordingTab(object):
    def __init__(self, gui, tab):
        self.gui = gui
        self.ctrl = gui.ctrl
        self.model = SequenceModel(with_hands(DEFAULT_JOINTS), self.ctrl.validate_frame_pose)
        self._create_vars()
        self._build(tab)

    def _create_vars(self):
        # Le variabili Tk restano attributi di PepperGUI: sono lo stato visibile della finestra.
        gui = self.gui
        gui.var_frame_dt = tk.StringVar(value="0.6")
        gui.var_capture_name = tk.StringVar(value="GESTO_" + now_stamp())
        # Editor manuale: ritoccare dt e singoli angoli dopo la cattura, senza modificare il JSON a mano
        gui.var_edit_dt = tk.StringVar()
        gui.var_edit_joint = tk.StringVar()
        gui.var_edit_angle = tk.StringVar()
        gui.var_edit_step = tk.StringVar(value="0.03")
        # Frame senza anti-collisione tra le braccia (mani sovrapposte) e catena interessata
        gui.var_frame_no_collision = tk.IntVar()
        gui.var_collision_chain = tk.StringVar(value="Arms")
        if self.model.joints:
            gui.var_edit_joint.set(self.model.joints[0])
        # Riprendere da un frame: posa del frame, poi braccia "morbide" (si muovono a mano ma non cadono)
        gui.var_soft_after = tk.IntVar(value=1)
        gui.var_soft_group = tk.StringVar(value="both")
        gui.var_soft_stiffness = tk.StringVar(value="0.40")
        gui.var_soft_state = tk.StringVar(value="Morbido: OFF")

    # ------------------------------------------------------------------ layout

    def _build(self, tab):
        gui = self.gui
        box_cap = tk.Frame(tab)
        box_cap.pack(fill="both", expand=True, padx=6, pady=6)

        row1 = tk.Frame(box_cap)
        row1.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(row1, text="Nome gesto:").pack(side="left")
        tk.Entry(row1, textvariable=gui.var_capture_name, width=28).pack(side="left", padx=6)
        tk.Label(row1, text="dt frame (s):").pack(side="left", padx=(10, 0))
        tk.Entry(row1, textvariable=gui.var_frame_dt, width=6).pack(side="left", padx=6)
        tk.Button(row1, text="Applica dt a tutti", command=self.on_apply_dt_all).pack(side="left", padx=6)

        def buttons(parent, specs):
            # width None = larghezza del testo (righe con etichette lunghe)
            for text, width, command, padx in specs:
                options = {"width": width} if width else {}
                tk.Button(parent, text=text, command=command, **options).pack(side="left", padx=padx)

        row2 = tk.Frame(box_cap)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        buttons(row2, [
            ("Prepara registrazione", None, self.on_prepare_recording, 3),
            ("Sblocca braccia", None, gui.on_free_arms, 3),
            ("Blocca braccia", None, gui.on_hold_arms, 3),
            ("Sblocca testa", None, gui.on_free_head, 12),
            ("Blocca testa", None, gui.on_hold_head, 3),
            ("Cattura posa", None, self.on_dump_pose, 12),
        ])

        row2c = tk.Frame(box_cap)
        row2c.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(row2c, text="Braccio singolo:").pack(side="left", padx=(0, 8))
        buttons(row2c, [
            ("Sblocca SX", 10, gui.on_free_left_arm, 3),
            ("Blocca SX", 10, gui.on_hold_left_arm, 3),
            ("Sblocca DX", 10, gui.on_free_right_arm, (12, 3)),
            ("Blocca DX", 10, gui.on_hold_right_arm, 3),
            ("Solo SX", 10, gui.on_move_only_left_arm, (12, 3)),
            ("Solo DX", 10, gui.on_move_only_right_arm, 3),
        ])

        row2b = tk.Frame(box_cap)
        row2b.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(row2b, text="Mani:").pack(side="left", padx=(0, 8))
        buttons(row2b, [
            ("Apri SX", 10, gui.on_open_left_hand, 3),
            ("Chiudi SX", 10, gui.on_close_left_hand, 3),
            ("Apri DX", 10, gui.on_open_right_hand, (12, 3)),
            ("Chiudi DX", 10, gui.on_close_right_hand, 3),
            ("Apri entrambe", 12, gui.on_open_both_hands, (12, 3)),
            ("Chiudi entrambe", 13, gui.on_close_both_hands, 3),
        ])

        row2d = tk.Frame(box_cap)
        row2d.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(row2d, text="Vai al frame selezionato", width=20, command=self.on_go_to_frame).pack(side="left", padx=(0, 4))
        tk.Checkbutton(row2d, text="poi braccia morbide", variable=gui.var_soft_after).pack(side="left", padx=(0, 12))
        tk.Label(row2d, text="Braccia morbide:").pack(side="left")
        for label, value in (("entrambe", "both"), ("SX", "left"), ("DX", "right")):
            tk.Radiobutton(row2d, text=label, variable=gui.var_soft_group, value=value).pack(side="left")
        tk.Label(row2d, text="rigidità").pack(side="left", padx=(8, 2))
        tk.Spinbox(row2d, from_=0.10, to=0.80, increment=0.05, width=5, format="%.2f",
                   textvariable=gui.var_soft_stiffness).pack(side="left")
        tk.Button(row2d, text="Attiva morbido", command=self.on_soft_on).pack(side="left", padx=(8, 3))
        tk.Button(row2d, text="Disattiva morbido", command=self.on_soft_off).pack(side="left", padx=3)
        tk.Label(row2d, textvariable=gui.var_soft_state, fg="dark green").pack(side="left", padx=8)

        row3 = tk.Frame(box_cap)
        row3.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left_list = tk.Frame(row3)
        left_list.pack(side="left", fill="both", expand=True)
        tk.Label(left_list, text="Frame catturati (in ordine):").pack(anchor="w")
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
        tk.Button(row_move, text="Sposta giù", width=8, command=self.on_move_frame_down).pack(side="left", padx=(2, 0))
        tk.Button(box_frames, text="Rimuovi selezionato", width=18, command=self.on_remove_frame).pack(padx=4, pady=2)
        tk.Button(box_frames, text="Copia frame", width=18, command=self.on_copy_selected_frame).pack(padx=4, pady=2)
        tk.Button(box_frames, text="Svuota lista", width=18, command=self.on_clear_frames).pack(padx=4, pady=(2, 4))

        box_file = tk.LabelFrame(col_a, text="File e prova")
        box_file.pack(fill="x", pady=(6, 3))
        tk.Button(box_file, text="Prova gesto", width=18, command=self.on_test_frames).pack(padx=4, pady=(4, 2))
        tk.Button(box_file, text="Salva sequenza", width=18, command=self.on_save_sequence).pack(padx=4, pady=2)
        tk.Button(box_file, text="Carica sequenza", width=18, command=self.on_load_sequence).pack(padx=4, pady=(2, 4))

        # Colonna B: modifica dei frame
        col_b = tk.Frame(row3)
        col_b.pack(side="left", fill="y", padx=(10, 0))

        box_edit = tk.LabelFrame(col_b, text="Modifica frame")
        box_edit.pack(fill="x", pady=(0, 3))
        grid = {"sticky": "w", "padx": 4, "pady": 2}

        tk.Label(box_edit, text="dt (s):").grid(row=0, column=0, **grid)
        tk.Entry(box_edit, textvariable=gui.var_edit_dt, width=7).grid(row=0, column=1, **grid)
        tk.Button(box_edit, text="Applica", width=8, command=self.on_apply_selected_dt).grid(row=0, column=2, **grid)

        tk.Label(box_edit, text="Giunto:").grid(row=1, column=0, **grid)
        self.opt_edit_joint = None
        if ttk:
            self.combo_edit_joint = ttk.Combobox(box_edit, textvariable=gui.var_edit_joint, values=self.model.joints,
                                                 width=16, state="readonly")
            self.combo_edit_joint.grid(row=1, column=1, columnspan=2, **grid)
            self.combo_edit_joint.bind("<<ComboboxSelected>>", self.on_edit_joint_changed)
        else:
            self.combo_edit_joint = None
            self.opt_edit_joint = tk.OptionMenu(box_edit, gui.var_edit_joint, *self.model.joints)
            self.opt_edit_joint.config(width=14)
            self.opt_edit_joint.grid(row=1, column=1, columnspan=2, **grid)

        tk.Label(box_edit, text="Angolo:").grid(row=2, column=0, **grid)
        tk.Entry(box_edit, textvariable=gui.var_edit_angle, width=10).grid(row=2, column=1, **grid)
        tk.Button(box_edit, text="Applica", width=8, command=self.on_apply_selected_angle).grid(row=2, column=2, **grid)

        tk.Label(box_edit, text="Passo:").grid(row=3, column=0, **grid)
        tk.Entry(box_edit, textvariable=gui.var_edit_step, width=7).grid(row=3, column=1, **grid)

        row_nudge = tk.Frame(box_edit)
        row_nudge.grid(row=4, column=0, columnspan=3, **grid)
        tk.Button(row_nudge, text="− passo", width=8, command=self.on_nudge_selected_angle_minus).pack(side="left", padx=(0, 4))
        tk.Button(row_nudge, text="+ passo", width=8, command=self.on_nudge_selected_angle_plus).pack(side="left", padx=4)

        tk.Button(box_edit, text="Valida frame", width=18, command=self.on_validate_selected_frame).grid(
            row=5, column=0, columnspan=3, sticky="w", padx=4, pady=(4, 4))

        tk.Checkbutton(box_edit, text="Senza anti-collisione braccia", variable=gui.var_frame_no_collision,
                       command=self.on_toggle_frame_no_collision).grid(
            row=6, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 0))
        tk.Label(box_edit, text="Catena:").grid(row=7, column=0, sticky="w", padx=4, pady=(0, 4))
        opt_chain = tk.OptionMenu(box_edit, gui.var_collision_chain, *ARM_COLLISION_CHAINS)
        opt_chain.config(width=6)
        opt_chain.grid(row=7, column=1, columnspan=2, sticky="w", padx=4, pady=(0, 4))

        # Colonna C: specchio e frame composito
        col_c = tk.Frame(row3)
        col_c.pack(side="left", fill="y", padx=(10, 0))

        box_mirror = tk.LabelFrame(col_c, text="Specchia frame")
        box_mirror.pack(fill="x", pady=(0, 3))
        tk.Button(box_mirror, text="SX -> DX", width=8, command=self.on_mirror_left_to_right).pack(side="left", padx=4, pady=4)
        tk.Button(box_mirror, text="DX -> SX", width=8, command=self.on_mirror_right_to_left).pack(side="left", padx=4, pady=4)

        box_composite = tk.LabelFrame(col_c, text="Frame composito")
        box_composite.pack(fill="x", pady=(6, 3))
        tk.Button(box_composite, text="Nuovo composito", width=18, command=self.on_new_composite_frame).pack(padx=4, pady=(4, 2))
        tk.Button(box_composite, text="Aggiorna SX", width=18, command=self.on_update_left_in_selected_frame).pack(padx=4, pady=2)
        tk.Button(box_composite, text="Aggiorna DX", width=18, command=self.on_update_right_in_selected_frame).pack(padx=4, pady=2)
        tk.Button(box_composite, text="Aggiorna testa", width=18, command=self.on_update_head_in_selected_frame).pack(padx=4, pady=(2, 4))

        box_coord = tk.LabelFrame(col_c, text="Frame da coordinate (beta)")
        box_coord.pack(fill="x", pady=(6, 3))
        tk.Button(box_coord, text="Apri...", width=18, command=gui.on_open_pose_dialog).pack(padx=4, pady=4)

    # ------------------------------------------------- interfaccia pubblica
    # (usata da pose_dialog e dalla facciata PepperGUI)

    @property
    def frames(self):
        return self.model.frames

    @property
    def joints(self):
        return self.model.joints

    def selected_frame_index(self):
        try:
            selected = self.list_frames.curselection()
            if not selected:
                return None
            index = int(selected[0])
            if self.model.is_index(index):
                return index
        except Exception:
            pass
        return None

    def base_frame_index(self):
        """Frame di partenza per un nuovo frame: quello selezionato, altrimenti l'ultimo (None se vuota)."""
        index = self.selected_frame_index()
        if index is None and self.model.frames:
            index = len(self.model.frames) - 1
        return index

    def base_angles(self):
        """Angoli {giunto: valore} del frame di partenza, o None."""
        index = self.base_frame_index()
        if index is None:
            return None
        return dict(zip(self.model.joints, self.model.frames[index].get("angles", [])))

    def insert_frame(self, frame):
        """Inserisce un frame dopo quello selezionato (in coda se nessuno) e lo seleziona."""
        index = self.model.insert_after(self.selected_frame_index(), frame)
        self.refresh_list()
        self.select(index)
        self.load_selected_to_editor()
        return index

    def select(self, index):
        try:
            self.list_frames.selection_clear(0, "end")
            self.list_frames.selection_set(index)
            self.list_frames.activate(index)
            self.list_frames.see(index)
        except Exception:
            pass

    def refresh_list(self):
        self.list_frames.delete(0, "end")
        for index in range(len(self.model.frames)):
            self.list_frames.insert("end", self.model.describe(index))

    def refresh(self):
        """Stato delle braccia morbide (valore in cache del controller)."""
        soft = self.ctrl.soft_hold_state()
        if soft:
            self.gui.var_soft_state.set("Morbido: ON (%s, %.2f)" % (SOFT_GROUP_NAMES.get(soft[0], soft[0]), soft[1]))
        else:
            self.gui.var_soft_state.set("Morbido: OFF")

    # ---------------------------------------------------------------- utilita'

    def _log(self, message):
        self.gui.enqueue_log(message)

    def _report_check(self, tag, check, failure, warn_prefix="WARN: "):
        """Scrive nel log l'esito della validazione di una posa. Ritorna check.ok."""
        if not check.ok:
            self._log("%s %s" % (tag, failure))
            for err in check.errors:
                self._log("%s ERRORE: %s" % (tag, safe_unicode(err)))
            return False
        for warn in check.warnings:
            self._log("%s %s%s" % (tag, warn_prefix, safe_unicode(warn)))
        return True

    def _log_mismatch(self, tag, exc):
        self._log("%s Frame %d non valido (%d angoli invece di %d): ricatturalo con Cattura posa"
                  % (tag, exc.index + 1, exc.count, exc.expected))

    def _log_problems(self, tag, problems):
        for problem in problems[:10]:
            self._log("%s ERRORE: %s" % (tag, safe_unicode(problem)))
        if len(problems) > 10:
            self._log("%s ... e altri %d problemi" % (tag, len(problems) - 10))

    def _reselect(self, index):
        """Dopo refresh_list: riseleziona la riga (senza spostare la vista)."""
        try:
            self.list_frames.selection_set(index)
        except Exception:
            pass

    def _get_dt_value(self):
        try:
            return clamp_dt(float(self.gui.var_frame_dt.get().strip()))
        except Exception:
            return DEFAULT_DT

    def _get_edit_step(self):
        try:
            step = float(self.gui.var_edit_step.get().strip())
        except Exception:
            step = 0.03
        if step <= 0:
            step = 0.03
        return min(step, 1.0)

    def _soft_stiffness_value(self):
        try:
            value = float(self.gui.var_soft_stiffness.get())
        except Exception:
            self._log("[MORBIDO] Stiffness non valida, uso 0.40")
            value = 0.40
        value = max(0.10, min(value, 0.80))
        self.gui.var_soft_stiffness.set("%.2f" % value)
        return value

    # ------------------------------------------------------- editor del frame

    def refresh_joint_selector(self):
        joints = list(self.model.joints or [])
        if not joints:
            return
        var = self.gui.var_edit_joint
        if var.get() not in joints:
            var.set(joints[0])
        try:
            if self.combo_edit_joint is not None:
                self.combo_edit_joint["values"] = joints
        except Exception:
            pass
        try:
            if self.opt_edit_joint is not None:
                menu = self.opt_edit_joint["menu"]
                menu.delete(0, "end")
                for joint in joints:
                    menu.add_command(label=joint, command=tk._setit(var, joint, self.on_edit_joint_changed))
        except Exception:
            pass

    def load_selected_to_editor(self):
        index = self.selected_frame_index()
        if index is None:
            return
        gui = self.gui
        frame = self.model.frames[index]
        gui.var_frame_no_collision.set(1 if frame.get(NO_ARM_COLLISION_KEY) else 0)
        dt = frame.get("dt", DEFAULT_DT)
        try:
            gui.var_edit_dt.set("%.3f" % float(dt))
        except Exception:
            gui.var_edit_dt.set(safe_unicode(dt))
        self.refresh_joint_selector()
        self._update_angle_entry()

    def _selected_joint_index(self):
        return self.model.joint_index(safe_unicode(self.gui.var_edit_joint.get()).strip())

    def _update_angle_entry(self):
        frame_index = self.selected_frame_index()
        joint_index = self._selected_joint_index()
        if frame_index is None or joint_index is None:
            return
        angles = self.model.frames[frame_index].get("angles", [])
        if joint_index >= len(angles):
            self.gui.var_edit_angle.set("")
            return
        try:
            self.gui.var_edit_angle.set("%.6f" % float(angles[joint_index]))
        except Exception:
            self.gui.var_edit_angle.set(safe_unicode(angles[joint_index]))

    def on_frame_select(self, event=None):
        self.load_selected_to_editor()

    def on_edit_joint_changed(self, event=None):
        self._update_angle_entry()

    def on_toggle_frame_no_collision(self):
        gui = self.gui
        index = self.selected_frame_index()
        if index is None:
            gui.var_frame_no_collision.set(0)
            self._log("[TUNING] Seleziona prima un frame.")
            return
        enabled = bool(gui.var_frame_no_collision.get())
        self.model.set_no_collision(index, enabled)
        self.refresh_list()
        self._reselect(index)
        windows = self.model.collision_windows()
        self._log("[SICUREZZA] Frame %d %s. Anti-collisione braccia (%s) spenta in: %s" % (
            index + 1, "senza anti-collisione" if enabled else "con anti-collisione",
            gui.var_collision_chain.get(),
            ", ".join("%.1f-%.1f s" % (a, b) for a, b in windows) if windows else "nessun intervallo"))

    def on_apply_selected_dt(self):
        index = self.selected_frame_index()
        if index is None:
            self._log("[TUNING] Seleziona prima un frame.")
            return
        try:
            dt = float(self.gui.var_edit_dt.get().strip())
        except Exception:
            self._log("[TUNING] dt non valido.")
            return
        dt = self.model.set_dt(index, dt)
        self.gui.var_frame_dt.set("%.3f" % dt)
        self.refresh_list()
        self._reselect(index)
        self.load_selected_to_editor()
        self._log("[TUNING] Frame %d: dt impostato a %.3f" % (index + 1, dt))

    def on_apply_selected_angle(self):
        index = self.selected_frame_index()
        joint_index = self._selected_joint_index()
        if index is None or joint_index is None:
            self._log("[TUNING] Seleziona frame e joint.")
            return
        try:
            value = float(self.gui.var_edit_angle.get().strip())
        except Exception:
            self._log("[TUNING] angolo non valido.")
            return
        try:
            check = self.model.set_angle(index, joint_index, value)
        except AngleCountMismatch as exc:
            self._log_mismatch("[TUNING]", exc)
            return
        if not self._report_check("[TUNING]", check, "VALORE NON APPLICATO: frame non valido"):
            return
        self._update_angle_entry()
        self._log("[TUNING] Frame %d: %s = %.6f" % (index + 1, safe_unicode(self.model.joints[joint_index]), value))

    def _nudge_selected_angle(self, sign):
        var = self.gui.var_edit_angle
        try:
            current = float(var.get().strip())
        except Exception:
            self._update_angle_entry()
            try:
                current = float(var.get().strip())
            except Exception:
                self._log("[TUNING] nessun angolo valido da modificare.")
                return
        var.set("%.6f" % (current + sign * self._get_edit_step()))
        self.on_apply_selected_angle()

    def on_nudge_selected_angle_minus(self):
        self._nudge_selected_angle(-1.0)

    def on_nudge_selected_angle_plus(self):
        self._nudge_selected_angle(1.0)

    def _mirror_selected(self, pairs, label):
        index = self.selected_frame_index()
        if index is None:
            self._log("[SPECCHIO] Seleziona prima un frame.")
            return
        try:
            check = self.model.mirror(index, pairs)
        except AngleCountMismatch as exc:
            self._log_mismatch("[SPECCHIO]", exc)
            return
        except MissingJoints as exc:
            self._log("[SPECCHIO] Joint mancante: %s o %s" % tuple(safe_unicode(j) for j in exc.joints))
            return
        except Exception as exc:
            self._log("[SPECCHIO] Errore durante lo specchio: %s" % str(exc))
            return
        if not self._report_check("[SPECCHIO]", check, "Frame NON modificato: posa specchiata non valida"):
            return
        self.refresh_list()
        self._reselect(index)
        self.load_selected_to_editor()
        self._log("[SPECCHIO] Frame %d aggiornato: %s" % (index + 1, label))

    def on_mirror_left_to_right(self):
        self._mirror_selected(LEFT_TO_RIGHT_ARM_MIRROR, "SX copiato/specchiato su DX")

    def on_mirror_right_to_left(self):
        self._mirror_selected(RIGHT_TO_LEFT_ARM_MIRROR, "DX copiato/specchiato su SX")

    def on_validate_selected_frame(self):
        index = self.selected_frame_index()
        if index is None:
            self._log("[VALIDAZIONE] Seleziona prima un frame.")
            return
        check = self.model.check_pose(self.model.frames[index].get("angles", []))
        if not check.ok:
            self._log("[VALIDAZIONE] Frame %d NON valido" % (index + 1))
            for err in check.errors:
                self._log("[VALIDAZIONE] ERRORE: %s" % safe_unicode(err))
        elif check.warnings:
            self._log("[VALIDAZIONE] Frame %d valido con warning" % (index + 1))
            for warn in check.warnings:
                self._log("[VALIDAZIONE] WARN: %s" % safe_unicode(warn))
        else:
            self._log("[VALIDAZIONE] Frame %d valido" % (index + 1))

    # ----------------------------------------- nuovi frame dalla posa del robot
    # La posa si legge in un thread separato; la sequenza si modifica nel thread
    # della finestra (gui.run_then), con i controlli sul frame ancora presente.

    def on_dump_pose(self):
        dt = self._get_dt_value()
        joints = list(self.model.joints)

        def apply(result):
            ok, angles, message = result
            if not ok:
                self._log("[DUMP] FAIL: %s" % safe_unicode(message))
                return
            try:
                check, index = self.model.append_pose(angles, dt, joints=joints)
            except SequenceChanged:
                self._log("[DUMP] Frame NON salvato: la sequenza e' cambiata durante la lettura della posa")
                return
            if not self._report_check("[VALIDAZIONE]", check, "FRAME NON SALVATO"):
                return
            self._log("[DUMP] Frame %d catturato (dt=%.2f) - joints=%d" % (index + 1, dt, len(joints)))
            try:
                preview = ", ".join(["%.3f" % float(value) for value in angles[:4]])
                self._log("[DUMP] Angoli preview: %s ..." % preview)
            except Exception:
                pass
            self.refresh_list()

        self.gui.run_then(lambda: self.ctrl.get_pose(joints), apply)

    def on_new_composite_frame(self):
        dt = self._get_dt_value()
        joints = list(self.model.joints)

        def apply(result):
            ok, angles, message = result
            if not ok:
                self._log("[COMPOSITO] Nuovo frame fallito: %s" % safe_unicode(message))
                return
            try:
                check, index = self.model.append_pose(angles, dt, joints=joints, composite=True)
            except SequenceChanged:
                self._log("[COMPOSITO] Frame NON creato: la sequenza e' cambiata durante la lettura della posa")
                return
            if not self._report_check("[COMPOSITO]", check, "FRAME NON CREATO: posa iniziale non valida"):
                return
            self._log("[COMPOSITO] Frame %d creato da posa attuale (dt=%.2f)" % (index + 1, dt))
            self.refresh_list()
            self.select(index)
            self.load_selected_to_editor()

        self.gui.run_then(lambda: self.ctrl.get_pose(joints), apply)

    def _update_selected_component(self, component_joints, label):
        index = self.selected_frame_index()
        if index is None:
            self._log("[COMPOSITO] Seleziona prima un frame.")
            return
        missing = self.model.missing_joints(component_joints)
        if missing:
            self._log("[COMPOSITO] Joint mancanti nel frame: %s" % ", ".join([safe_unicode(x) for x in missing]))
            return
        frame = self.model.frames[index]          # il frame, non la sua posizione: puo' cambiare
        joints_to_read = list(component_joints)

        def apply(result):
            ok, values, message = result
            if not ok:
                self._log("[COMPOSITO] Aggiornamento %s fallito: %s" % (safe_unicode(label), safe_unicode(message)))
                return
            current = self.model.index_of(frame)
            if current is None:
                self._log("[COMPOSITO] %s NON applicato: il frame %d non e' piu' nella sequenza"
                          % (safe_unicode(label), index + 1))
                return
            try:
                check = self.model.apply_component(current, joints_to_read, values)
            except AngleCountMismatch as exc:
                self._log_mismatch("[COMPOSITO]", exc)
                return
            except Exception as exc:
                self._log("[COMPOSITO] Errore mapping %s: %s" % (safe_unicode(label), str(exc)))
                return
            if not self._report_check("[COMPOSITO]", check,
                                      "%s NON applicato: frame risultante non valido" % safe_unicode(label)):
                return
            self._log("[COMPOSITO] Frame %d aggiornato: %s" % (current + 1, safe_unicode(label)))
            self.refresh_list()
            self.select(current)
            self.load_selected_to_editor()

        self.gui.run_then(lambda: self.ctrl.get_pose(joints_to_read), apply)

    def on_update_left_in_selected_frame(self):
        self._update_selected_component(LEFT_ARM_COMPONENT_JOINTS, "braccio SX")

    def on_update_right_in_selected_frame(self):
        self._update_selected_component(RIGHT_ARM_COMPONENT_JOINTS, "braccio DX")

    def on_update_head_in_selected_frame(self):
        self._update_selected_component(HEAD_COMPONENT_JOINTS, "testa")

    def on_prepare_recording(self):
        def run():
            ok, message = self.ctrl.prepare_gesture_recording()
            self._log("[REC] %s%s" % ("" if ok else "FAIL: ", safe_unicode(message)))
        self.gui.run_async(run)

    # ------------------------------------- riprendere da un frame, braccia morbide

    def on_go_to_frame(self):
        gui = self.gui
        index = self.selected_frame_index()
        if index is None:
            self._log("[POSA] Seleziona prima un frame nella lista.")
            return
        joints = list(self.model.joints)
        angles = list(self.model.frames[index].get("angles", []))
        if len(angles) != len(joints):
            self._log("[POSA] Il frame %d ha %d angoli, attesi %d: non posso usarlo." % (index + 1, len(angles), len(joints)))
            return
        soft_after = bool(gui.var_soft_after.get())
        group = gui.var_soft_group.get()
        stiffness = self._soft_stiffness_value()

        def run():
            ok, message = self.ctrl.go_to_pose(joints, angles)
            self._log("[POSA] Frame %d -> %s" % (index + 1, safe_unicode(message)))
            if ok and soft_after:
                ok_soft, message_soft = self.ctrl.start_soft_hold(group, stiffness)
                self._log("[MORBIDO] %s" % safe_unicode(message_soft))
        self._log("[POSA] Movimento verso il frame %d..." % (index + 1))
        gui.run_async(run)

    def on_soft_on(self):
        group = self.gui.var_soft_group.get()
        stiffness = self._soft_stiffness_value()

        def run():
            ok, message = self.ctrl.start_soft_hold(group, stiffness)
            self._log("[MORBIDO] %s" % safe_unicode(message))
        self.gui.run_async(run)

    def on_soft_off(self):
        def run():
            ok, message = self.ctrl.stop_soft_hold(1.0)
            self._log("[MORBIDO] %s" % safe_unicode(message))
        self.gui.run_async(run)

    # ------------------------------------------------------- ordine dei frame

    def _move_selected(self, delta):
        index = self.selected_frame_index()
        if index is None:
            self._log("[FRAME] Seleziona prima un frame da spostare.")
            return
        new_index = self.model.move(index, delta)
        if new_index is None:
            return
        self.refresh_list()
        self.select(new_index)
        self.load_selected_to_editor()
        self._log("[FRAME] Frame %d spostato in posizione %d" % (index + 1, new_index + 1))

    def on_move_frame_up(self):
        self._move_selected(-1)

    def on_move_frame_down(self):
        self._move_selected(1)

    def on_remove_frame(self):
        index = self.selected_frame_index()
        if self.model.remove(index):
            self._log("[FRAME] Rimosso frame %d" % (index + 1))
            self.refresh_list()

    def on_copy_selected_frame(self):
        """Duplica il frame selezionato in fondo alla sequenza (ripetere pose senza ricatturarle)."""
        index = self.selected_frame_index()
        if index is None:
            self._log("[FRAME] Seleziona prima un frame da copiare.")
            return
        check, new_index = self.model.copy_to_end(index)
        if not self._report_check("[FRAME]", check, "Copia NON creata: il frame di origine non e' valido",
                                  warn_prefix="WARN copia: "):
            return
        self.refresh_list()
        self.select(new_index)
        self.load_selected_to_editor()
        self._log("[FRAME] Copiato frame %d come nuovo frame %d" % (index + 1, new_index + 1))

    def on_clear_frames(self):
        self.model.clear()
        self.refresh_list()
        self.gui.var_edit_dt.set("")
        self.gui.var_edit_angle.set("")
        self._log("[FRAME] Lista dei frame svuotata")

    def on_apply_dt_all(self):
        dt = self._get_dt_value()
        self.model.set_all_dt(dt)
        self.refresh_list()
        self._log("[FRAME] dt applicato a tutti: %.2f" % dt)

    # ------------------------------------------------------------ prova e file

    def on_test_frames(self):
        joints = list(self.model.joints)
        frames_copy = copy.deepcopy(self.model.frames)     # il thread lavora su una copia
        chain = self.gui.var_collision_chain.get()

        def run():
            if not frames_copy:
                self._log("[TEST] Nessun frame da eseguire.")
                return
            ok, message = self.ctrl.run_frames_gesture(joints, frames_copy, collision_chain=chain)
            self._log("[TEST] %s" % safe_unicode(message))
        self.gui.run_async(run)

    def _ask_save_path(self, default_path):
        gesture_dir = self.gui.config["paths"]["gesture_dir"]
        ensure_dir(gesture_dir)
        return tkFileDialog.asksaveasfilename(
            initialdir=gesture_dir,
            initialfile=os.path.basename(default_path),
            defaultextension=".json",
            filetypes=JSON_FILETYPES,
        )

    def _gesture_name(self):
        return self.gui.var_capture_name.get().strip()

    def on_save_sequence(self):
        if self.model.frames:
            problems = self.model.problems()
            if problems:
                self._log_problems("[SAVE]", problems)
                self._log("[SAVE] Sequenza NON salvata: correggi i frame indicati")
                return
        path = self._ask_save_path(self.gui.gesture_store.build_default_sequence_path(self._gesture_name() or "GESTO"))
        if not path:
            return
        try:
            self.model.save(self.gui.gesture_store, path, self._gesture_name(), self.gui.var_collision_chain.get())
            self._log("[SAVE] Sequenza salvata: %s" % path)
        except Exception as exc:
            self._log("[SAVE] FAIL: %s" % str(exc))

    def on_load_sequence(self):
        gui = self.gui
        gesture_dir = gui.config["paths"]["gesture_dir"]
        ensure_dir(gesture_dir)
        path = tkFileDialog.askopenfilename(initialdir=gesture_dir, filetypes=JSON_FILETYPES)
        if not path:
            return
        try:
            data = self.model.load_file(path)
        except UnsupportedFormat:
            self._log("[LOAD] Formato non supportato.")
            return
        except InvalidSequenceFile as exc:
            # Rifiuto totale: la sequenza attuale resta com'e' (niente completamento con zeri)
            self._log("[LOAD] Sequenza NON caricata, il file non e' valido: %s" % path)
            self._log_problems("[LOAD]", exc.problems)
            return
        except Exception as exc:
            self._log("[LOAD] FAIL: %s" % str(exc))
            return
        gui.var_capture_name.set(data.get("name", "GESTO_" + now_stamp()))
        gui.var_collision_chain.set(safe_unicode(data.get("arm_collision_chain") or "Arms"))
        self.refresh_joint_selector()
        self.refresh_list()
        gui.var_edit_dt.set("")
        gui.var_edit_angle.set("")
        self._log("[LOAD] Sequenza caricata: %s (frames=%d)" % (path, len(self.model.frames)))
