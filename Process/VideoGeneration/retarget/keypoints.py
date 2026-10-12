"""
Formato comune dei keypoint e conversione dagli output di DWPose e MediaPipe.

Sistema di coordinate comune ("camera", destrorso):
    x verso destra dell'immagine, y verso l'alto, z verso la telecamera.
Una persona di fronte alla telecamera ha quindi:
    la propria sinistra verso +x, l'alto verso +y, il davanti verso +z.

Per DWPose (2D) la z e' sconosciuta (NaN) finche' non viene stimata da depth.py.
"""
import json

import numpy as np

BODY_POINTS = [
    "nose", "l_shoulder", "r_shoulder", "l_elbow", "r_elbow",
    "l_wrist", "r_wrist", "l_hip", "r_hip",
]

HAND_POINTS = 21          # modello mano standard (0 = polso, 9 = MCP medio, 8/12/16/20 = punte)
HAND_TIPS = [8, 12, 16, 20]
HAND_MIDDLE_MCP = 9


class PoseSequence(object):
    """
    Keypoint di una persona lungo un video.
        body[name]  -> array (T, 3)   (NaN se mancante)
        body_conf   -> dict name -> (T,)
        hands["l"/"r"] -> array (T, 21, 3)
        hand_conf["l"/"r"] -> (T,)  (confidenza media della mano)
    """

    def __init__(self, n_frames, fps, source, is_3d):
        self.n_frames = int(n_frames)
        self.fps = float(fps) if fps else 25.0
        self.source = source
        self.is_3d = bool(is_3d)
        nan3 = lambda: np.full((self.n_frames, 3), np.nan)
        self.body = dict((name, nan3()) for name in BODY_POINTS)
        self.body_conf = dict((name, np.zeros(self.n_frames)) for name in BODY_POINTS)
        self.hands = {
            "l": np.full((self.n_frames, HAND_POINTS, 3), np.nan),
            "r": np.full((self.n_frames, HAND_POINTS, 3), np.nan),
        }
        self.hand_conf = {"l": np.zeros(self.n_frames), "r": np.zeros(self.n_frames)}

    @property
    def times(self):
        return np.arange(self.n_frames) / self.fps

    def detection_rate(self, name):
        return float(np.mean(np.isfinite(self.body[name][:, 0])))

    def to_npz(self, path, extra=None):
        data = {"fps": self.fps, "source": self.source, "is_3d": self.is_3d,
                "extra_json": json.dumps(extra or {})}
        for name in BODY_POINTS:
            data["body_" + name] = self.body[name]
            data["conf_" + name] = self.body_conf[name]
        for side in ("l", "r"):
            data["hand_" + side] = self.hands[side]
            data["hand_conf_" + side] = self.hand_conf[side]
        np.savez_compressed(path, **data)

    @classmethod
    def from_npz(cls, path):
        """Ricarica una sequenza salvata con to_npz. Ritorna (sequenza, extra)."""
        d = np.load(path, allow_pickle=False)
        n = d["body_" + BODY_POINTS[0]].shape[0]
        seq = cls(n, float(d["fps"]), str(d["source"]), bool(d["is_3d"]))
        for name in BODY_POINTS:
            seq.body[name] = d["body_" + name].copy()
            seq.body_conf[name] = d["conf_" + name].copy()
        for side in ("l", "r"):
            seq.hands[side] = d["hand_" + side].copy()
            seq.hand_conf[side] = d["hand_conf_" + side].copy()
        extra = json.loads(str(d["extra_json"])) if "extra_json" in d.files else {}
        return seq, extra


# ---------------------------------------------------------------------------
# DWPose (COCO-WholeBody, 133 punti; oppure 134 in ordine OpenPose con il collo)
# ---------------------------------------------------------------------------

# COCO-WholeBody: 0 naso, 5/6 spalle sx/dx, 7/8 gomiti, 9/10 polsi, 11/12 anche,
# 91-111 mano sinistra, 112-132 mano destra (sinistra/destra della persona)
_COCO_BODY = {"nose": 0, "l_shoulder": 5, "r_shoulder": 6, "l_elbow": 7, "r_elbow": 8,
              "l_wrist": 9, "r_wrist": 10, "l_hip": 11, "r_hip": 12}
_COCO_HANDS = {"l": 91, "r": 112}

# Variante a 134 punti (controlnet_aux / easy_dwpose): collo inserito in 17 e
# corpo riordinato in stile OpenPose: 0 naso, 1 collo, 2/3/4 spalla-gomito-polso dx,
# 5/6/7 spalla-gomito-polso sx, 8 anca dx, 11 anca sx; mani 92-112 (sx), 113-133 (dx)
_OPENPOSE_BODY = {"nose": 0, "r_shoulder": 2, "r_elbow": 3, "r_wrist": 4,
                  "l_shoulder": 5, "l_elbow": 6, "l_wrist": 7, "r_hip": 8, "l_hip": 11}
_OPENPOSE_HANDS = {"l": 92, "r": 113}


def dwpose_layout(n_points):
    if n_points == 133:
        return _COCO_BODY, _COCO_HANDS
    if n_points == 134:
        return _OPENPOSE_BODY, _OPENPOSE_HANDS
    raise ValueError("Numero di keypoint DWPose non previsto: %d (attesi 133 o 134)" % n_points)


def from_dwpose(frames, fps, width, height, min_score=0.3):
    """
    frames: lista (per frame) di tuple (keypoints (K,2) in pixel, scores (K,)) oppure None.
    Ritorna PoseSequence 2D (z = NaN), coordinate normalizzate sull'altezza
    dell'immagine con y verso l'alto.
    """
    seq = PoseSequence(len(frames), fps, "dwpose", is_3d=False)
    scale = float(max(height, 1))
    for t, item in enumerate(frames):
        if item is None:
            continue
        kpts, scores = item
        kpts = np.asarray(kpts, dtype=float)
        scores = np.asarray(scores, dtype=float)
        body_idx, hand_start = dwpose_layout(kpts.shape[0])

        def to_cam(p):
            return np.array([p[0] / scale, -(p[1]) / scale, np.nan])

        for name, idx in body_idx.items():
            if scores[idx] >= min_score:
                seq.body[name][t] = to_cam(kpts[idx])
                seq.body_conf[name][t] = scores[idx]
        for side, start in hand_start.items():
            hs = scores[start:start + HAND_POINTS]
            if hs.mean() >= min_score:
                for j in range(HAND_POINTS):
                    seq.hands[side][t, j] = to_cam(kpts[start + j])
                seq.hand_conf[side][t] = hs.mean()
    return seq


# ---------------------------------------------------------------------------
# MediaPipe Holistic
# ---------------------------------------------------------------------------

# Pose (33 punti): 0 naso, 11/12 spalle sx/dx, 13/14 gomiti, 15/16 polsi, 23/24 anche
_MP_BODY = {"nose": 0, "l_shoulder": 11, "r_shoulder": 12, "l_elbow": 13, "r_elbow": 14,
            "l_wrist": 15, "r_wrist": 16, "l_hip": 23, "r_hip": 24}


def mediapipe_frame(results, width, height, min_visibility=0.5):
    """
    Converte il risultato di mp.solutions.holistic per un frame in un dict:
      body: name -> (xyz camera in metri, visibilita')  da pose_world_landmarks
      hands: side -> array (21,3) da left/right_hand_landmarks
      pose2d: name -> (x,y) normalizzati, usati per associare le mani ai polsi
    MediaPipe world: x a destra, y in basso, z in profondita' -> (x, -y, -z).
    """
    out = {"body": {}, "hands": {}, "pose2d": {}}
    world = getattr(results, "pose_world_landmarks", None)
    image_pose = getattr(results, "pose_landmarks", None)
    if world is not None:
        for name, idx in _MP_BODY.items():
            lm = world.landmark[idx]
            vis = float(getattr(lm, "visibility", 1.0))
            if vis >= min_visibility:
                out["body"][name] = (np.array([lm.x, -lm.y, -lm.z]), vis)
    if image_pose is not None:
        for name, idx in _MP_BODY.items():
            lm = image_pose.landmark[idx]
            out["pose2d"][name] = np.array([lm.x, lm.y])
    aspect = float(width) / float(max(height, 1))
    for side, attr in (("l", "left_hand_landmarks"), ("r", "right_hand_landmarks")):
        hand = getattr(results, attr, None)
        if hand is None:
            continue
        pts = np.array([[lm.x * aspect, -lm.y, -lm.z * aspect] for lm in hand.landmark])
        wrist2d = np.array([hand.landmark[0].x, hand.landmark[0].y])
        out["hands"][side] = (pts, wrist2d)
    return out


def from_mediapipe(frame_dicts, fps):
    """frame_dicts: lista di output di mediapipe_frame (o None). Ritorna PoseSequence 3D."""
    seq = PoseSequence(len(frame_dicts), fps, "mediapipe", is_3d=True)
    for t, fr in enumerate(frame_dicts):
        if not fr:
            continue
        for name, (xyz, vis) in fr["body"].items():
            seq.body[name][t] = xyz
            seq.body_conf[name][t] = vis
        hands = dict(fr["hands"])
        # Controllo di coerenza: ogni mano va al polso (2D) piu' vicino
        if fr["pose2d"].get("l_wrist") is not None and fr["pose2d"].get("r_wrist") is not None:
            for side in list(hands.keys()):
                pts, w2d = hands[side]
                dl = np.linalg.norm(w2d - fr["pose2d"]["l_wrist"])
                dr = np.linalg.norm(w2d - fr["pose2d"]["r_wrist"])
                best = "l" if dl <= dr else "r"
                if best != side and best not in hands:
                    hands[best] = hands.pop(side)
        for side, (pts, _) in hands.items():
            seq.hands[side][t] = pts
            seq.hand_conf[side][t] = 1.0
    return seq
