"""
Confronto del modello cinematico con le posizioni misurate dal robot.

NAOqi calcola con il proprio modello la posizione di giunti ed effettori
(ALMotion.getPosition(nome, FRAME_TORSO, True)). Registrando sul robot, per
alcune pose, gli angoli dei giunti e queste posizioni, si puo' verificare
quale modello di Pepper e' piu' vicino al robot vero:
  - "urdf": URDF ufficiale (modello in uso);
  - "doc":  URDF + polso spostato di 23.6 mm verso l'interno (documentazione NAOqi);
  - "semplificato": il modello usato fino al 07/10/2026.

Formato del file (JSON):
    {"samples": [
        {"angles": {"RShoulderPitch": 0.5, "RShoulderRoll": -0.2, ...},
         "positions": {"RElbowYaw": [x, y, z, ...], "RWristYaw": [...], "RArm": [...]}},
        ...
    ]}
Le posizioni sono in metri nel sistema del torso (le eventuali componenti di
rotazione dopo x, y, z vengono ignorate). Punti confrontati:
    <lato>ElbowYaw -> gomito, <lato>WristYaw -> polso, <lato>Arm -> centro della mano.

Uso:
    python3 -m retarget.model_check --input data/media/_retarget/model_samples.json
"""
import argparse
import json
import sys

import numpy as np

from . import pepper_kinematics as pk

POINTS = (("ElbowYaw", "elbow"), ("WristYaw", "wrist"), ("Arm", "hand"))
ARM = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw")
DOC_WRIST_OFFSET_Y = 0.0236


def _fk(model, side, q):
    if model == "semplificato":
        return pk.arm_forward_kinematics_simple(side, *q)
    if model == "doc":
        saved = pk.WRIST_OFFSET_Y
        pk.WRIST_OFFSET_Y = DOC_WRIST_OFFSET_Y
        try:
            return pk.arm_forward_kinematics(side, *q)
        finally:
            pk.WRIST_OFFSET_Y = saved
    return pk.arm_forward_kinematics(side, *q)


def compare(samples, models=("urdf", "doc", "semplificato")):
    """Ritorna {modello: {punto: [errori in metri]}}."""
    result = dict((m, dict((label, []) for _, label in POINTS)) for m in models)
    for sample in samples:
        angles = sample.get("angles", {})
        positions = sample.get("positions", {})
        for side in ("L", "R"):
            if not all((side + j) in angles for j in ARM):
                continue
            q = [float(angles[side + j]) for j in ARM]
            for model in models:
                fk = _fk(model, side, q)
                for suffix, label in POINTS:
                    measured = positions.get(side + suffix)
                    if measured is None or len(measured) < 3:
                        continue
                    err = np.linalg.norm(fk[label] - np.asarray(measured[:3], dtype=float))
                    result[model][label].append(float(err))
    return result


def format_report(result):
    lines = ["| Modello | Gomito (mediano / max) | Polso (mediano / max) | Centro mano (mediano / max) |",
             "|---|---|---|---|"]
    for model, points in result.items():
        cells = []
        for _, label in POINTS:
            e = np.array(points[label])
            cells.append("%.1f / %.1f mm (%d)" % (1000 * np.median(e), 1000 * e.max(), e.size) if e.size else "-")
        lines.append("| %s | %s |" % (model, " | ".join(cells)))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confronto modello cinematico di Pepper / posizioni misurate da NAOqi")
    ap.add_argument("--input", required=True)
    args = ap.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)
    samples = data.get("samples", data if isinstance(data, list) else [])
    if not samples:
        print("Nessun campione nel file.")
        return 1
    print("%d pose" % len(samples))
    print(format_report(compare(samples)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
