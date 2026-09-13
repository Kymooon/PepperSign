# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from peppersign.utils import ensure_dir, normalize_gesture_id, now_stamp, read_json, safe_unicode, write_json

DEFAULT_JOINTS = [
    "HeadYaw", "HeadPitch",
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

ARM_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

HEAD_JOINTS = ["HeadYaw", "HeadPitch"]


class GestureStore(object):
    def __init__(self, gesture_dir, log_cb=None):
        self.gesture_dir = gesture_dir
        self.log_cb = log_cb
        self.gestures = {}

    def log(self, message):
        if self.log_cb:
            try:
                self.log_cb(message)
                return
            except Exception:
                pass
        print message

    def keys(self):
        return sorted(self.gestures.keys())

    def get(self, gesture_id):
        return self.gestures.get(normalize_gesture_id(gesture_id))

    def clear(self):
        self.gestures = {}

    def reload(self):
        self.clear()
        return self.load_from_dir(self.gesture_dir)

    def load_from_dir(self, directory):
        ensure_dir(directory)
        loaded = 0
        for filename in sorted(os.listdir(directory)):
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(directory, filename)
            try:
                payload = read_json(path)
                key = self._derive_key(filename, payload)
                if not key:
                    self.log("[GESTURES] Skip senza chiave: %s" % path)
                    continue
                self.gestures[key] = payload
                loaded += 1
            except Exception as exc:
                self.log("[GESTURES] Errore caricamento %s: %s" % (path, str(exc)))
        self.log("[GESTURES] Caricate %d gesture da %s" % (loaded, directory))
        return loaded

    def _derive_key(self, filename, payload):
        explicit = payload.get("gesture_id") or payload.get("name") or os.path.splitext(filename)[0]
        return normalize_gesture_id(explicit)

    def build_default_sequence_path(self, base_name):
        ensure_dir(self.gesture_dir)
        return os.path.join(
            self.gesture_dir,
            "%s_sequence_%s.json" % (normalize_gesture_id(base_name or "gesto") or "gesto", now_stamp())
        )

    def build_default_ready_path(self, base_name):
        ensure_dir(self.gesture_dir)
        return os.path.join(
            self.gesture_dir,
            "%s_ready_%s.json" % (normalize_gesture_id(base_name or "gesto") or "gesto", now_stamp())
        )

    def save_frames_sequence(self, path, name, joints, frames):
        data = {
            "name": safe_unicode(name),
            "gesture_id": normalize_gesture_id(name),
            "format": "frames_v1",
            "joints": joints,
            "frames": frames,
            "created_at": now_stamp(),
        }
        write_json(path, data)

    def export_ready_gesture(self, path, name, joints, times_by_joint, angles_by_joint):
        data = {
            "name": safe_unicode(name),
            "gesture_id": normalize_gesture_id(name),
            "format": "ready_v1",
            "joints": joints,
            "times": times_by_joint,
            "angles": angles_by_joint,
            "created_at": now_stamp(),
        }
        write_json(path, data)
