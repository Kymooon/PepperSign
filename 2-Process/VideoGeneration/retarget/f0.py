"""
Fase F0 - fattibilita' della generazione automatica dei gesti da video (BETA).

Uso (dentro il container Process):
    python3 -m retarget.f0 --video assets/acqua.mp4 --name acqua
    python3 -m retarget.f0 --video assets/acqua.mp4 --name acqua --extractors dwpose
    python3 -m retarget.f0 --inspect          # struttura del detector DWPose (diagnosi)

Per ogni estrattore disponibile (DWPose 2D + profondita' stimata, MediaPipe 3D):
    - keypoint grezzi                  keypoints_<estrattore>.npz
    - angoli per ogni frame            angles_<estrattore>.csv
    - grafico delle traiettorie        angles_<estrattore>.png
    - gesto in formato GUI             <nome>_auto_<estrattore>.json   (frames_v1)
e un confronto tra gli estrattori in report.md.
Uscita di default: /data/media/_retarget_f0/<nome>/  ->  sul PC: data\\media\\_retarget_f0\\<nome>\\
"""
import argparse
import csv
import json
import os
import sys
import time

import numpy as np

from . import pepper_kinematics as pk
from . import postprocess as pp
from .depth import estimate_depth
from .extractors import (read_video, extract_dwpose, extract_mediapipe,
                         mediapipe_available, describe_object)
from .keypoints import PoseSequence
from .retarget import retarget_sequence

ARM_JOINTS = [j for j in pk.DEFAULT_JOINTS if not j.startswith("Head")]


def log(msg):
    print(msg)
    sys.stdout.flush()


def save_angles_csv(path, times, raw, clean):
    with open(path, "w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["time"] + ["raw_" + j for j in ARM_JOINTS] + ["clean_" + j for j in ARM_JOINTS])
        for t in range(len(times)):
            w.writerow(["%.3f" % times[t]]
                       + ["" if not np.isfinite(raw[j][t]) else "%.4f" % raw[j][t] for j in ARM_JOINTS]
                       + ["%.4f" % clean[j][t] for j in ARM_JOINTS])


def save_plot(path, title, times, raw, clean, keys):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        log("[PLOT] matplotlib non disponibile: %s" % exc)
        return False
    fig, axes = plt.subplots(6, 2, figsize=(12, 13), sharex=True)
    for col, side in enumerate("LR"):
        for row, suffix in enumerate(pk.ARM_JOINT_SUFFIXES):
            name = side + suffix
            ax = axes[row][col]
            ax.plot(times, raw[name], ".", markersize=3, alpha=0.5, label="grezzo")
            ax.plot(times, clean[name], "-", linewidth=1.5, label="filtrato")
            ax.plot(times[keys], clean[name][keys], "o", markersize=5, label="keyframe")
            lo, hi = pk.JOINT_LIMITS[name]
            ax.axhline(lo, color="grey", linewidth=0.5, linestyle=":")
            ax.axhline(hi, color="grey", linewidth=0.5, linestyle=":")
            ax.set_ylabel(name, fontsize=8)
            ax.tick_params(labelsize=7)
    axes[0][0].legend(fontsize=7, loc="upper right")
    axes[-1][0].set_xlabel("tempo (s)")
    axes[-1][1].set_xlabel("tempo (s)")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return True


def run_extractor(label, seq, elapsed, args, out_dir, times):
    """Retargeting + output a partire dai keypoint (2D grezzi o 3D)."""
    info = {"extractor": label, "elapsed_s": round(elapsed, 2), "n_frames": seq.n_frames, "fps": seq.fps}
    info["detection_rate"] = dict((n, round(seq.detection_rate(n), 3)) for n in
                                  ("l_shoulder", "r_shoulder", "l_elbow", "r_elbow", "l_wrist", "r_wrist", "l_hip", "r_hip"))
    info["hand_detection_rate"] = dict((s, round(float(np.mean(seq.hand_conf[s] > 0)), 3)) for s in ("l", "r"))
    if not seq.is_3d:
        info["depth"] = dict((k, round(float(v), 4)) for k, v in estimate_depth(seq).items())

    raw, direction_error = retarget_sequence(seq, mirror=args.mirror)
    clean = pp.process_trajectories(raw, smooth_window=args.smooth)
    keys = pp.select_keyframes(clean, times, epsilon=args.epsilon, max_keyframes=args.max_keyframes)
    frames = pp.keyframes_to_frames(clean, times, keys, speed=args.speed)

    info["keyframes"] = len(keys)
    info["duration_video_s"] = round(float(times[-1]), 2)
    info["duration_gesture_s"] = round(float(sum(f["dt"] for f in frames)), 2)
    info["retarget_rate"] = dict((j, round(float(np.mean(np.isfinite(raw[j]))), 3)) for j in ARM_JOINTS)
    info["limit_direction_error_deg"] = dict(
        (s, round(float(np.nanmean(direction_error[s])), 1) if np.isfinite(direction_error[s]).any() else None)
        for s in "LR")

    gesture_id = "%s_auto_%s" % (args.name, label)
    meta = {"extractor": label, "video": os.path.basename(args.video), "mirror": args.mirror,
            "speed": args.speed, "epsilon": args.epsilon, "smooth_window": args.smooth,
            "wrist_and_head": "posa di riposo (F0)"}
    data = pp.build_frames_v1(gesture_id, gesture_id, frames, meta)
    json_path = os.path.join(out_dir, gesture_id + ".json")
    pp.write_json(json_path, data)
    save_angles_csv(os.path.join(out_dir, "angles_%s.csv" % label), times, raw, clean)
    save_plot(os.path.join(out_dir, "angles_%s.png" % label),
              "%s - %s (%d keyframe)" % (args.name, label, len(keys)), times, raw, clean, keys)
    log("[%s] %d keyframe, gesto di %.1fs -> %s" % (label, len(keys), info["duration_gesture_s"], json_path))
    return info, clean


def compare(clean_by_extractor):
    labels = list(clean_by_extractor.keys())
    if len(labels) < 2:
        return None
    a, b = clean_by_extractor[labels[0]], clean_by_extractor[labels[1]]
    rows = {}
    for j in ARM_JOINTS:
        if j.endswith("Hand"):
            rows[j] = round(float(np.mean(np.abs(a[j] - b[j]))), 3)
        else:
            rows[j] = round(float(np.degrees(np.mean(np.abs(a[j] - b[j])))), 1)
    return {"pair": labels, "mean_abs_diff": rows}


def write_report(path, args, infos, comparison):
    lines = ["# F0 - Report retargeting: %s" % args.name, "",
             "Video: `%s`  " % args.video,
             "Parametri: mirror=%s, speed=%s, epsilon=%s rad, smoothing=%s frame" % (args.mirror, args.speed, args.epsilon, args.smooth),
             ""]
    lines += ["| Voce | " + " | ".join(i["extractor"] for i in infos) + " |",
              "|---|" + "---|" * len(infos)]

    def row(label, fn):
        lines.append("| %s | %s |" % (label, " | ".join(str(fn(i)) for i in infos)))

    row("Tempo di estrazione (s)", lambda i: i["elapsed_s"])
    row("Frame / fps", lambda i: "%d / %.1f" % (i["n_frames"], i["fps"]))
    row("Polsi rilevati (sx / dx)", lambda i: "%.0f%% / %.0f%%" % (100 * i["detection_rate"]["l_wrist"], 100 * i["detection_rate"]["r_wrist"]))
    row("Anche rilevate (sx / dx)", lambda i: "%.0f%% / %.0f%%" % (100 * i["detection_rate"]["l_hip"], 100 * i["detection_rate"]["r_hip"]))
    row("Mani rilevate (sx / dx)", lambda i: "%.0f%% / %.0f%%" % (100 * i["hand_detection_rate"]["l"], 100 * i["hand_detection_rate"]["r"]))
    row("Keyframe", lambda i: i["keyframes"])
    row("Durata video / gesto (s)", lambda i: "%s / %s" % (i["duration_video_s"], i["duration_gesture_s"]))
    row("Errore medio per limiti di Pepper (sx / dx, gradi)",
        lambda i: "%s / %s" % (i["limit_direction_error_deg"]["L"], i["limit_direction_error_deg"]["R"]))
    lines.append("")
    if comparison:
        lines += ["## Differenza media tra %s e %s" % tuple(comparison["pair"]), "",
                  "(gradi; per le mani: scala 0-1)", "", "| Giunto | Differenza |", "|---|---|"]
        for j, v in comparison["mean_abs_diff"].items():
            lines.append("| %s | %s |" % (j, v))
        lines.append("")
    lines += ["## Dettagli", "", "```json", json.dumps(infos, indent=2, ensure_ascii=False), "```", ""]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description="PepperSign F0: video -> gesto Pepper (beta)")
    ap.add_argument("--video", help="percorso del video (es. assets/acqua.mp4)")
    ap.add_argument("--name", help="nome del gesto (default: nome del file)")
    ap.add_argument("--extractors", default="dwpose,mediapipe", help="dwpose,mediapipe")
    ap.add_argument("--out", default=None, help="cartella di uscita")
    ap.add_argument("--mirror", action="store_true", help="specchia sinistra/destra")
    ap.add_argument("--speed", type=float, default=1.0, help="<1 piu' lento, >1 piu' veloce")
    ap.add_argument("--epsilon", type=float, default=0.08, help="tolleranza keyframe (rad)")
    ap.add_argument("--max-keyframes", type=int, default=20)
    ap.add_argument("--smooth", type=int, default=9, help="finestra smoothing (frame)")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--inspect", action="store_true", help="stampa la struttura del detector DWPose")
    args = ap.parse_args(argv)

    if args.inspect:
        from easy_dwpose import DWposeDetector
        det = DWposeDetector(device="cpu")
        print("\n".join(describe_object(det, max_depth=3)))
        return 0
    if not args.video:
        ap.error("--video obbligatorio")

    args.name = args.name or os.path.splitext(os.path.basename(args.video))[0]
    data_dir = os.environ.get("PEPPERSIGN_DATA_DIR", os.path.join(os.path.expanduser("~"), "PepperSignData"))
    out_dir = args.out or os.path.join(data_dir, "_retarget_f0", args.name)
    os.makedirs(out_dir, exist_ok=True)

    frames, fps, width, height = read_video(args.video, args.max_frames)
    log("[VIDEO] %s: %d frame, %.1f fps, %dx%d" % (args.video, len(frames), fps, width, height))

    # 1) estrazione dei keypoint (salvati in keypoints_<estrattore>.npz)
    for label in [e.strip() for e in args.extractors.split(",") if e.strip()]:
        try:
            if label == "dwpose":
                seq, elapsed = extract_dwpose(frames, fps, width, height, log=log)
            elif label == "mediapipe":
                if not mediapipe_available():
                    log("[MediaPipe] non disponibile (modulo mediapipe.solutions.holistic): salto.\n"
                        "  Vedi le istruzioni F0 per eseguirlo in un container temporaneo.")
                    continue
                seq, elapsed = extract_mediapipe(frames, fps, width, height, log=log)
            else:
                log("[ERRORE] estrattore sconosciuto: %s" % label)
                continue
            seq.to_npz(os.path.join(out_dir, "keypoints_%s.npz" % label), {"elapsed_s": elapsed})
        except Exception as exc:
            import traceback
            log("[ERRORE] %s: %s" % (label, exc))
            traceback.print_exc()

    # 2) retargeting e report su TUTTI i keypoint presenti nella cartella:
    #    cosi' DWPose e MediaPipe possono essere eseguiti in comandi separati
    #    e confrontati alla fine.
    infos, cleans = [], {}
    for label in ("dwpose", "mediapipe"):
        path = os.path.join(out_dir, "keypoints_%s.npz" % label)
        if not os.path.exists(path):
            continue
        seq, extra = PoseSequence.from_npz(path)
        seq_times = np.arange(seq.n_frames) / seq.fps
        info, clean = run_extractor(label, seq, float(extra.get("elapsed_s", 0.0)), args, out_dir, seq_times)
        infos.append(info)
        cleans[label] = clean

    if not infos:
        log("[F0] nessun estrattore ha prodotto risultati")
        return 1
    write_report(os.path.join(out_dir, "report.md"), args, infos, compare(cleans))
    log("[F0] risultati in %s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
