"""Test del modello cinematico URDF di Pepper e dello script di confronto con il robot."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from retarget import model_check, pepper_kinematics as pk  # noqa: E402

# 1) posa zero (braccio dritto in avanti): valori attesi dall'URDF
fk = pk.arm_forward_kinematics("R", 0.0, 0.0, 0.0, 0.0, 0.0)
t = pk.ELBOW_PITCH_OFFSET
expected_elbow = np.array([-0.057 + 0.1812, -0.14974 - 0.015, 0.08682 + 0.00013])
expected_wrist = expected_elbow + 0.15 * np.array([np.cos(t), 0.0, -np.sin(t)])
assert np.allclose(fk["elbow"], expected_elbow, atol=1e-9), fk["elbow"]
assert np.allclose(fk["wrist"], expected_wrist, atol=1e-9), fk["wrist"]
print("Posa zero, polso dx (mm):", np.round(1000 * fk["wrist"], 1))

# 2) simmetria: braccio sinistro = speculare del destro (y -> -y, angoli di roll/yaw con segno opposto)
rng = np.random.default_rng(1)
for _ in range(200):
    sp, sr, ey, er, wy = rng.uniform(-1.5, 1.5), rng.uniform(0.01, 1.5), rng.uniform(-2, 2), rng.uniform(-1.5, -0.01), rng.uniform(-1.8, 1.8)
    L = pk.arm_forward_kinematics("L", sp, sr, ey, er, wy)
    R = pk.arm_forward_kinematics("R", sp, -sr, -ey, -er, -wy)
    for k in ("elbow", "wrist", "hand"):
        assert np.allclose(L[k] * [1, -1, 1], R[k], atol=1e-9), k
print("Simmetria sinistra/destra: OK")

# 3) lunghezze dei segmenti costanti
for _ in range(200):
    q = [rng.uniform(-2, 2), -rng.uniform(0.01, 1.5), rng.uniform(-2, 2), rng.uniform(0.01, 1.5), rng.uniform(-1.8, 1.8)]
    f = pk.arm_forward_kinematics("R", *q)
    assert abs(np.linalg.norm(f["elbow"] - f["shoulder"]) - np.hypot(0.1812, np.hypot(0.015, 0.00013))) < 1e-9
    assert abs(np.linalg.norm(f["wrist"] - f["elbow"]) - 0.15) < 1e-9
    assert abs(np.linalg.norm(f["hand"] - f["wrist"]) - np.hypot(0.0695, 0.0303)) < 1e-9
print("Lunghezze dei segmenti: OK")

# 4) model_check: campioni generati con il modello URDF -> errore nullo per "urdf"
samples = []
for _ in range(20):
    q = [rng.uniform(-1, 1.5), -rng.uniform(0.1, 1.2), rng.uniform(0.3, 1.8), rng.uniform(0.2, 1.4), rng.uniform(-1, 1)]
    f = pk.arm_forward_kinematics("R", *q)
    samples.append({"angles": dict(("R" + j, v) for j, v in zip(model_check.ARM, q)),
                    "positions": {"RElbowYaw": list(f["elbow"]) + [0, 0, 0], "RWristYaw": list(f["wrist"]), "RArm": list(f["hand"])}})
res = model_check.compare(samples)
print(model_check.format_report(res))
assert max(res["urdf"]["wrist"]) < 1e-9 and max(res["urdf"]["hand"]) < 1e-9
assert np.median(res["semplificato"]["wrist"]) > 0.01
print("OK")
