"""
Stima della profondita' per keypoint 2D (opzione A, DWPose).

Idea: se la lunghezza reale L di un segmento (braccio o avambraccio) e' nota e
nell'immagine se ne vede la proiezione d, la componente di profondita' vale
    |dz| = sqrt(max(L^2 - d^2, 0))
Il segno e' ambiguo (avanti o dietro): nei segni LIS le mani lavorano quasi
sempre davanti al corpo, quindi si assume dz >= 0 (verso la telecamera).

La lunghezza L e' stimata dal video stesso: quando il segmento e' parallelo al
piano dell'immagine la proiezione coincide con la lunghezza reale, quindi si usa
un percentile alto delle lunghezze 2D osservate, con un minimo dato dalle
proporzioni antropometriche rispetto alla larghezza delle spalle.
"""
import numpy as np

# Proporzioni medie rispetto alla larghezza delle spalle (distanza tra i due acromion)
UPPER_ARM_RATIO = 0.78
FOREARM_RATIO = 0.68
PERCENTILE = 95


def _segment_lengths(a, b):
    return np.linalg.norm(a[:, :2] - b[:, :2], axis=1)


def estimate_depth(seq, forward_sign=1.0):
    """
    Riempie la componente z dei keypoint di braccia e mani di una PoseSequence 2D.
    Spalle e anche sono poste a z = 0 (persona frontale).
    Ritorna un dict con le lunghezze stimate (per il report).
    """
    if seq.is_3d:
        return {}

    shoulder_w = _segment_lengths(seq.body["l_shoulder"], seq.body["r_shoulder"])
    sw = float(np.nanmedian(shoulder_w)) if np.any(np.isfinite(shoulder_w)) else np.nan

    for name in ("l_shoulder", "r_shoulder", "l_hip", "r_hip", "nose"):
        pts = seq.body[name]
        ok = np.isfinite(pts[:, 0])
        pts[ok, 2] = 0.0
    # Il naso sta davanti alle spalle: utile per il controllo dell'orientamento
    nose = seq.body["nose"]
    ok = np.isfinite(nose[:, 0])
    if np.isfinite(sw):
        nose[ok, 2] = forward_sign * 0.25 * sw

    info = {"shoulder_width": sw}
    for side in ("l", "r"):
        s, e, w = seq.body[side + "_shoulder"], seq.body[side + "_elbow"], seq.body[side + "_wrist"]
        d_upper = _segment_lengths(s, e)
        d_fore = _segment_lengths(e, w)
        L_upper = _robust_length(d_upper, UPPER_ARM_RATIO * sw)
        L_fore = _robust_length(d_fore, FOREARM_RATIO * sw)
        info[side + "_upper_arm"] = L_upper
        info[side + "_forearm"] = L_fore

        dz_e = forward_sign * np.sqrt(np.clip(L_upper ** 2 - d_upper ** 2, 0.0, None))
        e[:, 2] = s[:, 2] + dz_e
        dz_w = forward_sign * np.sqrt(np.clip(L_fore ** 2 - d_fore ** 2, 0.0, None))
        w[:, 2] = e[:, 2] + dz_w

        # La mano segue la profondita' del polso (serve solo il rapporto di apertura)
        hand = seq.hands[side]
        ok = np.isfinite(hand[:, 0, 0]) & np.isfinite(w[:, 2])
        hand[ok, :, 2] = w[ok, 2][:, None]
    return info


def _robust_length(lengths, prior):
    finite = lengths[np.isfinite(lengths)]
    observed = float(np.percentile(finite, PERCENTILE)) if finite.size else np.nan
    candidates = [v for v in (observed, prior) if np.isfinite(v)]
    return max(candidates) if candidates else np.nan
