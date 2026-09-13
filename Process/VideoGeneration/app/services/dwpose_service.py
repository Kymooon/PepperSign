import os
import cv2
import imageio.v2 as imageio
import numpy as np
from tqdm.auto import tqdm
from pathlib import Path

def load_video(input_path: str):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"Impossibile aprire il file video: {input_path}")

    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
    frames = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
    cap.release()
    return frames, fps

def save_video(frames, output_path: str, fps: int):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    writer = imageio.get_writer(
        output_path,
        format="FFMPEG",
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p"
    )

    for frame in frames:
        writer.append_data(frame)

    writer.close()

def save_thumbnail(frame, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    imageio.imwrite(output_path, frame)

def process_to_skeleton(
    detector,
    detector_lock,
    gpu_sem,
    input_path: str,
    output_video_path: str,
    output_image_path: str
):
    video, fps = load_video(input_path)

    result_frames = []
    with gpu_sem:  # limita job GPU
        with detector_lock:
            for frame in tqdm(video):
                processed_frame = detector(
                    frame,
                    output_type="np",
                    include_hands=True,
                    include_face=True
                )
                result_frames.append(processed_frame)

    save_video(result_frames, output_video_path, fps)

    if result_frames:
        mid = len(result_frames) // 2
        save_thumbnail(result_frames[mid], output_image_path)

    return {"fps": fps, "num_frames": len(result_frames)}

# --------- baseline similarity (uguale al tuo) ---------
def _frame_to_mask(frame_rgb: np.ndarray, size: int = 192):
    img = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    _, mask = cv2.threshold(img, 30, 255, cv2.THRESH_BINARY)
    return (mask > 0).astype(np.uint8)

def _mask_iou(a: np.ndarray, b: np.ndarray):
    inter = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    return 0.0 if union == 0 else inter / union

def compute_similarity_percent(template_mp4: str, try_skeleton_mp4: str, sample_fps: int = 5):
    t_frames, t_fps = load_video(template_mp4)
    u_frames, u_fps = load_video(try_skeleton_mp4)

    if len(t_frames) < 3 or len(u_frames) < 3:
        return 0.0, 0

    t_step = max(1, int(t_fps / sample_fps))
    u_step = max(1, int(u_fps / sample_fps))

    t_sample = t_frames[::t_step]
    u_sample = u_frames[::u_step]

    n = min(len(t_sample), len(u_sample))
    if n < 2:
        return 0.0, 0

    scores = []
    for i in range(n):
        scores.append(_mask_iou(_frame_to_mask(t_sample[i]), _frame_to_mask(u_sample[i])))

    score = float(np.mean(scores)) if scores else 0.0
    return score, int(round(score * 100))