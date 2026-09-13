# -*- coding: utf-8 -*-
from __future__ import absolute_import

import datetime
import json
import os
import socket

from peppersign.compat import PY2, text_type


def safe_unicode(value):
    try:
        if value is None:
            return u""
        if isinstance(value, text_type):
            return value
        if PY2:
            return value.decode("utf-8", "ignore")
        return str(value)
    except Exception:
        try:
            return text_type(value)
        except Exception:
            return u""


def normalize_gesture_id(value):
    return safe_unicode(value).strip().lower()


def clamp(value, lo, hi):
    try:
        if value < lo:
            return lo
        if value > hi:
            return hi
        return value
    except Exception:
        return value


def ensure_dir(path):
    try:
        if path and not os.path.exists(path):
            os.makedirs(path)
    except Exception:
        pass


def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def tcp_check(ip, port, timeout=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        sock.close()
        return True
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return False


def read_json(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    return json.loads(raw)


def write_json(path, data):
    with open(path, "wb") as handle:
        handle.write(json.dumps(data, indent=2))
