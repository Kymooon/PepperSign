"""Test dello script F0 con estrattori finti (DWPose e MediaPipe non sono installabili qui)."""
import os, sys, json, shutil, tempfile
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_roundtrip import make_sequence  # noqa (esegue anche i test round-trip)
from retarget import f0, extractors
from retarget.keypoints import PoseSequence

T = 75
t = np.arange(T) / 25.0
cfgs = [{"LShoulderPitch": 1.0 - 0.8 * np.sin(np.pi * x / t[-1]), "LShoulderRoll": 0.3, "LElbowYaw": -1.0,
         "LElbowRoll": -0.4 - 0.6 * np.sin(2 * np.pi * x / t[-1]) ** 2,
         "RShoulderPitch": 0.6, "RShoulderRoll": -0.2, "RElbowYaw": 1.2, "RElbowRoll": 0.9} for x in t]
seq3d = make_sequence(cfgs, offset=np.zeros(3))
rng = np.random.default_rng(1)
for k in seq3d.body: seq3d.body[k] += rng.normal(0, 0.004, seq3d.body[k].shape)   # rumore
seq3d.hands["l"][:] = np.nan
def fake_mp(frames, fps, w, h, log=print): return seq3d, 0.5
def fake_dw(frames, fps, w, h, device=None, log=print):
    s = PoseSequence(seq3d.n_frames, fps, "dwpose", False)
    for k in seq3d.body:
        s.body[k] = seq3d.body[k].copy(); s.body[k][:, 2] = np.nan
    s.body["r_wrist"][10:20] = np.nan        # polso perso per 10 frame
    return s, 1.2
f0.extract_dwpose, f0.extract_mediapipe, f0.mediapipe_available = fake_dw, fake_mp, lambda: True

tmp = tempfile.mkdtemp()
video = os.path.join(tmp, "fake.mp4")
vw = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 25, (64, 48))
for _ in range(T): vw.write(np.zeros((48, 64, 3), np.uint8))
vw.release()
out = os.path.join(tmp, "f0_out")
assert f0.main(["--video", video, "--name", "prova", "--out", out]) == 0
print(sorted(os.listdir(out)))
print(open(os.path.join(out, "report.md")).read().split("## Dettagli")[0])
