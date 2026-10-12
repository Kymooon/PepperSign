"""Test della stima del polso (WristYaw) dai punti della mano."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from retarget import pepper_kinematics as pk, wrist as W  # noqa: E402
from retarget.generate import generate  # noqa: E402
from retarget.keypoints import PoseSequence  # noqa: E402

rng = np.random.default_rng(3)

# 1) Pepper: dato il segnale prodotto da un WristYaw noto, il solutore lo ritrova
errs = []
for _ in range(300):
    for side in "LR":
        sg = 1 if side == "L" else -1
        q = np.array([rng.uniform(-0.5, 1.5), sg * rng.uniform(0.1, 1.0), -sg * rng.uniform(0.3, 1.8), -sg * rng.uniform(0.3, 1.5)])
        w_true = rng.uniform(-1.6, 1.6)
        c = W.pepper_palm_signal(side, q, w_true)
        if not np.isfinite(c):
            continue
        w, M = W.solve_wrist(side, q, c, w_ref=w_true + rng.normal(0, 0.1))
        if w is None:
            continue
        errs.append(abs(w - w_true))
print("Solutore polso: errore mediano %.4f rad, 95%% %.4f rad su %d casi" % (np.median(errs), np.percentile(errs, 95), len(errs)))
assert np.percentile(errs, 95) < 1e-3

# 2) persona: mano che ruota attorno all'avambraccio orizzontale -> segnale = cos(angolo)
T = 50
seq = PoseSequence(T, 25, "dwpose", False)
angles = np.linspace(0, np.pi, T)            # da palmo verso la camera a dorso verso la camera
for t in range(T):
    seq.body["r_elbow"][t] = [0.30, -0.60, np.nan]
    seq.body["r_wrist"][t] = [0.50, -0.60, np.nan]   # avambraccio verso +x
    hand = np.full((21, 3), np.nan)
    hand[0] = [0.50, -0.60, np.nan]
    hand[9] = [0.60, -0.60, np.nan]
    half = 0.04 * np.cos(angles[t])               # meta' larghezza nocche proiettata
    hand[5] = [0.58, -0.60 + half, np.nan]        # indice
    hand[17] = [0.58, -0.60 - half, np.nan]       # mignolo
    seq.hands["r"][t] = hand
    seq.hand_conf["r"][t] = 0.9
c, info = W.human_palm_signal(seq, "r")
print("Segnale persona: inizio %.2f, meta' %.2f, fine %.2f (larghezza nocche %.3f)" % (c[0], c[T // 2], c[-1], info["knuckle_width"]))
assert c[0] > 0.95 and abs(c[T // 2]) < 0.1 and c[-1] < -0.95
c_m, _ = W.human_palm_signal(seq, "r", mirror=True)
assert np.allclose(c_m, -c)
seq.hand_conf["r"][:] = 0.2
c_low, info_low = W.human_palm_signal(seq, "r")
assert np.all(np.isnan(c_low)) and info_low["frames"] == 0

# 3) punti di svolta: oscillazione di 4 Hz -> un picco ogni mezzo periodo
t = np.arange(100) / 25.0
v = 0.3 * np.sin(2 * np.pi * 4 * t) * ((t > 1) & (t < 3))
pts = W.turning_points(v, t)
print("Punti di svolta su oscillazione 4 Hz: %d" % len(pts))
assert len(pts) >= 14 and all(abs(v[i]) > 0.2 for i in pts[:-1])
assert W.turning_points(np.zeros(50), t[:50]) == []
assert W.turning_points(0.03 * np.sin(2 * np.pi * 4 * t), t) == []

# 4) pipeline: braccio alzato con mano che oscilla -> WristYaw oscilla nei keyframe
T = 75
seq = PoseSequence(T, 25, "dwpose", False)
for k in range(T):
    up = 15 <= k < 60
    seq.body["l_shoulder"][k] = [0.75, -0.55, np.nan]
    seq.body["r_shoulder"][k] = [0.45, -0.55, np.nan]
    seq.body["l_hip"][k] = [0.72, -1.05, np.nan]
    seq.body["r_hip"][k] = [0.48, -1.05, np.nan]
    seq.body["nose"][k] = [0.6, -0.35, np.nan]
    seq.body["l_elbow"][k] = [0.80, -0.80, np.nan]
    seq.body["l_wrist"][k] = [0.80, -0.99, np.nan]
    seq.body["r_elbow"][k] = [0.36, -0.70 if up else -0.80, np.nan]
    wr = np.array([0.55, -0.42]) if up else np.array([0.40, -0.995])
    seq.body["r_wrist"][k] = [wr[0], wr[1], np.nan]
    if up:
        f = wr - np.array([0.36, -0.70])
        f = f / np.linalg.norm(f)
        n = np.array([-f[1], f[0]])
        ang = 1.0 + 0.5 * np.sin(2 * np.pi * 3 * k / 25.0)
        hand = np.full((21, 3), np.nan)
        hand[0, :2] = wr
        hand[9, :2] = wr + 0.08 * f
        hand[5, :2] = wr + 0.07 * f + 0.03 * np.cos(ang) * n
        hand[17, :2] = wr + 0.07 * f - 0.03 * np.cos(ang) * n
        seq.hands["r"][k] = hand
        seq.hand_conf["r"][k] = 0.9
gesture, raw, clean, keys, stats = generate(seq, "prova_polso", speed=0.8)
J = gesture["joints"]
wy = [dict(zip(J, fr["angles"]))["RWristYaw"] for fr in gesture["frames"]]
print("Pipeline: %d keyframe, WristYaw nei keyframe (gradi): %s, stats %s"
      % (len(wy), [int(round(np.degrees(x))) for x in wy], stats["wrist"]["R"]))
assert stats["wrist"]["R"]["estimated"] > 30
assert stats["wrist"]["R"]["turning_points"] >= 4
assert max(wy) - min(wy) > 0.3
assert abs(wy[0] - pk.REST_POSE["RWristYaw"]) < 1e-6 and abs(wy[-1] - pk.REST_POSE["RWristYaw"]) < 0.13
for fr in gesture["frames"]:
    for j, a in zip(J, fr["angles"]):
        lo, hi = pk.JOINT_LIMITS[j]
        assert lo - 1e-9 <= a <= hi + 1e-9, (j, a)

# 5) --no-wrist: polso fermo nella posa di riposo (comportamento precedente)
gesture0, _, _, _, stats0 = generate(seq, "prova_polso", speed=0.8, use_wrist=False)
wy0 = [dict(zip(J, fr["angles"]))["RWristYaw"] for fr in gesture0["frames"]]
assert all(abs(x) < 1e-9 for x in wy0) and stats0["wrist"] == {}
print("OK")
