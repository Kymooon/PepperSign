# -*- coding: utf-8 -*-
from __future__ import absolute_import

import copy
import os
import sys

# Solo su Windows con Python 2.7 installato in C:\Python27 serve indicare a
# Tkinter dove trovare Tcl/Tk. Su Linux/Docker non si tocca nulla.
if sys.platform.startswith("win"):
    _tcl_dir = os.environ.get("PEPPERSIGN_TCL_DIR", r"C:\Python27\tcl")
    if os.path.isdir(_tcl_dir):
        os.environ.setdefault("TCL_LIBRARY", os.path.join(_tcl_dir, "tcl8.5"))
        os.environ.setdefault("TK_LIBRARY", os.path.join(_tcl_dir, "tk8.5"))

from peppersign.utils import ensure_dir, read_json


DEFAULT_CONFIG = {
    "robot": {
        "ip": "127.0.0.1",
        "port": 9559,
    },
    "webapp": {
        "base_url": "http://127.0.0.1:8080/PepperSign",
        "next_path": "/api/pepper/next",
        "audio_upload_path": "/api/pepper/audio",
        "poll_timeout": 5,
        "poll_sleep_ok": 0.2,
        "poll_sleep_idle": 0.3,
        "poll_sleep_error": 1.0,
        "audio_upload_timeout": 60,
    },
    "process": {
        # Servizio Process (Python 3): usato per i "Frame da coordinate" (beta)
        "url": "http://127.0.0.1:5000",
        "timeout": 20,
    },
    "audio": {
        "remote_wav": "/tmp/rec_utente.wav",
        "rec_seconds": 4,
    },
    "paths": {
        "save_dir": os.path.join(os.path.expanduser("~"), "PepperSignGestures"),
        "gesture_dir": os.path.join(os.path.expanduser("~"), "PepperSignGestures"),
    },
    "ui": {
        "window_title": "PepperSign - Pannello Locale (Tkinter)",
        "window_size": "980x640",
        "rest_on_close": True,
    },
    "robot_defaults": {
        "tts_language": "Italian",
        "stop_basic_awareness_on_connect": True,
        "connect_wakeup": True,
        "animated_say_use_speaking_movement": True,
        "animated_say_mode": "contextual",
        "animated_say_fallback_to_tts": True,
        # Autonomia durante l'esecuzione dei gesti (vedi controller.py):
        #   "pause" = pausa selettiva dei movimenti autonomi delle braccia
        #   "off"   = pausa di tutti i movimenti autonomi (Autonomous Life resta nel suo stato)
        #   "none"  = nessun intervento
        "gesture_autonomy": "pause",
        # Attese (s) prima e dopo ogni gesto, con i movimenti autonomi in pausa:
        # prima = tempo perche' si fermino e le braccia si irrigidiscano,
        # dopo = posa finale tenuta prima di riattivarli
        "gesture_pre_delay": 0.8,
        "gesture_post_delay": 0.6,
    },
}


def fake_robot_enabled():
    """
    True se e' attiva la modalita' demo (PEPPERSIGN_FAKE_ROBOT=1):
    il controller usa un robot simulato (peppersign/fake_qi.py) invece di Pepper.
    """
    value = os.environ.get("PEPPERSIGN_FAKE_ROBOT", "")
    return value.strip().lower() in ("1", "true", "yes", "si", "on")


def _deep_update(base, overrides):
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


# Variabili d'ambiente (usate da Docker) -> chiave di configurazione.
# Hanno la precedenza sia sui default sia sul file JSON.
ENV_OVERRIDES = [
    ("PEPPERSIGN_ROBOT_IP", ("robot", "ip"), str),
    ("PEPPERSIGN_ROBOT_PORT", ("robot", "port"), int),
    ("PEPPERSIGN_WEBAPP_URL", ("webapp", "base_url"), str),
    ("PEPPERSIGN_GESTURE_DIR", ("paths", "gesture_dir"), str),
    ("PEPPERSIGN_SAVE_DIR", ("paths", "save_dir"), str),
    ("PEPPERSIGN_TTS_LANGUAGE", ("robot_defaults", "tts_language"), str),
    ("PEPPERSIGN_WINDOW_SIZE", ("ui", "window_size"), str),
    ("PEPPERSIGN_GESTURE_AUTONOMY", ("robot_defaults", "gesture_autonomy"), str),
    ("PEPPERSIGN_PROCESS_URL", ("process", "url"), str),
    ("PEPPERSIGN_GESTURE_PRE_DELAY", ("robot_defaults", "gesture_pre_delay"), float),
    ("PEPPERSIGN_GESTURE_POST_DELAY", ("robot_defaults", "gesture_post_delay"), float),
]


def _apply_env_overrides(config):
    for env_name, (section, key), cast in ENV_OVERRIDES:
        value = os.environ.get(env_name)
        if value is None or not value.strip():
            continue
        try:
            config[section][key] = cast(value.strip())
        except Exception:
            print "[CONFIG] Valore non valido per %s: %r" % (env_name, value)
    return config


def build_runtime_config(config_path=None):
    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path:
        override = read_json(config_path)
        _deep_update(config, override)

    _apply_env_overrides(config)

    # Se non indicata esplicitamente, la cartella di salvataggio segue quella dei gesti.
    if not os.environ.get("PEPPERSIGN_SAVE_DIR") and os.environ.get("PEPPERSIGN_GESTURE_DIR"):
        config["paths"]["save_dir"] = config["paths"]["gesture_dir"]

    base_url = config["webapp"]["base_url"].rstrip("/")
    next_path = config["webapp"]["next_path"]
    audio_upload_path = config["webapp"]["audio_upload_path"]

    if not next_path.startswith("/"):
        next_path = "/" + next_path
    if not audio_upload_path.startswith("/"):
        audio_upload_path = "/" + audio_upload_path

    config["webapp"]["next_url"] = base_url + next_path
    config["webapp"]["audio_upload_url"] = base_url + audio_upload_path

    ensure_dir(config["paths"]["save_dir"])
    ensure_dir(config["paths"]["gesture_dir"])

    return config