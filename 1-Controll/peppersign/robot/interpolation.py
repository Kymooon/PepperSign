# -*- coding: utf-8 -*-
"""
Dai frame di un gesto (formato frames_v1) alle traiettorie per
ALMotion.angleInterpolation. Nessuna chiamata al robot: i limiti arrivano
dall'esterno come funzione `clamp_fn(joints, angles)`.

Controllo dei dati (check_frames, check_gesture): un gesto o un
frame non coerente viene RIFIUTATO, mai completato o tagliato. Prima gli angoli
mancanti diventavano 0 rad (braccio teso in avanti, mano chiusa) e quelli in
piu' venivano tolti, spostando in silenzio i valori sui giunti sbagliati.
"""
from __future__ import absolute_import

from peppersign.compat import string_types
from peppersign.robot.joints import is_valid_number

try:
    _INTEGER_TYPES = (int, long)  # noqa: F821 (Python 2)
except NameError:
    _INTEGER_TYPES = (int,)

# Massimo di problemi riportati per esteso in un messaggio
MAX_REPORTED_PROBLEMS = 5


class InvalidGesture(ValueError):
    """Gesto o frame non coerente; `problems` e' l'elenco dei problemi trovati."""

    def __init__(self, problems):
        self.problems = list(problems)
        ValueError.__init__(self, summarize(self.problems))


def summarize(problems):
    """Testo breve con i primi problemi (per log ed esiti dei comandi)."""
    problems = list(problems)
    text = "; ".join(problems[:MAX_REPORTED_PROBLEMS])
    if len(problems) > MAX_REPORTED_PROBLEMS:
        text += " (e altri %d)" % (len(problems) - MAX_REPORTED_PROBLEMS)
    return text


def _short(value, limit=30):
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def is_number(value):
    """Numero vero e finito (non bool, non testo, non NaN/infinito, non assurdo)."""
    if isinstance(value, bool) or not isinstance(value, _INTEGER_TYPES + (float,)):
        return False
    return is_valid_number(value)


def check_joints(joints):
    """Problemi dell'elenco dei giunti (vuoto, nomi non validi, duplicati)."""
    if not isinstance(joints, (list, tuple)) or not joints:
        return ["elenco dei giunti mancante o vuoto"]
    problems = []
    seen = set()
    for index, name in enumerate(joints):
        if not isinstance(name, string_types) or not name.strip():
            problems.append("giunto %d: nome non valido (%s)" % (index + 1, _short(name)))
        elif name in seen:
            problems.append("giunto %s ripetuto" % name)
        else:
            seen.add(name)
    return problems


def check_frames(joints, frames):
    """
    Problemi di una sequenza frames_v1 (lista vuota = valida): ogni frame deve avere
    esattamente un angolo numerico per giunto e, se indicato, un dt numerico.
    """
    problems = check_joints(joints)
    if problems:
        return problems
    if not isinstance(frames, (list, tuple)) or not frames:
        return ["nessun frame"]
    expected = len(joints)
    for index, frame in enumerate(frames):
        label = "frame %d" % (index + 1)
        if not isinstance(frame, dict):
            problems.append("%s: non e' un oggetto" % label)
            continue
        angles = frame.get("angles")
        if not isinstance(angles, (list, tuple)):
            problems.append("%s: angoli mancanti" % label)
            continue
        if len(angles) != expected:
            problems.append("%s: %d angoli invece di %d" % (label, len(angles), expected))
            continue
        bad = [joints[i] for i, value in enumerate(angles) if not is_number(value)]
        if bad:
            problems.append("%s: valore non numerico per %s" % (label, ", ".join(bad[:4])))
        if "dt" in frame and frame["dt"] is not None and not is_number(frame["dt"]):
            problems.append("%s: dt non valido (%s)" % (label, _short(frame["dt"])))
        elif "dt" in frame and is_number(frame["dt"]) and frame["dt"] <= 0:
            problems.append("%s: dt deve essere maggiore di 0" % label)
    return problems


def check_gesture(payload):
    """Problemi di un gesto letto da JSON (formato frames_v1, l'unico supportato)."""
    if not isinstance(payload, dict):
        return ["il file non contiene un oggetto JSON"]
    if payload.get("format") == "ready_v1" or (payload.get("frames") is None and payload.get("times") is not None):
        return ["formato ready_v1 non piu' supportato: ricarica o registra di nuovo la sequenza (frames_v1)"]
    if payload.get("frames") is None:
        return ["mancano i frame (formato frames_v1)"]
    return check_frames(payload.get("joints"), payload.get("frames"))

# Frame "senza anti-collisione tra le braccia": per i segni in cui le mani si
# sovrappongono (es. buonasera) la protezione di NAOqi sposterebbe un braccio.
NO_ARM_COLLISION_KEY = "no_arm_collision"

DEFAULT_FRAME_DT = 0.6
MIN_FRAME_DT = 0.05


def frame_dt(frame):
    """Durata (s) della transizione verso un frame: default 0.6, minimo 0.05."""
    try:
        dt = float(frame.get("dt", DEFAULT_FRAME_DT))
    except (TypeError, ValueError, OverflowError):
        dt = DEFAULT_FRAME_DT
    return max(dt, MIN_FRAME_DT)


def arm_collision_windows(frames):
    """
    Intervalli di tempo [inizio, fine] (s dall'inizio del movimento) senza
    anti-collisione tra le braccia. Per ogni gruppo di frame consecutivi segnati
    la protezione e' spenta dall'inizio della transizione verso il primo frame
    segnato fino all'arrivo nel primo frame NON segnato successivo (o alla fine
    del gesto), cosi' anche la separazione delle mani avviene senza protezione.
    """
    windows = []
    t = 0.0
    start = None
    for frame in frames or []:
        t_prev = t
        t += frame_dt(frame)
        if frame.get(NO_ARM_COLLISION_KEY):
            if start is None:
                start = t_prev
        elif start is not None:
            windows.append([round(start, 3), round(t, 3)])
            start = None
    if start is not None:
        windows.append([round(start, 3), round(t, 3)])
    return windows


def normalize_frame_angles(joints, frame_angles, clamp_fn):
    """
    Angoli di un frame limitati con clamp_fn. Il numero di angoli deve essere
    uguale a quello dei giunti: altrimenti InvalidGesture (nessun completamento).
    """
    angles = list(frame_angles or [])
    if len(angles) != len(joints):
        raise InvalidGesture(["%d angoli invece di %d" % (len(angles), len(joints))])
    return clamp_fn(joints, angles)


def build_interpolation_from_frames(joints, frames, clamp_fn):
    """
    Frame -> (times_by_joint, angles_by_joint) per angleInterpolation, con i
    tempi cumulati. Ritorna (None, None) se mancano giunti o frame; solleva
    InvalidGesture se i frame non sono coerenti (vedi check_frames).
    """
    if not joints or not frames:
        return None, None
    problems = check_frames(joints, frames)
    if problems:
        raise InvalidGesture(problems)

    total_time = 0.0
    key_times = []
    normalized_frames = []

    for frame in frames:
        total_time += frame_dt(frame)
        key_times.append(total_time)
        normalized_frames.append(normalize_frame_angles(joints, frame.get("angles", []), clamp_fn))

    angles_by_joint = []
    for joint_index in range(len(joints)):
        per_joint = []
        for frame_angles in normalized_frames:
            per_joint.append(frame_angles[joint_index])
        angles_by_joint.append(per_joint)

    times_by_joint = [list(key_times) for _ in joints]
    return times_by_joint, angles_by_joint
