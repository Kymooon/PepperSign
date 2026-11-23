# -*- coding: utf-8 -*-
"""
Finestra di controllo di Controll (Tkinter).

PepperGUI e' la facciata: crea la finestra, monta le quattro schede e il log,
esegue il ciclo di aggiornamento (_tick). Il lavoro e' nelle parti in ui/:

- ui.tabs.status_tab     scheda 1, stato e scelta del robot
- ui.tabs.commands_tab   scheda 2, voce, gesti, volume
- ui.tabs.recording_tab  scheda 3, registrazione dei segni (dati in ui.sequence)
- ui.tabs.safety_tab     scheda 4, temperature, ostacoli, protezioni
- ui.log_panel           barra di stato e log
- ui.dispatcher          thread separati e ritorno nel thread della finestra
- ui.actions             comandi semplici (tabella)

I metodi on_* e gli attributi usati da main.py, dai test e da pose_dialog
restano disponibili qui con gli stessi nomi.
"""
from __future__ import absolute_import

from peppersign.compat import tk, tkFileDialog, tkMessageBox, ttk  # noqa: F401 (usati dai test)
from peppersign.ui.actions import install_actions
from peppersign.ui.dispatcher import UiDispatcher
from peppersign.ui.log_panel import LogPanel
from peppersign.ui.sequence import (HEAD_COMPONENT_JOINTS, LEFT_ARM_COMPONENT_JOINTS,  # noqa: F401
                                    LEFT_TO_RIGHT_ARM_MIRROR, RIGHT_ARM_COMPONENT_JOINTS,
                                    RIGHT_TO_LEFT_ARM_MIRROR)
from peppersign.ui.tabs.commands_tab import CommandsTab
from peppersign.ui.tabs.recording_tab import RecordingTab
from peppersign.ui.tabs.safety_tab import SafetyTab
from peppersign.ui.tabs.status_tab import StatusTab
from peppersign.utils import safe_unicode

TAB_TITLES = [
    "1) Stato robot",
    "2) Comandi",
    "3) Registrazione segni",
    "4) Sicurezza e motori",
]
DEMO_TITLE_SUFFIX = "  [DEMO - robot simulato]"
TICK_MS = 500


class PepperGUI(object):
    def __init__(self, controller, config, gesture_store):
        self.ctrl = controller
        self.config = config
        self.gesture_store = gesture_store

        self.root = tk.Tk()
        self.root.title(config["ui"]["window_title"])
        self.root.geometry(config["ui"]["window_size"])

        self.dispatcher = UiDispatcher(lambda message: self.enqueue_log(message))
        self._pose_dialog = None
        self._base_title = None
        self._shown_title = None

        # Variabili condivise tra le schede e la barra di stato
        self.var_robot = tk.StringVar()
        self.var_webapp = tk.StringVar()
        self.var_life = tk.StringVar()
        self.var_last = tk.StringVar()
        self.var_error = tk.StringVar()
        self.var_volume = tk.StringVar(value="N/A")
        self.var_mode = tk.StringVar()
        self.var_gesture_count = tk.StringVar()
        self.var_autonomy = tk.StringVar()
        self.var_connection = tk.StringVar(value="NON CONNESSO")
        self.var_say_text = tk.StringVar()
        keys = gesture_store.keys()
        self.var_gesture = tk.StringVar(value=keys[0] if keys else "")

        self._build()
        self._tick()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ thread

    def enqueue_log(self, message):
        """Riga di log, da qualunque thread."""
        self.dispatcher.log(message)

    def run_async(self, fn, *args):
        """fn(*args) in un thread separato (chiamate al robot)."""
        self.dispatcher.run_async(fn, *args)

    _run_async = run_async

    def run_then(self, work, apply_in_ui):
        """work() in un thread separato, apply_in_ui(risultato) nel thread della finestra."""
        self.dispatcher.run_then(work, apply_in_ui)

    # ------------------------------------------------------------------ layout

    def _build(self):
        paned = tk.PanedWindow(self.root, orient="vertical", sashrelief="raised", sashwidth=6)
        paned.pack(fill="both", expand=True, padx=8, pady=6)

        top = tk.Frame(paned)
        paned.add(top, minsize=300)
        bottom = tk.Frame(paned)
        paned.add(bottom, minsize=100)

        tab_status, tab_commands, tab_recording, tab_safety = self._create_tabs(top, TAB_TITLES)
        self.status = StatusTab(self, tab_status)
        self.commands = CommandsTab(self, tab_commands)
        self.recording = RecordingTab(self, tab_recording)
        self.safety = SafetyTab(self, tab_safety)
        self.log_panel = LogPanel(self, bottom)

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

    # ------------------------------------------- stato della sequenza (facciata)

    @property
    def frames(self):
        return self.recording.model.frames

    @frames.setter
    def frames(self, value):
        self.recording.model.frames = value

    @property
    def capture_joints(self):
        return self.recording.model.joints

    @capture_joints.setter
    def capture_joints(self, value):
        self.recording.model.joints = list(value)

    @property
    def list_frames(self):
        return self.recording.list_frames

    @property
    def txt_log(self):
        return self.log_panel.txt_log

    # ------------------------------------------------------------ aggiornamento

    def _tick(self):
        self.dispatcher.drain(self.log_panel.append)
        for refresh in (self._update_title, self.status.refresh, self.safety.refresh, self.recording.refresh):
            try:
                refresh()
            except Exception:
                pass
        self.root.after(TICK_MS, self._tick)

    def _update_title(self):
        if self._base_title is None:
            self._base_title = safe_unicode(self.config.get("ui", {}).get("window_title", "PepperSign")).replace(
                DEMO_TITLE_SUFFIX, "")
        title = self._base_title + (DEMO_TITLE_SUFFIX if self.ctrl.fake_robot else "")
        if title != self._shown_title:
            self._shown_title = title
            try:
                self.root.title(title)
            except Exception:
                pass

    # ----------------------------------------------------------- finestre e uscita

    def on_open_pose_dialog(self):
        """Finestra per creare un frame da punto del corpo + orientamento della mano (servizio Process)."""
        dialog = self._pose_dialog
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


# --------------------------------------------------------------------------
# Pulsanti delle schede: stessi nomi di prima, delegati alla scheda che li gestisce
# --------------------------------------------------------------------------

_DELEGATES = {
    "status": ["on_reconnect", "on_apply_target", "on_simulate_disconnect"],
    "commands": ["on_say", "on_say_animated", "on_gesture", "on_wakeup", "on_rest", "on_reload_gestures"],
    "safety": ["on_set_protection", "on_restore_protections", "on_refresh_protections",
               "on_reset_safety_counts", "on_toggle_demo_obstacle"],
    "recording": [
        "on_prepare_recording", "on_dump_pose", "on_new_composite_frame",
        "on_update_left_in_selected_frame", "on_update_right_in_selected_frame", "on_update_head_in_selected_frame",
        "on_frame_select", "on_edit_joint_changed", "on_toggle_frame_no_collision",
        "on_apply_selected_dt", "on_apply_selected_angle",
        "on_nudge_selected_angle_minus", "on_nudge_selected_angle_plus",
        "on_mirror_left_to_right", "on_mirror_right_to_left", "on_validate_selected_frame",
        "on_go_to_frame", "on_soft_on", "on_soft_off",
        "on_move_frame_up", "on_move_frame_down", "on_remove_frame", "on_copy_selected_frame",
        "on_clear_frames", "on_apply_dt_all",
        "on_test_frames", "on_save_sequence", "on_load_sequence",
        # nomi interni di prima, usati dai test
        ("_get_selected_frame_index", "selected_frame_index"),
        ("_select_frame_index", "select"),
        ("_refresh_frames_listbox", "refresh_list"),
        ("_load_selected_frame_to_editor", "load_selected_to_editor"),
    ],
}


def _make_delegate(part, method):
    def delegate(self, *args, **kwargs):
        return getattr(getattr(self, part), method)(*args, **kwargs)
    delegate.__name__ = method
    delegate.__doc__ = "Vedi %s.%s" % (part, method)
    return delegate


def _install_delegates(cls):
    for part, names in _DELEGATES.items():
        for name in names:
            name, method = name if isinstance(name, tuple) else (name, name)
            setattr(cls, name, _make_delegate(part, method))


_install_delegates(PepperGUI)
install_actions(PepperGUI)
