"""
Frame di Pepper da coordinate: posizione della mano + direzione di palmo e dita (BETA).

E' l'equivalente del generatore MATLAB di Botta et al. (posizione 3D,
orientamento, configurazione della mano, specchiatura sull'altro braccio,
pesi del solutore), ma produce direttamente frame nel formato della GUI di
Controll (frames_v1), quindi si possono mescolare con i frame registrati
muovendo il robot o generati dal video.

Sistema di riferimento: torso di Pepper, in metri
    x avanti, y verso la SINISTRA del robot (= destra di chi lo guarda), z in alto.
    Spalle a x = -0.057, y = +-0.150, z = 0.087. Riferimenti utili (approssimati):
    centro del petto davanti al tablet ~ (0.15, 0, 0.0), altezza del mento ~ z 0.20.

Direzioni (palmo / dita): un vettore "x,y,z" oppure un nome, dal punto di vista del robot:
    avanti, indietro, su, giu, sinistra, destra, dentro (verso il centro del corpo),
    fuori (verso l'esterno). Si possono combinare: "avanti+su".

Uso (dentro il container Process):
    python3 -m retarget.pose --side R --point 0.20 -0.05 0.20 --palm indietro --fingers su
    python3 -m retarget.pose --side R --landmark mento --offset 3 0 0 --palm indietro
    python3 -m retarget.pose --side R --point 0.20 -0.05 0.20 --palm sinistra --mirror --hand 1 \
        --out /data/gestures/prova_coordinate.json --dt 1.2
Con --out il frame viene aggiunto in coda al gesto (frames_v1), creato se non esiste:
in Controll si apre con "Carica sequenza JSON".
"""
import argparse
import datetime
import json
import os
import sys

import numpy as np

from . import ik
from . import landmarks as lm
from . import pepper_kinematics as pk

ARM5 = ik.ARM5_SUFFIXES

_BASE_DIRECTIONS = {
    "avanti": (1, 0, 0), "forward": (1, 0, 0),
    "indietro": (-1, 0, 0), "back": (-1, 0, 0),
    "su": (0, 0, 1), "alto": (0, 0, 1), "up": (0, 0, 1),
    "giu": (0, 0, -1), "basso": (0, 0, -1), "down": (0, 0, -1),
    "sinistra": (0, 1, 0), "left": (0, 1, 0),
    "destra": (0, -1, 0), "right": (0, -1, 0),
}

# Soglie per gli avvisi
WARN_POSITION = 0.02        # m
WARN_ORIENTATION = 20.0     # gradi


def parse_direction(text, side):
    """Nome (anche combinato con '+') o 'x,y,z' -> vettore unitario nel torso; None se vuoto."""
    if text is None or str(text).strip() == "":
        return None
    text = str(text).strip().lower()
    if "," in text:
        v = np.array([float(x) for x in text.split(",")], dtype=float)
    else:
        v = np.zeros(3)
        inward = (0, -1, 0) if side == "L" else (0, 1, 0)
        for part in text.replace(" ", "").split("+"):
            if part in ("dentro", "inward"):
                v += inward
            elif part in ("fuori", "outward"):
                v -= np.array(inward)
            elif part in _BASE_DIRECTIONS:
                v += _BASE_DIRECTIONS[part]
            else:
                raise ValueError("Direzione sconosciuta: %s" % part)
    n = np.linalg.norm(v)
    if n < 1e-9:
        raise ValueError("Direzione nulla: %s" % text)
    return v / n


def rest_angles():
    return dict((j, float(pk.REST_POSE[j])) for j in pk.DEFAULT_JOINTS)


def solve_side(side, point=None, palm=None, fingers=None, hand=None, base=None,
               w_palm=ik.DEFAULT_ORIENT_WEIGHT, w_fingers=ik.DEFAULT_ORIENT_WEIGHT, point_kind="hand"):
    """
    Risolve un braccio. base: angoli {giunto: valore} di partenza (es. frame precedente).
    Ritorna (angoli {giunto: valore} del braccio, info con errori e avvisi).
    """
    base = base or rest_angles()
    q_init = [base[side + s] for s in ARM5]
    target = None if point is None else np.asarray(point, dtype=float)
    q, info = ik.solve_arm_pose(side, target, palm, fingers, point=point_kind, q_init=q_init,
                                w_palm=w_palm, w_fingers=w_fingers)
    angles = dict((side + s, float(v)) for s, v in zip(ARM5, q))
    angles[side + "Hand"] = float(np.clip(hand, 0.0, 1.0)) if hand is not None else float(base[side + "Hand"])
    warnings = []
    if info.get("error_position", 0.0) > WARN_POSITION:
        warnings.append("posizione non raggiungibile: scarto %.1f cm" % (100 * info["error_position"]))
    for key, label in (("palm", "palmo"), ("fingers", "dita")):
        if info.get("error_%s_deg" % key, 0.0) > WARN_ORIENTATION:
            warnings.append("%s ruotato di %.0f gradi rispetto alla richiesta" % (label, info["error_%s_deg" % key]))
    if info["tablet_penetration"] > 0.0:
        warnings.append("vicino al tablet (%.1f cm)" % (100 * info["tablet_penetration"]))
    info["warnings"] = warnings
    return angles, info


def make_frame(sides, base=None, dt=1.0, mirror=False):
    """
    sides: {"R": {point, palm, fingers, hand, ...}, "L": {...}} (uno o entrambi).
    mirror=True: il braccio risolto (uno solo) viene copiato specchiato sull'altro.
    Ritorna (frame frames_v1 {angles, dt, note, warning?}, info per lato).
    """
    angles = dict(base) if base else rest_angles()
    infos = {}
    for side, spec in sides.items():
        arm, info = solve_side(side, base=angles, **spec)
        angles.update(arm)
        infos[side] = info
        if mirror:
            suffix_angles = dict((j[1:], v) for j, v in arm.items())
            angles.update(pk.mirror_arm_angles(suffix_angles, side))
    warnings = ["%s: %s" % (side, w) for side, info in infos.items() for w in info["warnings"]]
    frame = {"angles": [float(angles[j]) for j in pk.DEFAULT_JOINTS], "dt": round(float(dt), 3),
             "note": "da coordinate (beta)"}
    if warnings:
        frame["warning"] = "; ".join(warnings)
    return frame, infos


def append_to_gesture(path, frame, name=None):
    """Aggiunge il frame in coda a un gesto frames_v1 (lo crea se non esiste). Ritorna il gesto."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            gesture = json.load(handle)
        if gesture.get("format") != "frames_v1" or list(gesture.get("joints", [])) != list(pk.DEFAULT_JOINTS):
            raise ValueError("%s non e' un gesto frames_v1 con i giunti standard" % path)
    else:
        gid = name or os.path.splitext(os.path.basename(path))[0]
        gesture = {"name": gid, "gesture_id": gid, "format": "frames_v1", "joints": list(pk.DEFAULT_JOINTS),
                   "frames": [], "created_at": datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
                   "source": "coordinates_beta"}
    gesture["frames"].append(frame)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(gesture, handle, indent=2, ensure_ascii=False)
    return gesture


def solve_request(payload):
    """
    Richiesta JSON (GUI di Controll / endpoint /retarget/pose) -> risposta JSON.
        side: "R" | "L"
        landmark: id da landmarks.py   oppure   point: [x, y, z] (torso, metri)
        offset_cm: {"avanti": 0, "su": 0, "esterno": 0}   (solo con landmark)
        palm, fingers: nome o "x,y,z" (vuoto = libero); hand: 0..1 o null
        mirror: bool; dt: s; base: {giunto: angolo} (partenza, es. frame selezionato)
        w_palm, w_fingers: pesi (opzionali)
    Solleva ValueError per richieste non valide.
    """
    side = str(payload.get("side", "R")).upper()
    if side not in ("L", "R"):
        raise ValueError("side deve essere L o R")
    if payload.get("landmark"):
        off = payload.get("offset_cm") or {}
        point = lm.landmark_point(payload["landmark"], side,
                                  forward=float(off.get("avanti", 0.0)) / 100.0,
                                  up=float(off.get("su", 0.0)) / 100.0,
                                  outward=float(off.get("esterno", 0.0)) / 100.0)
    elif payload.get("point") is not None:
        point = [float(v) for v in payload["point"]]
        if len(point) != 3:
            raise ValueError("point deve avere 3 coordinate")
    else:
        point = None
    palm = parse_direction(payload.get("palm"), side)
    fingers = parse_direction(payload.get("fingers"), side)
    if point is None and palm is None and fingers is None:
        raise ValueError("serve un punto o almeno una direzione")
    hand = payload.get("hand")
    base = rest_angles()
    for joint, value in (payload.get("base") or {}).items():
        if joint in base and value is not None:
            base[joint] = float(value)
    spec = {"point": point, "palm": palm, "fingers": fingers,
            "hand": None if hand is None else float(hand),
            "w_palm": float(payload.get("w_palm", ik.DEFAULT_ORIENT_WEIGHT)),
            "w_fingers": float(payload.get("w_fingers", ik.DEFAULT_ORIENT_WEIGHT))}
    frame, infos = make_frame({side: spec}, base=base, dt=float(payload.get("dt", 1.0)),
                              mirror=bool(payload.get("mirror", False)))
    info = infos[side]
    return {
        "ok": True,
        "joints": list(pk.DEFAULT_JOINTS),
        "angles": dict(zip(pk.DEFAULT_JOINTS, frame["angles"])),
        "frame": frame,
        "point": point,
        "error_position_cm": round(100 * info["error_position"], 2) if "error_position" in info else None,
        "error_palm_deg": round(info["error_palm_deg"], 1) if "error_palm_deg" in info else None,
        "error_fingers_deg": round(info["error_fingers_deg"], 1) if "error_fingers_deg" in info else None,
        "tablet_cm": round(100 * info["tablet_penetration"], 2),
        "warnings": info["warnings"],
    }


def _last_frame_angles(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        gesture = json.load(handle)
    if not gesture.get("frames"):
        return None
    return dict(zip(gesture["joints"], gesture["frames"][-1]["angles"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Frame di Pepper da coordinate della mano (beta)")
    ap.add_argument("--side", choices=["L", "R"], default="R", help="braccio del robot (default R)")
    ap.add_argument("--point", type=float, nargs=3, metavar=("X", "Y", "Z"),
                    help="posizione del centro della mano nel torso (metri)")
    ap.add_argument("--landmark", choices=lm.landmark_ids(), default=None,
                    help="punto del corpo di Pepper al posto di --point")
    ap.add_argument("--offset", type=float, nargs=3, default=(0.0, 0.0, 0.0), metavar=("AVANTI", "SU", "ESTERNO"),
                    help="spostamento dal punto del corpo, in cm")
    ap.add_argument("--wrist-point", action="store_true", help="--point si riferisce al polso, non al centro della mano")
    ap.add_argument("--palm", default=None, help="direzione del palmo (es. avanti, dentro, 'x,y,z')")
    ap.add_argument("--fingers", default=None, help="direzione delle dita (es. su, avanti+su)")
    ap.add_argument("--hand", type=float, default=None, help="apertura della mano 0..1")
    ap.add_argument("--mirror", action="store_true", help="copia la posa specchiata sull'altro braccio")
    ap.add_argument("--w-palm", type=float, default=ik.DEFAULT_ORIENT_WEIGHT)
    ap.add_argument("--w-fingers", type=float, default=ik.DEFAULT_ORIENT_WEIGHT)
    ap.add_argument("--dt", type=float, default=1.0, help="durata del movimento verso questo frame (s)")
    ap.add_argument("--out", default=None, help="gesto frames_v1 a cui aggiungere il frame")
    ap.add_argument("--name", default=None)
    args = ap.parse_args(argv)

    if args.landmark:
        args.point = lm.landmark_point(args.landmark, args.side, forward=args.offset[0] / 100.0,
                                       up=args.offset[1] / 100.0, outward=args.offset[2] / 100.0)
    if args.point is None and args.palm is None and args.fingers is None:
        ap.error("serve almeno uno tra --point, --landmark, --palm, --fingers")
    spec = {"point": args.point, "palm": parse_direction(args.palm, args.side),
            "fingers": parse_direction(args.fingers, args.side), "hand": args.hand,
            "w_palm": args.w_palm, "w_fingers": args.w_fingers,
            "point_kind": "wrist" if args.wrist_point else "hand"}
    base = _last_frame_angles(args.out) if args.out else None
    frame, infos = make_frame({args.side: spec}, base=base, dt=args.dt, mirror=args.mirror)

    angles = dict(zip(pk.DEFAULT_JOINTS, frame["angles"]))
    info = infos[args.side]
    print("Braccio %s:" % args.side)
    for s in ARM5 + ("Hand",):
        j = args.side + s
        print("  %-15s %7.3f rad  %7.1f gradi" % (j, angles[j], np.degrees(angles[j])))
    print("  posizione ottenuta: (%.3f, %.3f, %.3f) m" % tuple(info["position"]))
    if "error_position" in info:
        print("  scarto posizione: %.1f mm" % (1000 * info["error_position"]))
    for key, label in (("palm", "palmo"), ("fingers", "dita")):
        if "error_%s_deg" % key in info:
            print("  scarto %s: %.1f gradi" % (label, info["error_%s_deg" % key]))
    for w in info["warnings"]:
        print("  [AVVISO] %s" % w)
    if args.out:
        gesture = append_to_gesture(args.out, frame, args.name)
        print("Frame %d aggiunto a %s" % (len(gesture["frames"]), args.out))
    else:
        print(json.dumps(frame))
    return 0


if __name__ == "__main__":
    sys.exit(main())
