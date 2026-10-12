"""
Estrazione dei keypoint dai frame video.

- DWPose: usa il DWposeDetector di easy_dwpose gia' presente nel container Process.
  Il detector disegna lo scheletro; qui serve invece il modulo interno di stima
  della posa, che restituisce (keypoints, scores). Il modulo viene cercato tra
  gli attributi del detector (il nome cambia tra le librerie derivate da DWPose);
  con --inspect lo script stampa la struttura per la diagnosi.
- MediaPipe: soluzione "Holistic" (pose 3D in metri + mani). Non e' installata
  nell'immagine: per la fase F0 si installa a mano nel container
  (pip install "mediapipe==0.10.14").
"""
import time

import numpy as np

from . import keypoints as kp


def read_video(path, max_frames=None):
    import cv2
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("Impossibile aprire il video: %s" % path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)             # BGR
        if max_frames and len(frames) >= max_frames:
            break
    cap.release()
    if not frames:
        raise ValueError("Video vuoto: %s" % path)
    h, w = frames[0].shape[:2]
    return frames, float(fps), w, h


# ---------------------------------------------------------------------------
# DWPose
# ---------------------------------------------------------------------------

_CANDIDATE_ATTRS = ("pose_estimation", "pose_estimator", "wholebody", "estimator", "model", "detector")


def _looks_like_estimator(obj):
    name = type(obj).__name__.lower()
    return callable(obj) and any(k in name for k in ("whole", "pose", "estimat"))


def find_dwpose_estimator(detector):
    for attr in _CANDIDATE_ATTRS:
        obj = getattr(detector, attr, None)
        if obj is not None and callable(obj):
            return obj, attr
    for attr, obj in vars(detector).items():
        if _looks_like_estimator(obj):
            return obj, attr
    return None, None


def describe_object(obj, depth=0, max_depth=2):
    lines = []
    pad = "  " * depth
    lines.append("%s%s" % (pad, type(obj)))
    if depth >= max_depth:
        return lines
    for attr, val in sorted(getattr(obj, "__dict__", {}).items()):
        lines.append("%s  .%s -> %s%s" % (pad, attr, type(val).__name__, " (callable)" if callable(val) else ""))
        if hasattr(val, "__dict__") and not isinstance(val, (np.ndarray,)):
            lines.extend(describe_object(val, depth + 2, max_depth))
    return lines


def _parse_estimator_output(result):
    """Accetta (keypoints, scores) o array (N,K,3); ritorna (kpts (N,K,2), scores (N,K))."""
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        kpts, scores = np.asarray(result[0], dtype=float), np.asarray(result[1], dtype=float)
        if kpts.ndim == 2:
            kpts, scores = kpts[None], scores[None]
        return kpts, scores
    arr = np.asarray(result, dtype=float)
    if arr.ndim == 3 and arr.shape[-1] >= 3:
        return arr[..., :2], arr[..., 2]
    raise ValueError("Formato di output DWPose non riconosciuto: %r" % type(result))


def extract_dwpose(frames, fps, width, height, device=None, log=print):
    import torch
    from easy_dwpose import DWposeDetector

    device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    detector = DWposeDetector(device=device)
    estimator, attr = find_dwpose_estimator(detector)
    if estimator is None:
        raise RuntimeError(
            "Modulo di stima della posa non trovato in DWposeDetector.\n"
            + "\n".join(describe_object(detector)))
    log("[DWPose] stimatore: detector.%s (%s), device=%s" % (attr, type(estimator).__name__, device))

    out = []
    t0 = time.time()
    for i, frame in enumerate(frames):
        kpts, scores = _parse_estimator_output(estimator(frame))
        if kpts.shape[0] == 0:
            out.append(None)
            continue
        # se ci sono piu' persone, tengo quella con il corpo piu' affidabile
        best = int(np.argmax(scores[:, :17].mean(axis=1)))
        k, s = kpts[best], scores[best]
        if k.max() <= 1.5:            # coordinate normalizzate -> pixel
            k = k * np.array([width, height])
        out.append((k, s))
        if (i + 1) % 25 == 0:
            log("[DWPose] %d/%d frame" % (i + 1, len(frames)))
    elapsed = time.time() - t0
    n_points = next((item[0].shape[0] for item in out if item is not None), None)
    log("[DWPose] %d frame in %.1fs, %s keypoint per persona" % (len(frames), elapsed, n_points))
    return kp.from_dwpose(out, fps, width, height), elapsed


# ---------------------------------------------------------------------------
# MediaPipe
# ---------------------------------------------------------------------------

def mediapipe_available():
    try:
        import mediapipe as mp
        return hasattr(mp, "solutions") and hasattr(mp.solutions, "holistic")
    except Exception:
        return False


def extract_mediapipe(frames, fps, width, height, log=print):
    import cv2
    import mediapipe as mp

    holistic = mp.solutions.holistic.Holistic(
        static_image_mode=False, model_complexity=1, smooth_landmarks=True,
        refine_face_landmarks=False, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    out = []
    t0 = time.time()
    try:
        for i, frame in enumerate(frames):
            res = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            out.append(kp.mediapipe_frame(res, width, height))
            if (i + 1) % 25 == 0:
                log("[MediaPipe] %d/%d frame" % (i + 1, len(frames)))
    finally:
        holistic.close()
    elapsed = time.time() - t0
    log("[MediaPipe] %d frame in %.1fs" % (len(frames), elapsed))
    return kp.from_mediapipe(out, fps), elapsed
