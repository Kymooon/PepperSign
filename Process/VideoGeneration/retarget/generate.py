"""
Fase F1 - Generazione di un gesto Pepper da video (BETA).

Uso (dentro il container Process):
    python3 -m retarget.generate --video assets/acqua.mp4 --name acqua
    python3 -m retarget.generate --video assets/acqua.mp4 --name acqua --reuse   # riusa i keypoint gia' estratti
    python3 -m retarget.generate --video assets/acqua.mp4 --name acqua --speed 0.6

Pipeline:
    DWPose -> keypoint 2D -> profondita' stimata -> riconoscimento posa di riposo
    -> retargeting geometrico (punto di partenza)
    -> cinematica inversa sulla posizione del polso (limiti dei giunti, tablet)
    -> rotazione del polso (WristYaw) dai punti della mano
    -> apertura mani -> smoothing -> keyframe (picchi del polso inclusi) -> riposo a inizio/fine
    -> JSON frames_v1

Uscita (default /data/media/_retarget/<nome>/  ->  sul PC data\\media\\_retarget\\<nome>\\):
    <nome>_auto.json   gesto frames_v1 da copiare in data\\gestures
    check.png          video + Pepper di fronte e di lato nei keyframe
    angles.png         traiettorie dei giunti
    report.md          qualita': errore del polso, collisioni, parametri
    keypoints_dwpose.npz
"""
import argparse
import os
import sys
import warnings

import numpy as np

from . import ik
from . import pepper_kinematics as pk
from . import postprocess as pp
from .depth import estimate_depth
from .keypoints import PoseSequence
from .rest import detect_rest
from .retarget import retarget_sequence, torso_frame
from .wrist import DEFAULT_HAND_CONF, turning_points, wrist_trajectory

ARM = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll")
REST_THRESHOLD = 0.12      # rad: oltre questa distanza dalla posa di riposo si aggiunge un frame di riposo


def log(msg):
    print(msg)
    sys.stdout.flush()


def _rest_vector(side):
    return np.array([pk.REST_POSE[side + s] for s in ARM])


def human_scales(seq, depth_info):
    """Larghezza spalle e lunghezza del braccio della persona (stesse unita' dei keypoint)."""
    b = seq.body
    sw = np.nanmedian(np.linalg.norm(b["l_shoulder"] - b["r_shoulder"], axis=1))
    arm = {}
    for side in ("l", "r"):
        if depth_info:
            arm[side] = depth_info[side + "_upper_arm"] + depth_info[side + "_forearm"]
        else:
            up = np.linalg.norm(b[side + "_elbow"] - b[side + "_shoulder"], axis=1)
            fo = np.linalg.norm(b[side + "_wrist"] - b[side + "_elbow"], axis=1)
            arm[side] = np.nanpercentile(up, 90) + np.nanpercentile(fo, 90)
    return float(sw), arm


def generate(seq, name, speed=0.8, mirror=False, epsilon=0.08, max_keyframes=20,
             smooth=9, rest_ends=True, use_ik=True, log=log, use_wrist=True, wrist_flip=False,
             hand_conf=DEFAULT_HAND_CONF, smooth_hand=pp.DEFAULT_FAST_WINDOW, wrist_gain=1.0):
    """Ritorna (gesture_dict, dense_raw, dense_clean, keys, stats)."""
    depth_info = estimate_depth(seq) if not seq.is_3d else {}
    rest = detect_rest(seq)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw, _ = retarget_sequence(seq, mirror=mirror)

    sw_h, arm_h = human_scales(seq, depth_info)
    k_lateral = 2 * pk.SHOULDER_OFFSET_Y / sw_h
    pepper_arm = pk.UPPER_ARM_LENGTH + pk.LOWER_ARM_LENGTH
    b = seq.body
    T = seq.n_frames
    stats = {"frontal_error_cm": [], "error_3d_cm": [], "geo_frontal_error_cm": [],
             "rest_frames": {}, "active_frames": {}, "wrist": {}}

    for human_side, robot_side in (("l", "L"), ("r", "R")):
        if mirror:
            robot_side = "R" if robot_side == "L" else "L"
        k_arm = pepper_arm / arm_h[human_side]
        prev = None
        n_rest = 0
        for t in range(T):
            names = [robot_side + s for s in ARM]
            if rest[human_side][t]:
                for n, v in zip(names, _rest_vector(robot_side)):
                    raw[n][t] = v
                raw[robot_side + "Hand"][t] = pk.REST_POSE[robot_side + "Hand"]
                prev = None
                n_rest += 1
                continue
            if not use_ik:
                continue
            frame = torso_frame(b["l_shoulder"][t], b["r_shoulder"][t], b["l_hip"][t], b["r_hip"][t])
            if frame is None:
                continue
            origin, R = frame
            s = R.T.dot(b[human_side + "_shoulder"][t] - origin)
            w = R.T.dot(b[human_side + "_wrist"][t] - origin)
            if not (np.all(np.isfinite(s)) and np.all(np.isfinite(w))):
                continue
            if mirror:
                s, w = s * np.array([1, -1, 1]), w * np.array([1, -1, 1])
            target = ik.target_from_human(robot_side, s, w, k_lateral, k_arm)

            q_geo = np.array([raw[n][t] for n in names])
            if not np.isfinite(q_geo[2]):                      # ElbowYaw indefinito (gomito dritto)
                q_geo[2] = prev[2] if prev is not None else pk.REST_POSE[names[2]]
            q_geo = np.array([pk.clamp_to_limits(n, v) for n, v in zip(names, q_geo)])
            geo_wrist = pk.arm_forward_kinematics(robot_side, *q_geo)["wrist"]
            q, info = ik.solve_arm(robot_side, target, prev if prev is not None else q_geo, q_ref=q_geo)
            for n, v in zip(names, q):
                raw[n][t] = v
            prev = q
            stats["frontal_error_cm"].append(100 * info["error_frontal"])
            stats["error_3d_cm"].append(100 * info["error_3d"])
            stats["geo_frontal_error_cm"].append(100 * float(np.linalg.norm((geo_wrist - target)[1:])))
        stats["rest_frames"][robot_side] = n_rest
        stats["active_frames"][robot_side] = T - n_rest

        # Rotazione del polso dai punti della mano (con gli angoli del braccio appena calcolati)
        if use_wrist:
            arm = np.column_stack([raw[robot_side + s] for s in ARM])
            wrist, winfo = wrist_trajectory(seq, human_side, robot_side, arm, rest[human_side],
                                            mirror=mirror, min_conf=hand_conf, flip=wrist_flip)
            raw[robot_side + "WristYaw"] = wrist
            stats["wrist"][robot_side] = {"estimated": winfo["estimated"], "hand_frames": winfo["frames"]}

    clean = pp.process_trajectories(raw, smooth_window=smooth, fast_window=smooth_hand)
    times = np.arange(T) / seq.fps
    mandatory = []
    if use_wrist:
        for side in "LR":
            if stats["wrist"].get(side, {}).get("estimated", 0):
                if wrist_gain != 1.0:
                    # amplifica solo le oscillazioni rapide, non la rotazione media
                    name = side + "WristYaw"
                    slow = pp.savgol(clean[name], 15)
                    lo, hi = pk.JOINT_LIMITS[name]
                    clean[name] = np.clip(slow + wrist_gain * (clean[name] - slow), lo, hi)
                pts = turning_points(clean[side + "WristYaw"], times)
                stats["wrist"][side]["turning_points"] = len(pts)
                stats["wrist"][side]["range"] = (float(np.min(clean[side + "WristYaw"])),
                                                 float(np.max(clean[side + "WristYaw"])))
                mandatory += pts
    keys = pp.select_keyframes(clean, times, epsilon=epsilon, max_keyframes=max_keyframes,
                               mandatory=sorted(set(mandatory)))
    frames = pp.keyframes_to_frames(clean, times, keys, speed=speed, first_dt=1.5,
                                    joint_max_velocity=pp.JOINT_MAX_VELOCITY)

    if rest_ends:
        frames = add_rest_ends(frames)

    # Controllo collisioni con il tablet sui keyframe (dopo smoothing e clamp)
    collisions = 0
    for fr in frames:
        a = dict(zip(pk.DEFAULT_JOINTS, fr["angles"]))
        pen = max(ik.tablet_collision(side, [a[side + s] for s in ARM]) for side in "LR")
        if pen > 0.0:
            fr["warning"] = "tablet %.1fcm" % (100 * pen)
            collisions += 1
    stats["tablet_keyframes"] = collisions

    gesture_id = "%s_auto" % name
    meta = {
        "method": "F1: geometrico + IK posizione polso",
        "model": "URDF pepper_description",
        "extractor": seq.source, "mirror": mirror, "speed": speed, "epsilon": epsilon,
        "smooth_window": smooth, "rest_ends": rest_ends, "ik": use_ik,
        "wrist_yaw": ("stimato dai punti della mano (flip=%s, conf>=%.2f)" % (wrist_flip, hand_conf))
                     if use_wrist else "posa di riposo",
        "smooth_hand_window": smooth_hand, "wrist_gain": wrist_gain, "head": "posa di riposo",
        "scales": {"k_lateral": round(k_lateral, 4), "human_shoulder_width": round(sw_h, 4)},
    }
    gesture = pp.build_frames_v1(gesture_id, gesture_id, frames, meta)
    return gesture, raw, clean, keys, stats


def add_rest_ends(frames, dt_rest=1.5, max_velocity=1.5):
    """Aggiunge un keyframe di riposo all'inizio e alla fine se il gesto non parte/finisce gia' a riposo."""
    rest = [float(pk.REST_POSE[j]) for j in pk.DEFAULT_JOINTS]

    def far(angles):
        return max(abs(a - r) for a, r in zip(angles, rest)) > REST_THRESHOLD

    out = list(frames)
    if out and far(out[0]["angles"]):
        first = dict(out[0])
        delta = max(abs(a - r) for a, r in zip(first["angles"], rest))
        first["dt"] = round(max(first["dt"], delta / max_velocity, 0.6), 3)
        out = [{"angles": rest, "dt": dt_rest, "source_time": 0.0, "note": "riposo iniziale"}, first] + out[1:]
    if out and far(out[-1]["angles"]):
        delta = max(abs(a - r) for a, r in zip(out[-1]["angles"], rest))
        out.append({"angles": rest, "dt": round(max(delta / max_velocity, 1.0), 3),
                    "source_time": out[-1].get("source_time", 0.0), "note": "riposo finale"})
    return out


def write_report(path, args, gesture, stats, seq):
    fe = np.array(stats["frontal_error_cm"])
    ge = np.array(stats["geo_frontal_error_cm"])
    e3 = np.array(stats["error_3d_cm"])
    total = sum(f["dt"] for f in gesture["frames"])
    lines = [
        "# Gesto generato da video (BETA F1): %s" % args.name, "",
        "Video: `%s` - estrattore: %s - %d frame a %.1f fps" % (args.video, seq.source, seq.n_frames, seq.fps), "",
        "| Voce | Valore |", "|---|---|",
        "| Keyframe | %d |" % len(gesture["frames"]),
        "| Durata del gesto | %.2f s (velocita' %.2f) |" % (total, args.speed),
        "| Frame a riposo (braccio sx / dx di Pepper) | %d / %d |" % (stats["rest_frames"].get("L", 0), stats["rest_frames"].get("R", 0)),
    ]
    if fe.size:
        lines += [
            "| Errore del polso visto di fronte, solo direzioni (mediano / max) | %.1f / %.1f cm |" % (np.median(ge), ge.max()),
            "| Errore del polso visto di fronte, con IK (mediano / max) | %.1f / %.1f cm |" % (np.median(fe), fe.max()),
            "| Errore 3D con IK, profondita' inclusa (mediano / max) | %.1f / %.1f cm |" % (np.median(e3), e3.max()),
        ]
    for side, label in (("R", "dx"), ("L", "sx")):
        w = stats.get("wrist", {}).get(side)
        if not w:
            continue
        if w.get("estimated"):
            lo, hi = w.get("range", (0.0, 0.0))
            lines.append("| Polso %s (WristYaw): frame stimati / picchi tenuti come keyframe / escursione | %d / %d / %.0f..%.0f gradi |"
                         % (label, w["estimated"], w.get("turning_points", 0), np.degrees(lo), np.degrees(hi)))
        else:
            lines.append("| Polso %s (WristYaw) | non stimato (mano poco visibile: %d frame affidabili) |" % (label, w["hand_frames"]))
    lines += ["| Keyframe con possibile contatto con il tablet | %d |" % stats["tablet_keyframes"], "",
              "## Keyframe", "", "| # | dt (s) | tempo video (s) | nota |", "|---|---|---|---|"]
    for i, f in enumerate(gesture["frames"]):
        lines.append("| %d | %.2f | %.2f | %s |" % (i + 1, f["dt"], f.get("source_time", 0), f.get("warning", f.get("note", ""))))
    if getattr(args, "no_wrist", False):
        lines += ["", "Il polso (WristYaw) e la testa restano nella posa di riposo (--no-wrist)."]
    else:
        lines += ["", "Polso (WristYaw): stimato dalla rotazione della mano nel video (beta). Il verso della "
                  "rotazione va confermato sul robot: se e' al contrario, rigenera con --wrist-flip. "
                  "La testa resta nella posa di riposo."]
    lines += ["Errori e collisioni sono calcolati sul modello semplificato di Pepper (da verificare sul robot)."]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv=None):
    from .extractors import read_video, extract_dwpose
    from .f0 import save_plot
    from .visualize import save_check_image

    ap = argparse.ArgumentParser(description="PepperSign F1: video -> gesto Pepper (beta)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--reuse", action="store_true", help="riusa keypoints_dwpose.npz se presente (anche da F0)")
    ap.add_argument("--speed", type=float, default=0.8, help="default 0.8 = 20%% piu' lento del video")
    ap.add_argument("--mirror", action="store_true")
    ap.add_argument("--epsilon", type=float, default=0.08)
    ap.add_argument("--max-keyframes", type=int, default=20)
    ap.add_argument("--smooth", type=int, default=9)
    ap.add_argument("--no-ik", action="store_true", help="solo retargeting geometrico (come F0)")
    ap.add_argument("--no-rest-ends", action="store_true", help="non aggiungere il riposo a inizio/fine")
    ap.add_argument("--no-wrist", action="store_true", help="polso fermo nella posa di riposo (come prima)")
    ap.add_argument("--wrist-flip", action="store_true", help="sceglie l'altro verso di rotazione del polso")
    ap.add_argument("--hand-conf", type=float, default=DEFAULT_HAND_CONF,
                    help="confidenza minima della mano per stimare il polso (default 0.5)")
    ap.add_argument("--wrist-gain", type=float, default=1.0,
                    help="amplifica le oscillazioni del polso (es. 1.5 = +50%%), default 1 = come nel video")
    ap.add_argument("--smooth-hand", type=int, default=pp.DEFAULT_FAST_WINDOW,
                    help="finestra di smoothing per polso e mano (frame, default 5)")
    args = ap.parse_args(argv)

    args.name = args.name or os.path.splitext(os.path.basename(args.video))[0]
    data_dir = os.environ.get("PEPPERSIGN_DATA_DIR", os.path.join(os.path.expanduser("~"), "PepperSignData"))
    out_dir = args.out or os.path.join(data_dir, "_retarget", args.name)
    os.makedirs(out_dir, exist_ok=True)

    frames_bgr, fps, width, height = read_video(args.video)
    log("[VIDEO] %s: %d frame, %.1f fps, %dx%d" % (args.video, len(frames_bgr), fps, width, height))

    npz = os.path.join(out_dir, "keypoints_dwpose.npz")
    f0_npz = os.path.join(data_dir, "_retarget_f0", args.name, "keypoints_dwpose.npz")
    if args.reuse and not os.path.exists(npz) and os.path.exists(f0_npz):
        npz = f0_npz
    if args.reuse and os.path.exists(npz):
        seq, _ = PoseSequence.from_npz(npz)
        log("[DWPose] keypoint riusati da %s" % npz)
    else:
        seq, elapsed = extract_dwpose(frames_bgr, fps, width, height, log=log)
        seq.to_npz(os.path.join(out_dir, "keypoints_dwpose.npz"), {"elapsed_s": elapsed})

    gesture, raw, clean, keys, stats = generate(
        seq, args.name, speed=args.speed, mirror=args.mirror, epsilon=args.epsilon,
        max_keyframes=args.max_keyframes, smooth=args.smooth,
        rest_ends=not args.no_rest_ends, use_ik=not args.no_ik,
        use_wrist=not args.no_wrist, wrist_flip=args.wrist_flip,
        hand_conf=args.hand_conf, smooth_hand=args.smooth_hand, wrist_gain=args.wrist_gain)

    json_path = os.path.join(out_dir, gesture["gesture_id"] + ".json")
    pp.write_json(json_path, gesture)
    times = np.arange(seq.n_frames) / seq.fps
    save_plot(os.path.join(out_dir, "angles.png"), "%s - F1 (%d keyframe)" % (args.name, len(keys)),
              times, raw, clean, keys)
    save_check_image(os.path.join(out_dir, "check.png"), gesture, seq, frames_bgr,
                     title="%s - gesto generato (beta)" % args.name)
    write_report(os.path.join(out_dir, "report.md"), args, gesture, stats, seq)

    fe = stats["frontal_error_cm"]
    log("[F1] %d keyframe, %.1fs, errore polso di fronte mediano %.1f cm, contatti tablet: %d"
        % (len(gesture["frames"]), sum(f["dt"] for f in gesture["frames"]),
           float(np.median(fe)) if fe else float("nan"), stats["tablet_keyframes"]))
    for side in ("R", "L"):
        w = stats.get("wrist", {}).get(side)
        if w and w.get("estimated"):
            lo, hi = w.get("range", (0.0, 0.0))
            log("[F1] polso %s: %d frame stimati, %d picchi come keyframe, escursione %.0f..%.0f gradi"
                % ("dx" if side == "R" else "sx", w["estimated"], w.get("turning_points", 0), np.degrees(lo), np.degrees(hi)))
    log("[F1] gesto: %s" % json_path)
    log("[F1] per provarlo: copia il file in data\\gestures, poi nella GUI 'Ricarica' (o 'Carica sequenza')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
