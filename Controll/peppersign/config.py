# -*- coding: utf-8 -*-
from __future__ import absolute_import

import copy
import os

os.environ['TCL_LIBRARY'] = r'C:\Python27\tcl\tcl8.5'
os.environ['TK_LIBRARY'] = r'C:\Python27\tcl\tk8.5'

from peppersign.utils import ensure_dir, read_json


DEFAULT_CONFIG = {
    "robot": {
        "ip": "192.168.137.141",
        "port": 9559,
    },
    "webapp": {
        "base_url": "http://192.168.137.1:8080/PepperSign_Web_war_exploded",
        "next_path": "/api/pepper/next",
        "audio_upload_path": "/api/pepper/audio",
        "poll_timeout": 5,
        "poll_sleep_ok": 0.2,
        "poll_sleep_idle": 0.3,
        "poll_sleep_error": 1.0,
        "audio_upload_timeout": 60,
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
    },
}


def _deep_update(base, overrides):
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def build_runtime_config(config_path=None):
    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path:
        override = read_json(config_path)
        _deep_update(config, override)

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