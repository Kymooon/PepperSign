"""Test del passo 2: IK con posizione e orientamento della mano, frame da coordinate."""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from retarget import ik, pepper_kinematics as pk, pose  # noqa: E402

rng = np.random.default_rng(11)

# 1) pose raggiungibili (posizione + palmo + dita): ricostruite quasi esattamente
errs = []
for _ in range(80):
    side = "L" if rng.random() < 0.5 else "R"
    sg = 1 if side == "L" else -1
    q = np.array([rng.uniform(-1, 1.5), sg * rng.uniform(0.1, 1.2), sg * rng.uniform(-1.8, 1.8),
                  -sg * rng.uniform(0.2, 1.4), rng.uniform(-1.6, 1.6)])
    if ik.tablet_collision(side, q, ik.TABLET_MARGIN) > 0:
        continue
    fk = pk.arm_forward_kinematics(side, *q)
    ax = pk.hand_axes(side, fk)
    _, info = ik.solve_arm_pose(side, fk["hand"], ax["palm"], ax["fingers"])
    errs.append((1000 * info["error_position"], info["error_palm_deg"], info["error_fingers_deg"]))
e = np.array(errs)
print("Pose complete raggiungibili (%d): posizione 95%% %.2f mm, palmo 95%% %.2f gradi, dita 95%% %.2f gradi"
      % (len(e), np.percentile(e[:, 0], 95), np.percentile(e[:, 1], 95), np.percentile(e[:, 2], 95)))
assert np.percentile(e[:, 0], 95) < 1.0 and np.percentile(e[:, 1], 95) < 1.0 and np.percentile(e[:, 2], 95) < 1.0

# 2) solo orientamento: raggiunto esattamente
fk = pk.arm_forward_kinematics("R", 0.8, -0.3, 1.0, 1.2, 0.5)
ax = pk.hand_axes("R", fk)
_, info = ik.solve_arm_pose("R", None, ax["palm"], ax["fingers"])
assert info["error_palm_deg"] < 0.5 and info["error_fingers_deg"] < 0.5

# 3) specchio: il braccio sinistro con bersagli speculari da' gli angoli speculari
flip = np.array([1.0, -1.0, 1.0])
for _ in range(10):
    q = np.array([rng.uniform(-0.5, 1.2), -rng.uniform(0.1, 1.0), rng.uniform(0.3, 1.5), rng.uniform(0.3, 1.3), rng.uniform(-1, 1)])
    fk = pk.arm_forward_kinematics("R", *q)
    ax = pk.hand_axes("R", fk)
    qR, _ = ik.solve_arm_pose("R", fk["hand"], ax["palm"], ax["fingers"])
    qL, _ = ik.solve_arm_pose("L", fk["hand"] * flip, ax["palm"] * flip, ax["fingers"] * flip)
    mirrored = pk.mirror_arm_angles(dict(zip(ik.ARM5_SUFFIXES, qR)), "R")
    fkL = pk.arm_forward_kinematics("L", *[mirrored["L" + s] for s in ik.ARM5_SUFFIXES])
    fkL2 = pk.arm_forward_kinematics("L", *qL)
    assert np.linalg.norm(fkL["hand"] - fkL2["hand"]) < 2e-3
print("Specchio sinistra/destra: OK")

# 4) direzioni per nome
assert np.allclose(pose.parse_direction("avanti", "R"), [1, 0, 0])
assert np.allclose(pose.parse_direction("dentro", "R"), [0, 1, 0])
assert np.allclose(pose.parse_direction("dentro", "L"), [0, -1, 0])
assert np.allclose(pose.parse_direction("avanti+su", "R"), np.array([1, 0, 1]) / np.sqrt(2))
assert np.allclose(pose.parse_direction("0,0,2", "R"), [0, 0, 1])
assert pose.parse_direction("", "R") is None

# 5) frame da coordinate: limiti rispettati, avvisi, specchio, scrittura frames_v1
frame, infos = pose.make_frame({"R": {"point": [0.25, -0.15, 0.05], "palm": pose.parse_direction("dentro", "R"),
                                      "fingers": pose.parse_direction("avanti", "R"), "hand": 1.0}}, mirror=True, dt=1.2)
angles = dict(zip(pk.DEFAULT_JOINTS, frame["angles"]))
for j, a in angles.items():
    lo, hi = pk.JOINT_LIMITS[j]
    assert lo - 1e-9 <= a <= hi + 1e-9, (j, a)
assert abs(angles["LShoulderRoll"] + angles["RShoulderRoll"]) < 1e-9 and angles["LHand"] == angles["RHand"] == 1.0
far, far_info = pose.make_frame({"R": {"point": [0.6, -0.15, 0.1]}})
assert "warning" in far and "non raggiungibile" in far["warning"]
tablet_frame, tablet_info = pose.make_frame({"R": {"point": [0.03, 0.0, -0.05]}})
assert tablet_info["R"]["tablet_penetration"] < 0.005
print("Bersaglio nel tablet: penetrazione %.1f cm" % (100 * tablet_info["R"]["tablet_penetration"]))

path = os.path.join(tempfile.mkdtemp(), "prova_coordinate.json")
pose.append_to_gesture(path, frame)
pose.append_to_gesture(path, far)
with open(path, encoding="utf-8") as handle:
    gesture = json.load(handle)
assert gesture["format"] == "frames_v1" and len(gesture["frames"]) == 2 and gesture["joints"] == pk.DEFAULT_JOINTS
print("Gesto da coordinate scritto in", path)

# 6) CLI
assert pose.main(["--side", "R", "--point", "0.25", "-0.15", "0.05", "--palm", "dentro", "--out", path]) == 0
assert pose.main(["--side", "L", "--landmark", "mento", "--offset", "2", "0", "0"]) == 0

# 7) richieste della GUI (endpoint /retarget/pose) e punti del corpo
from retarget import landmarks as lm  # noqa: E402
for lid in lm.landmark_ids():
    for side in "LR":
        item = lm.get_landmark(lid)
        res = pose.solve_request({"side": side, "landmark": lid, "palm": item[5], "fingers": item[6]})
        assert res["ok"] and len(res["angles"]) == len(pk.DEFAULT_JOINTS)
        assert res["tablet_cm"] < 0.5, (lid, side, res["tablet_cm"])
p_r = lm.landmark_point("guancia", "R")
p_l = lm.landmark_point("guancia", "L")
assert p_r[1] < 0 < p_l[1] and abs(p_r[1] + p_l[1]) < 1e-12
res = pose.solve_request({"side": "R", "landmark": "mento", "offset_cm": {"avanti": 3, "su": -2, "esterno": 1},
                          "hand": 0.9, "base": {"RShoulderPitch": 0.4}, "mirror": True, "dt": 0.8})
assert abs(res["angles"]["RHand"] - 0.9) < 1e-9 and abs(res["angles"]["LHand"] - 0.9) < 1e-9
assert abs(res["point"][0] - 0.13) < 1e-9 and abs(res["point"][2] - 0.18) < 1e-9 and abs(res["point"][1] + 0.01) < 1e-9
print("Mento (R): scarto %.2f cm, avvisi %s" % (res["error_position_cm"], res["warnings"]))
for bad in ({"side": "X", "landmark": "mento"}, {"side": "R"}, {"side": "R", "landmark": "boh"},
            {"side": "R", "point": [1, 2]}, {"side": "R", "landmark": "mento", "palm": "storto"}):
    try:
        pose.solve_request(bad)
    except (ValueError, KeyError):
        pass
    else:
        raise AssertionError("richiesta non valida accettata: %r" % bad)
print("OK")
