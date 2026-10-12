"""Test F1: IK sulla posizione del polso, tablet, posa di riposo, pipeline completa."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from retarget import ik, pepper_kinematics as pk, postprocess as pp  # noqa: E402
from retarget.generate import generate  # noqa: E402
from retarget.keypoints import PoseSequence  # noqa: E402
from retarget.rest import detect_rest  # noqa: E402

rng = np.random.default_rng(7)

# 1) IK: bersagli raggiungibili -> polso esatto
errs = []
for _ in range(150):
    for side in "LR":
        sg = 1 if side == "L" else -1
        q = np.array([rng.uniform(-1, 1.5), sg * rng.uniform(0.1, 1.2), -sg * rng.uniform(0.3, 1.8), -sg * rng.uniform(0.2, 1.4)])
        if ik.tablet_collision(side, q, ik.TABLET_MARGIN) > 0:
            continue
        tgt = pk.arm_forward_kinematics(side, *q)["wrist"]
        _, info = ik.solve_arm(side, tgt, q + rng.normal(0, 0.3, 4), reg=1e-6)
        errs.append(info["error_3d"])
print("IK raggiungibili: errore max %.2f mm su %d casi" % (1000 * max(errs), len(errs)))
assert np.percentile(errs, 95) < 1e-3

# 2) IK: bersaglio davanti al mento (oltre il limite del gomito) -> errore frontale piccolo
S = pk.shoulder_position("R")
_, info = ik.solve_arm("R", np.array([0.10, -0.02, S[2] + 0.07]), [0.5, -0.3, 1.0, 1.2])
print("IK mento: errore frontale %.1f cm (3D %.1f cm)" % (100 * info["error_frontal"], 100 * info["error_3d"]))
assert info["error_frontal"] < 0.03

# 3) IK: bersaglio dentro il tablet -> nessuna penetrazione
_, info = ik.solve_arm("R", np.array([0.08, -0.05, -0.05]), [1.0, -0.3, 1.0, 1.0])
print("IK tablet: penetrazione %.1f cm" % (100 * info["tablet_penetration"]))
assert info["tablet_penetration"] < 0.005

# 4) posa di riposo: polso sul bordo inferiore -> riposo; mano alzata -> attivo
T = 60
seq = PoseSequence(T, 25, "dwpose", False)
for t in range(T):
    up = 20 <= t < 40
    seq.body["l_shoulder"][t] = [0.75, -0.55, np.nan]
    seq.body["r_shoulder"][t] = [0.45, -0.55, np.nan]
    seq.body["l_hip"][t] = [0.72, -1.05, np.nan]
    seq.body["r_hip"][t] = [0.48, -1.05, np.nan]
    seq.body["nose"][t] = [0.6, -0.35, np.nan]
    seq.body["l_elbow"][t] = [0.80, -0.80, np.nan]
    seq.body["l_wrist"][t] = [0.80, -0.99, np.nan]
    seq.body["r_elbow"][t] = [0.36, -0.70 if up else -0.80, np.nan]
    seq.body["r_wrist"][t] = [0.55, -0.42, np.nan] if up else [0.40, -0.995, np.nan]
rest = detect_rest(seq)
print("riposo sx:", "".join("R" if x else "." for x in rest["l"]))
print("riposo dx:", "".join("R" if x else "." for x in rest["r"]))
assert rest["l"].all() and not rest["r"][22:38].any() and rest["r"][:18].all()

# 5) pipeline completa: inizia e finisce a riposo, mano alzata in mezzo, JSON valido
gesture, raw, clean, keys, stats = generate(seq, "prova", speed=0.8)
fr = gesture["frames"]
rest_vec = np.array([pk.REST_POSE[j] for j in pk.DEFAULT_JOINTS])
assert np.allclose(fr[0]["angles"], rest_vec, atol=0.13) and np.allclose(fr[-1]["angles"], rest_vec, atol=0.13)
J = gesture["joints"]
mid = max(fr, key=lambda f: -dict(zip(J, f["angles"]))["RShoulderPitch"])
print("keyframe: %d, durata %.1fs, RShoulderPitch minimo %.2f rad, contatti tablet %d"
      % (len(fr), sum(f["dt"] for f in fr), dict(zip(J, mid["angles"]))["RShoulderPitch"], stats["tablet_keyframes"]))
for f in fr:
    for j, a in zip(J, f["angles"]):
        lo, hi = pk.JOINT_LIMITS[j]
        assert lo - 1e-9 <= a <= hi + 1e-9, (j, a)
path = os.path.join(tempfile.mkdtemp(), "prova_auto.json")
pp.write_json(path, gesture)
print("OK - JSON:", path)
