"""
Post-elaborazione delle traiettorie dei giunti e export nel formato frames_v1.

 1. riempimento dei buchi (interpolazione lineare; giunti mai stimati -> posa di riposo)
 2. smoothing Savitzky-Golay (solo numpy); finestra piu' corta per polso e mano
    (FAST_JOINTS), che hanno movimenti rapidi da non appiattire
 3. clamp ai limiti di Pepper
 4. riduzione a keyframe: algoritmo tipo Ramer-Douglas-Peucker sulle traiettorie
    (si aggiunge un keyframe dove l'interpolazione lineare tra i keyframe gia'
    scelti si discosta di piu' di `epsilon` radianti su almeno un giunto);
    eventuali keyframe obbligatori (es. i picchi della rotazione del polso)
    sono sempre inclusi
 5. dt dei keyframe dal tempo reale del video, diviso per il fattore di velocita'
    e allungato se un giunto supererebbe la velocita' massima consentita.
"""
import datetime
import json

import numpy as np

from . import pepper_kinematics as pk

# Giunti con movimenti rapidi: smoothing piu' leggero e velocita' massima piu' alta
FAST_JOINTS = ("LWristYaw", "RWristYaw", "LHand", "RHand")
DEFAULT_FAST_WINDOW = 5
# Velocita' massime tra keyframe (rad/s) per giunto; gli altri usano max_velocity.
# WristYaw di Pepper arriva a ~17 rad/s: 5 rad/s resta ampiamente sotto il limite.
JOINT_MAX_VELOCITY = {"LWristYaw": 5.0, "RWristYaw": 5.0}


def fill_gaps(values, default):
    v = np.array(values, dtype=float)
    ok = np.isfinite(v)
    if not ok.any():
        return np.full_like(v, default)
    idx = np.arange(len(v))
    return np.interp(idx, idx[ok], v[ok])


def savgol(values, window=9, order=2):
    """Filtro Savitzky-Golay con padding a specchio."""
    v = np.asarray(values, dtype=float)
    n = len(v)
    if n < 3:
        return v.copy()
    window = int(window)
    if window % 2 == 0:
        window += 1
    window = min(window, n if n % 2 == 1 else n - 1)
    if window <= order:
        return v.copy()
    half = window // 2
    x = np.arange(-half, half + 1)
    A = np.vander(x, order + 1, increasing=True)
    coeffs = np.linalg.pinv(A)[0]
    padded = np.concatenate([v[half:0:-1], v, v[-2:-half - 2:-1]])
    return np.convolve(padded, coeffs[::-1], mode="valid")


def process_trajectories(raw, smooth_window=9, fast_window=None):
    """
    raw: dict giunto -> (T,). Ritorna dict giunto -> (T,) pulito e nei limiti.
    fast_window: finestra di smoothing per FAST_JOINTS (default = smooth_window).
    """
    clean = {}
    for name in pk.DEFAULT_JOINTS:
        v = fill_gaps(raw[name], pk.REST_POSE[name])
        if name.endswith("ElbowYaw"):
            v = np.unwrap(v)          # evita salti di 2*pi prima dello smoothing
        if np.isfinite(raw[name]).any():
            window = fast_window if (fast_window and name in FAST_JOINTS) else smooth_window
            v = savgol(v, window)
        lo, hi = pk.JOINT_LIMITS[name]
        clean[name] = np.clip(v, lo, hi)
    return clean


def select_keyframes(traj, times, epsilon=0.08, max_keyframes=20, min_gap=0.12, mandatory=()):
    """
    Ritorna gli indici dei keyframe (sempre inclusi il primo, l'ultimo e i `mandatory`).
    max_keyframes limita i keyframe aggiunti oltre a quelli obbligatori.
    """
    Q = np.column_stack([traj[name] for name in pk.DEFAULT_JOINTS])
    n = len(times)
    if n <= 2:
        return list(range(n))

    def max_deviation(i, j):
        if j - i < 2:
            return -1.0, None
        alpha = (times[i + 1:j] - times[i]) / max(times[j] - times[i], 1e-9)
        interp = Q[i] + alpha[:, None] * (Q[j] - Q[i])
        dev = np.max(np.abs(Q[i + 1:j] - interp), axis=1)
        k = int(np.argmax(dev))
        return float(dev[k]), i + 1 + k

    fixed = sorted(set([0, n - 1] + [int(i) for i in mandatory if 0 < int(i) < n - 1]))
    eps = float(epsilon)
    for _ in range(30):
        keys = list(fixed)
        stack = list(zip(fixed[:-1], fixed[1:]))
        while stack:
            i, j = stack.pop()
            dev, k = max_deviation(i, j)
            if k is not None and dev > eps:
                if times[k] - times[i] >= min_gap and times[j] - times[k] >= min_gap:
                    keys.append(k)
                    stack.append((i, k))
                    stack.append((k, j))
        keys = sorted(set(keys))
        if len(keys) <= max_keyframes + len(fixed) - 2:
            return keys
        eps *= 1.3
    return keys


def keyframes_to_frames(traj, times, keys, speed=1.0, first_dt=1.0, max_velocity=2.0, min_dt=0.15,
                        joint_max_velocity=None):
    """Ritorna la lista di frame {angles, dt, source_time} nel formato della GUI."""
    limits = [float((joint_max_velocity or {}).get(name, max_velocity)) for name in pk.DEFAULT_JOINTS]
    frames = []
    prev = None
    for n, k in enumerate(keys):
        angles = [float(traj[name][k]) for name in pk.DEFAULT_JOINTS]
        if n == 0:
            dt = first_dt
        else:
            dt = (times[k] - times[keys[n - 1]]) / max(speed, 1e-3)
            needed = max(abs(a - b) / v for a, b, v in zip(angles, prev, limits))
            dt = max(dt, needed, min_dt)
        frames.append({"angles": angles, "dt": round(float(dt), 3), "source_time": round(float(times[k]), 3)})
        prev = angles
    return frames


def build_frames_v1(name, gesture_id, frames, metadata):
    return {
        "name": name,
        "gesture_id": gesture_id,
        "format": "frames_v1",
        "joints": list(pk.DEFAULT_JOINTS),
        "frames": frames,
        "created_at": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
        "source": "video_beta",
        "beta": metadata,
    }


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
