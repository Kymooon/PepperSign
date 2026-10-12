"""
Immagine di controllo: per alcuni keyframe mostra il frame del video con i
keypoint e la posa risultante di Pepper vista di fronte e di lato.
Serve a valutare il gesto a colpo d'occhio prima di provarlo sul robot.

Convenzioni dei disegni:
  - vista frontale come se si guardasse Pepper di fronte: il braccio destro del
    robot (rosso) appare a sinistra, come il braccio destro del segnante nel video;
  - vista laterale: avanti verso destra;
  - riquadro tratteggiato = tablet (approssimato), cerchio = testa;
  - segmento verde = lato del pollice della mano (rotazione del polso):
    nel video la linea delle nocche (mignolo -> indice), su Pepper l'asse
    lato-pollice della mano.
"""
import numpy as np

from . import pepper_kinematics as pk
from .ik import TABLET_BOX_MIN, TABLET_BOX_MAX
from .wrist import KNUCKLE_INDEX, KNUCKLE_PINKY, THUMB_AXIS

COLORS = {"L": "tab:blue", "R": "tab:red", "l": "tab:blue", "r": "tab:red"}


def _draw_pepper(ax, angles, view):
    fk = pk.forward_kinematics_pose(angles)
    i = 1 if view == "front" else 0
    for side in ("L", "R"):
        pts = [fk[side][k] for k in ("shoulder", "elbow", "wrist", "hand")]
        ax.plot([p[i] for p in pts], [p[2] for p in pts], "-o", color=COLORS[side], lw=2, ms=3)
        # lato del pollice (orientamento della mano dato da WristYaw)
        thumb = fk[side]["hand"] + 0.05 * fk[side]["r_hand"].dot(THUMB_AXIS[side])
        ax.plot([fk[side]["hand"][i], thumb[i]], [fk[side]["hand"][2], thumb[2]], "-", color="tab:green", lw=2)
    z_sh = pk.SHOULDER_OFFSET_Z
    if view == "front":
        ax.plot([-pk.SHOULDER_OFFSET_Y, pk.SHOULDER_OFFSET_Y], [z_sh, z_sh], "k-", lw=3)
        lo, hi = TABLET_BOX_MIN, TABLET_BOX_MAX
        ax.add_patch(_rect(lo[1], lo[2], hi[1] - lo[1], hi[2] - lo[2]))
        ax.plot(0, z_sh + 0.13, "o", ms=16, mfc="none", color="k")
    else:
        x_sh = pk.SHOULDER_OFFSET_X
        ax.plot([x_sh, x_sh], [z_sh - 0.3, z_sh], "k-", lw=3)
        lo, hi = TABLET_BOX_MIN, TABLET_BOX_MAX
        ax.add_patch(_rect(lo[0], lo[2], hi[0] - lo[0], hi[2] - lo[2]))
        ax.plot(-0.038, z_sh + 0.13, "o", ms=16, mfc="none", color="k")   # testa (HeadYaw a x = -0.038)
    ax.set_xlim(-0.42, 0.42)
    ax.set_ylim(-0.35, 0.42)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=6)


def _rect(x, y, w, h):
    import matplotlib.pyplot as plt
    return plt.Rectangle((x, y), w, h, fill=False, ls="--", color="grey")


def save_check_image(path, gesture, seq=None, video_frames=None, n_cols=6, title=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    frames = gesture["frames"]
    joints = gesture["joints"]
    idx = np.unique(np.linspace(0, len(frames) - 1, min(n_cols, len(frames))).round().astype(int))
    rows = 3 if video_frames is not None else 2
    fig, axes = plt.subplots(rows, len(idx), figsize=(3.1 * len(idx), 3.0 * rows), squeeze=False)
    for c, k in enumerate(idx):
        fr = frames[k]
        angles = dict(zip(joints, fr["angles"]))
        r = 0
        if video_frames is not None:
            ax = axes[0][c]
            t = int(round(fr.get("source_time", 0.0) * (seq.fps if seq else 25.0)))
            t = max(0, min(t, len(video_frames) - 1))
            img = video_frames[t]
            ax.imshow(img[:, :, ::-1])            # BGR -> RGB
            H = img.shape[0]
            if seq is not None and not seq.is_3d:
                for side in ("l", "r"):
                    pts = [seq.body[side + "_" + n][t] for n in ("shoulder", "elbow", "wrist")]
                    ax.plot([p[0] * H for p in pts], [-p[1] * H for p in pts], "-o", color=COLORS[side], lw=2, ms=3)
                    hand = seq.hands[side][t]
                    if np.all(np.isfinite(hand[[KNUCKLE_INDEX, KNUCKLE_PINKY], :2])):
                        kn = hand[[KNUCKLE_PINKY, KNUCKLE_INDEX]]
                        ax.plot(kn[:, 0] * H, -kn[:, 1] * H, "-", color="tab:green", lw=2)
            ax.set_title("kf %d - video %.2fs" % (k, fr.get("source_time", 0.0)), fontsize=8)
            ax.axis("off")
            r = 1
        _draw_pepper(axes[r][c], angles, "front")
        axes[r][c].set_title("Pepper di fronte" + (" - " + fr["warning"] if fr.get("warning") else ""), fontsize=7)
        _draw_pepper(axes[r + 1][c], angles, "side")
        axes[r + 1][c].set_title("Pepper di lato", fontsize=7)
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=95)
    plt.close(fig)
    return True
