"""Test di andata e ritorno: angoli Pepper -> FK -> keypoint 'umani' -> retarget -> angoli."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from retarget import pepper_kinematics as pk
from retarget.keypoints import PoseSequence
from retarget.retarget import retarget_sequence
from retarget.depth import estimate_depth
from retarget import postprocess as pp

rng = np.random.default_rng(0)

def random_arm(side):
    sgn = 1 if side == "L" else -1
    sp = rng.uniform(-1.2, 1.5)
    sr = sgn * rng.uniform(0.05, 1.3)
    ey = sgn * rng.uniform(-1.8, 1.8) * -1
    er = -sgn * rng.uniform(0.3, 1.5)
    return sp, sr, ey, er

def torso_to_camera(p, yaw, scale, offset):
    # torso: x avanti, y sinistra, z su  ->  camera: x destra(=sinistra persona), y su, z verso camera(=avanti)
    cam = np.array([p[1], p[2], p[0]])
    c, s = np.cos(yaw), np.sin(yaw)
    Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return scale * Ry.dot(cam) + offset

def make_sequence(configs, yaw=0.0, scale=1.7, offset=np.array([0.3, 0.1, -2.0])):
    T = len(configs)
    seq = PoseSequence(T, 25, "synthetic", True)
    for t, cfg in enumerate(configs):
        fk = pk.forward_kinematics_pose(cfg)
        for side, s in (("L", "l"), ("R", "r")):
            seq.body[s + "_shoulder"][t] = torso_to_camera(fk[side]["shoulder"], yaw, scale, offset)
            seq.body[s + "_elbow"][t] = torso_to_camera(fk[side]["elbow"], yaw, scale, offset)
            seq.body[s + "_wrist"][t] = torso_to_camera(fk[side]["wrist"], yaw, scale, offset)
            hip = fk[side]["shoulder"] + np.array([0, 0, -0.45])
            seq.body[s + "_hip"][t] = torso_to_camera(hip, yaw, scale, offset)
        seq.body["nose"][t] = torso_to_camera(np.array([0.08, 0, 0.25]), yaw, scale, offset)
    return seq

def angle_err(a, b):
    return np.abs((a - b + np.pi) % (2 * np.pi) - np.pi)

# --- 1) 3D, pose casuali, persona ruotata/spostata/scalata ---
configs = []
for _ in range(300):
    cfg = {}
    for side in ("L", "R"):
        sp, sr, ey, er = random_arm(side)
        cfg.update({side + "ShoulderPitch": sp, side + "ShoulderRoll": sr, side + "ElbowYaw": ey, side + "ElbowRoll": er})
    configs.append(cfg)
# Il retargeting usa le direzioni dei segmenti: e' esatto per un braccio senza
# offset laterali. Per questo controllo si annullano gli offset del gomito
# dell'URDF (l'inclinazione di 9 gradi resta ed e' gestita); con il modello
# completo resta un errore minimo (offset verticale di 0.13 mm, controllato piu' sotto).
_saved = (pk.ELBOW_OFFSET_Y, pk.ELBOW_OFFSET_Z)
pk.ELBOW_OFFSET_Y, pk.ELBOW_OFFSET_Z = 0.0, 0.0
for yaw in (0.0, 0.3):
    seq = make_sequence(configs, yaw=yaw)
    raw, derr = retarget_sequence(seq)
    for j in ["ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll"]:
        errs = []
        for side in "LR":
            truth = np.array([c[side + j] for c in configs])
            errs.append(angle_err(raw[side + j], truth))
        e = np.concatenate(errs)
        print("3D yaw=%.1f  %-14s max err = %.2e rad" % (yaw, j, np.nanmax(e)))
        assert np.nanmax(e) < 1e-6, j
print("3D: angoli ricostruiti esattamente (anche con persona ruotata, spostata e scalata)")
pk.ELBOW_OFFSET_Y, pk.ELBOW_OFFSET_Z = _saved

# Modello URDF completo (offset del gomito di 15 mm): errore piccolo
seq = make_sequence(configs)
raw, _ = retarget_sequence(seq)
for j in ["ShoulderPitch", "ShoulderRoll", "ElbowRoll"]:
    e = np.concatenate([angle_err(raw[side + j], np.array([c[side + j] for c in configs])) for side in "LR"])
    print("URDF completo  %-14s errore mediano = %.1f deg, 95%% = %.1f deg" % (j, np.degrees(np.nanmedian(e)), np.degrees(np.nanpercentile(e, 95))))
    assert np.degrees(np.nanpercentile(e, 95)) < 1.0, j

# --- 2) mirror: il braccio sinistro umano va sul braccio destro di Pepper ---
seq = make_sequence(configs[:50])
raw_m, _ = retarget_sequence(seq, mirror=True)
truth = np.array([c["LShoulderRoll"] for c in configs[:50]])
assert np.allclose(raw_m["RShoulderRoll"], -truth), "mirror"
print("mirror: OK")

# --- 3) 2D + stima profondita' (opzione A): pose con mani davanti al corpo ---
configs2 = []
for _ in range(300):
    cfg = {}
    for side in ("L", "R"):
        sgn = 1 if side == "L" else -1
        cfg.update({side + "ShoulderPitch": rng.uniform(-0.3, 1.2), side + "ShoulderRoll": sgn * rng.uniform(0.05, 0.6),
                    side + "ElbowYaw": -sgn * rng.uniform(0.6, 1.6), side + "ElbowRoll": -sgn * rng.uniform(0.3, 1.2)})
    configs2.append(cfg)
seq3 = make_sequence(configs2, offset=np.zeros(3))
seq2 = PoseSequence(seq3.n_frames, 25, "synthetic2d", False)
for k in seq3.body:
    seq2.body[k] = seq3.body[k].copy(); seq2.body[k][:, 2] = np.nan
info = estimate_depth(seq2)
raw2, derr2 = retarget_sequence(seq2)
for j in ["ShoulderPitch", "ShoulderRoll", "ElbowRoll"]:
    e = np.concatenate([angle_err(raw2[s + j], np.array([c[s + j] for c in configs2])) for s in "LR"])
    print("2D+depth %-14s errore mediano = %.1f deg, 90%% = %.1f deg" % (j, np.degrees(np.nanmedian(e)), np.degrees(np.nanpercentile(e, 90))))

# --- 4) postprocess + keyframe su una traiettoria liscia ---
T = 100
t = np.arange(T) / 25.0
smooth_cfg = [{"LShoulderPitch": 1.0 - 0.8 * np.sin(np.pi * x / t[-1]), "LShoulderRoll": 0.3,
               "LElbowYaw": -1.0, "LElbowRoll": -0.4 - 0.6 * np.sin(2 * np.pi * x / t[-1]) ** 2,
               "RShoulderPitch": 1.4, "RShoulderRoll": -0.2, "RElbowYaw": 1.2, "RElbowRoll": 0.5} for x in t]
seq4 = make_sequence(smooth_cfg)
raw4, _ = retarget_sequence(seq4)
raw4["LShoulderPitch"][30:35] = np.nan          # buco nei dati
clean = pp.process_trajectories(raw4)
keys = pp.select_keyframes(clean, t, epsilon=0.05, max_keyframes=20)
frames = pp.keyframes_to_frames(clean, t, keys)
print("keyframe:", len(keys), "su", T, "frame; dt =", [f["dt"] for f in frames])
assert 3 <= len(keys) <= 20
for name in pk.DEFAULT_JOINTS:
    lo, hi = pk.JOINT_LIMITS[name]
    assert np.all(clean[name] >= lo - 1e-9) and np.all(clean[name] <= hi + 1e-9)
# errore di ricostruzione interpolando i keyframe
Q = np.column_stack([clean[n] for n in pk.DEFAULT_JOINTS]); K = Q[keys]
recon = np.column_stack([np.interp(t, t[keys], K[:, i]) for i in range(Q.shape[1])])
print("max errore interpolando i keyframe: %.3f rad" % np.max(np.abs(recon - Q)))
data = pp.build_frames_v1("test", "test_auto", frames, {"extractor": "synthetic"})
pp.write_json(os.path.join(tempfile.gettempdir(), "test_auto.json"), data)
print("JSON scritto in", tempfile.gettempdir())
