"""
Rotazione del polso di Pepper (WristYaw) stimata dai punti della mano (BETA).

Pepper ha un solo grado di liberta' al polso: la rotazione attorno all'asse
dell'avambraccio (WristYaw, +-104 gradi). Non puo' piegare il polso su/giu'.
Qui si stima quanto e' ruotata la mano della persona e si cerca il WristYaw
che fa apparire la mano di Pepper ruotata allo stesso modo a chi guarda il
robot di fronte (stessa idea della cinematica inversa: conta cio' che vede
l'interlocutore).

Misura sulla persona (2D, per frame):
    f = direzione dell'avambraccio nell'immagine (gomito -> polso)
    k = linea delle nocche, dal mignolo (17) all'indice (5): lato del pollice
    c = componente di k perpendicolare a f, divisa per la larghezza delle
        nocche vista di fronte (W0)                               c in [-1, 1]
    c ~ +-1: palmo (o dorso) rivolto verso la telecamera; c ~ 0: mano di taglio.
    Il segno distingue palmo e dorso (dipende da quale lato appare il pollice).

Stessa misura su Pepper, per gli angoli del braccio gia' calcolati dall'IK:
    k(w) = asse lato-pollice della mano di Pepper ruotato di w attorno
           all'avambraccio, proiettato nella vista frontale (y, z del torso)
    c_p(w) = A cos(w) + B sin(w) = M cos(w - phi)
    -> due soluzioni w = phi +- acos(c / M): si sceglie quella piu' vicina
       al frame precedente (continuita'); al primo frame quella piu' vicina
       a 0, oppure l'altra con --wrist-flip.

Limiti noti:
 - da un video 2D non si distingue sempre il verso della rotazione (pollice
   verso la telecamera o lontano): il verso va confermato sul robot
   (--wrist-flip sceglie l'altro);
 - l'asse lato-pollice della mano di Pepper (THUMB_AXIS) e' ricavato dalla
   posa di riposo (WristYaw = 0: palmo verso la coscia, pollice in avanti),
   da confermare sul robot;
 - la stima si fa solo dove la mano e' rilevata bene (confidenza >= hand_conf),
   negli altri frame il valore viene interpolato dai vicini o resta a riposo.
"""
import numpy as np

from . import pepper_kinematics as pk

KNUCKLE_INDEX = 5
KNUCKLE_PINKY = 17
PALM_BASE = 0
PALM_MIDDLE = 9

DEFAULT_HAND_CONF = 0.5
KNUCKLE_PALM_RATIO = 0.7      # larghezza nocche / lunghezza del palmo di una mano tipica
MIN_VISIBILITY = 0.3          # sotto: avambraccio di Pepper quasi puntato verso chi guarda
MIN_FOREARM_2D = 1e-3         # avambraccio umano troppo corto nell'immagine: stima inaffidabile
JOINT_MARGIN = 0.02           # rad dal fine corsa

# Asse "lato pollice" della mano di Pepper nel sistema della mano (r_hand) del modello.
# Con la posa di riposo e WristYaw = 0 corrisponde al pollice in avanti e al palmo verso la coscia.
THUMB_AXIS = {"L": np.array([0.0, -1.0, 0.0]), "R": np.array([0.0, 1.0, 0.0])}


def _cross2(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def human_palm_signal(seq, side, mirror=False, min_conf=DEFAULT_HAND_CONF):
    """
    c(t) in [-1, 1] per la mano `side` ("l"/"r") della persona; NaN dove non affidabile.
    Ritorna (c, info).
    """
    T = seq.n_frames
    c = np.full(T, np.nan)
    hand = seq.hands[side]
    conf = seq.hand_conf[side]
    f = seq.body[side + "_wrist"][:, :2] - seq.body[side + "_elbow"][:, :2]
    k = hand[:, KNUCKLE_INDEX, :2] - hand[:, KNUCKLE_PINKY, :2]
    palm = np.linalg.norm(hand[:, PALM_MIDDLE, :2] - hand[:, PALM_BASE, :2], axis=1)
    fn = np.linalg.norm(f, axis=1)
    ok = (conf >= min_conf) & np.all(np.isfinite(k), axis=1) & np.all(np.isfinite(f), axis=1) & (fn > MIN_FOREARM_2D)
    info = {"frames": int(ok.sum()), "knuckle_width": float("nan")}
    if ok.sum() < 3:
        return c, info
    kn = np.linalg.norm(k, axis=1)
    w0 = max(np.percentile(kn[ok], 90), KNUCKLE_PALM_RATIO * np.nanpercentile(palm[ok], 90))
    if not np.isfinite(w0) or w0 <= 1e-9:
        return c, info
    fu = f[ok] / fn[ok][:, None]
    c[ok] = np.clip(_cross2(fu, k[ok]) / w0, -1.0, 1.0)
    if mirror:                 # specchio sinistra/destra: x -> -x cambia il segno del prodotto vettoriale
        c = -c
    info["knuckle_width"] = float(w0)
    return c, info


def pepper_palm_coeffs(side, q_arm):
    """
    Per il braccio di Pepper (SP, SR, EY, ER) ritorna (A, B) con
    c_p(w) = A cos(w) + B sin(w), oppure None se l'avambraccio punta verso chi guarda.
    """
    fk = pk.arm_forward_kinematics(side, q_arm[0], q_arm[1], q_arm[2], q_arm[3], 0.0)
    r_fore = fk["r_fore"]
    f2 = r_fore[:, 0][[1, 2]]                  # vista frontale: (y, z) del torso
    n = np.linalg.norm(f2)
    if n < 1e-6:
        return None
    f2 = f2 / n
    a = THUMB_AXIS[side]
    u = r_fore.dot(a)                          # w = 0
    v = r_fore.dot(np.array([0.0, -a[2], a[1]]))   # derivata della rotazione attorno a x
    A = float(_cross2(f2, u[[1, 2]]))
    B = float(_cross2(f2, v[[1, 2]]))
    return A, B


def pepper_palm_signal(side, q_arm, wrist_yaw):
    coeffs = pepper_palm_coeffs(side, q_arm)
    if coeffs is None:
        return float("nan")
    A, B = coeffs
    return A * np.cos(wrist_yaw) + B * np.sin(wrist_yaw)


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def solve_wrist(side, q_arm, c_target, w_ref=None, flip=False):
    """
    WristYaw di Pepper che riproduce c_target. Ritorna (w, M) oppure (None, M).
    w_ref: valore del frame precedente (continuita'); se None si sceglie la soluzione
    piu' vicina a 0 (o la piu' lontana con flip=True).
    """
    coeffs = pepper_palm_coeffs(side, q_arm)
    if coeffs is None:
        return None, 0.0
    A, B = coeffs
    M = float(np.hypot(A, B))
    if M < MIN_VISIBILITY:
        return None, M
    phi = float(np.arctan2(B, A))
    d = float(np.arccos(np.clip(c_target / M, -1.0, 1.0)))
    lo, hi = pk.JOINT_LIMITS[side + "WristYaw"]
    lo, hi = lo + JOINT_MARGIN, hi - JOINT_MARGIN
    cands = []
    for w in (_wrap(phi + d), _wrap(phi - d)):
        wc = min(max(w, lo), hi)
        # costo: errore sul segnale dopo il clamp + distanza dal riferimento
        err = abs(A * np.cos(wc) + B * np.sin(wc) - c_target)
        cands.append((wc, err))
    if w_ref is None:
        cands.sort(key=lambda x: (round(x[1], 2), abs(x[0])))
        return (cands[-1][0] if flip and len(cands) > 1 and cands[-1][1] < 0.3 else cands[0][0]), M
    cands.sort(key=lambda x: x[1] * 2.0 + abs(x[0] - w_ref))
    return cands[0][0], M


def wrist_trajectory(seq, human_side, robot_side, arm_angles, rest_flags,
                     mirror=False, min_conf=DEFAULT_HAND_CONF, flip=False):
    """
    arm_angles: (T, 4) angoli del braccio di Pepper (SP, SR, EY, ER), NaN dove mancano.
    Ritorna (wrist (T,) con NaN dove non stimato e posa di riposo nei frame di riposo, info).
    """
    T = seq.n_frames
    c, info = human_palm_signal(seq, human_side, mirror=mirror, min_conf=min_conf)
    out = np.full(T, np.nan)
    rest_value = pk.REST_POSE[robot_side + "WristYaw"]
    prev = None
    estimated = 0
    for t in range(T):
        if rest_flags[t]:
            out[t] = rest_value
            prev = None
            continue
        q = arm_angles[t]
        if not (np.isfinite(c[t]) and np.all(np.isfinite(q))):
            continue
        w, _ = solve_wrist(robot_side, q, c[t], w_ref=prev, flip=flip)
        if w is None:
            continue
        out[t] = w
        prev = w
        estimated += 1
    info["estimated"] = estimated
    info["signal"] = c
    return out, info


def turning_points(values, times, min_amplitude=0.12, min_gap=0.08):
    """
    Indici dei massimi/minimi locali di un segnale con escursione >= min_amplitude
    (isteresi), distanti almeno min_gap secondi. Servono come keyframe obbligatori
    per non perdere le oscillazioni rapide del polso.
    """
    v = np.asarray(values, dtype=float)
    n = len(v)
    if n < 3 or not np.all(np.isfinite(v)):
        return []
    points = []
    hi_i = lo_i = 0
    direction = 0          # 0 = non ancora deciso, +1 salita, -1 discesa
    ext_i = 0
    for i in range(1, n):
        if direction == 0:
            if v[i] > v[hi_i]:
                hi_i = i
            if v[i] < v[lo_i]:
                lo_i = i
            if v[hi_i] - v[lo_i] >= min_amplitude:
                if hi_i > lo_i:            # salita: il minimo precedente e' un punto di svolta
                    points.append(lo_i)
                    direction, ext_i = 1, hi_i
                else:
                    points.append(hi_i)
                    direction, ext_i = -1, lo_i
            continue
        if direction == 1:
            if v[i] > v[ext_i]:
                ext_i = i
            elif v[ext_i] - v[i] >= min_amplitude:
                points.append(ext_i)
                direction, ext_i = -1, i
        else:
            if v[i] < v[ext_i]:
                ext_i = i
            elif v[i] - v[ext_i] >= min_amplitude:
                points.append(ext_i)
                direction, ext_i = 1, i
    if direction != 0:
        points.append(ext_i)           # ultimo estremo (scartato se troppo vicino alla fine)
    # distanza minima tra i punti e dai bordi
    out = []
    for i in points:
        tol = 1e-6
        if times[i] - times[0] < min_gap - tol or times[-1] - times[i] < min_gap - tol:
            continue
        if out and times[i] - times[out[-1]] < min_gap - tol:
            continue
        out.append(i)
    return out
