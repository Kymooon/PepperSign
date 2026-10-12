"""
Retargeting geometrico: keypoint 3D umani -> angoli dei giunti delle braccia di Pepper.

Per ogni frame:
 1. si costruisce il sistema del torso della persona (spalle + anche):
        y = dalla spalla destra alla sinistra, z = verso l'alto, x = y x z (avanti)
    cosi' posizione, distanza e inclinazione della persona nell'inquadratura
    non contano;
 2. per ogni braccio si calcolano la direzione del braccio u (spalla->gomito)
    e dell'avambraccio f (gomito->polso) nel sistema del torso;
 3. si invertono analiticamente le rotazioni del modello di Pepper
    (vedi pepper_kinematics):
        u = Ry(SP) Rz(SR + a) [1,0,0]      ->  SR = asin(u_y) - a,  SP = atan2(-u_z, u_x)
           (a = angolo dovuto all'offset laterale del gomito nell'URDF, ~4.7 gradi)
        f' = (Ry(SP) Rz(SR) Ry(t))^T f = Rx(EY) Rz(ER) [1,0,0]
           (t = inclinazione fissa del gomito nell'URDF, ~ -9 gradi)
           = (cos ER, sin ER cos EY, sin ER sin EY)
                                            ->  |ER| = acos(f'_x)
                                                ER < 0 a sinistra, > 0 a destra
                                                EY = atan2(f'_z / sin ER, f'_y / sin ER)
    Quando il gomito e' quasi dritto EY non e' definito: viene lasciato NaN e
    poi interpolato dai frame vicini (postprocess);
 4. l'apertura della mano (0 chiusa - 1 aperta) e' stimata dal rapporto tra la
    distanza media polso-punte delle dita e la lunghezza del palmo.

Il polso (WristYaw) e la testa restano alla posa di riposo in F0.
"""
import numpy as np

from . import pepper_kinematics as pk
from .keypoints import HAND_TIPS, HAND_MIDDLE_MCP

ELBOW_STRAIGHT_THRESHOLD = 0.15   # rad: sotto questa piega ElbowYaw non e' affidabile
HAND_RATIO_CLOSED = 1.15
HAND_RATIO_OPEN = 1.85


def _normalize(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None


def torso_frame(ls, rs, lh, rh):
    """Ritorna (origine, R) con R = [x y z] colonne; locale = R^T (p - origine)."""
    if not (np.all(np.isfinite(ls)) and np.all(np.isfinite(rs))):
        return None
    origin = 0.5 * (ls + rs)
    y = _normalize(ls - rs)
    if y is None:
        return None
    if np.all(np.isfinite(lh)) and np.all(np.isfinite(rh)):
        up = origin - 0.5 * (lh + rh)
    else:
        up = np.array([0.0, 1.0, 0.0])           # anche non visibili: verticale dell'immagine
    z = _normalize(up - np.dot(up, y) * y)
    if z is None:
        return None
    x = np.cross(y, z)
    return origin, np.column_stack([x, y, z])


def arm_angles(side, u, f):
    """
    u, f: direzioni (unitarie) di braccio e avambraccio nel sistema del torso.
    Ritorna (SP, SR, EY, ER) senza clamp (EY = NaN se il gomito e' dritto).
    """
    # offset laterale del gomito (URDF): il segmento spalla-gomito e' ruotato di
    # alpha rispetto all'asse x del braccio, quindi si sottrae da ShoulderRoll
    sign = 1.0 if side == "L" else -1.0
    alpha = float(np.arctan2(sign * pk.ELBOW_OFFSET_Y, pk.UPPER_ARM_LENGTH))
    sr = float(np.arcsin(np.clip(u[1], -1.0, 1.0))) - alpha
    sp = float(np.arctan2(-u[2], u[0]))
    r_upper = pk.rot_y(sp).dot(pk.rot_z(sr)).dot(pk.rot_y(pk.ELBOW_PITCH_OFFSET))
    fl = r_upper.T.dot(f)
    mag = float(np.arccos(np.clip(fl[0], -1.0, 1.0)))
    er = -mag if side == "L" else mag
    if mag < ELBOW_STRAIGHT_THRESHOLD:
        ey = np.nan
    else:
        s = np.sin(er)
        ey = float(np.arctan2(fl[2] / s, fl[1] / s))
    return sp, sr, ey, er


def hand_openness(hand_pts):
    """hand_pts: (21,3). Ritorna 0..1 oppure NaN."""
    if not np.all(np.isfinite(hand_pts[[0, HAND_MIDDLE_MCP] + HAND_TIPS, :2])):
        return np.nan
    p = hand_pts[:, :2]          # il rapporto in 2D e' sufficiente e piu' stabile
    palm = np.linalg.norm(p[HAND_MIDDLE_MCP] - p[0])
    if palm < 1e-6:
        return np.nan
    tips = np.mean([np.linalg.norm(p[i] - p[0]) for i in HAND_TIPS])
    ratio = tips / palm
    return float(np.clip((ratio - HAND_RATIO_CLOSED) / (HAND_RATIO_OPEN - HAND_RATIO_CLOSED), 0.0, 1.0))


def retarget_sequence(seq, mirror=False):
    """
    PoseSequence (3D) -> dict giunto -> array (T,) di angoli grezzi (NaN dove non stimabile)
    piu' diagnostica: errore di direzione dovuto ai limiti dei giunti.
    mirror=False: lato anatomico (braccio destro del segnante -> braccio destro di Pepper).
    """
    T = seq.n_frames
    out = dict((name, np.full(T, np.nan)) for name in pk.DEFAULT_JOINTS)
    direction_error = {"L": np.full(T, np.nan), "R": np.full(T, np.nan)}
    b = seq.body
    for t in range(T):
        frame = torso_frame(b["l_shoulder"][t], b["r_shoulder"][t], b["l_hip"][t], b["r_hip"][t])
        if frame is None:
            continue
        origin, R = frame
        for human_side, robot_side in (("l", "L"), ("r", "R")):
            if mirror:
                robot_side = "R" if robot_side == "L" else "L"
            s, e, w = b[human_side + "_shoulder"][t], b[human_side + "_elbow"][t], b[human_side + "_wrist"][t]
            if not (np.all(np.isfinite(s)) and np.all(np.isfinite(e)) and np.all(np.isfinite(w))):
                continue
            u = _normalize(R.T.dot(e - s))
            f = _normalize(R.T.dot(w - e))
            if u is None or f is None:
                continue
            if mirror:   # specchio rispetto al piano sagittale: y -> -y
                u = u * np.array([1, -1, 1])
                f = f * np.array([1, -1, 1])
            sp, sr, ey, er = arm_angles(robot_side, u, f)
            p = robot_side
            out[p + "ShoulderPitch"][t] = sp
            out[p + "ShoulderRoll"][t] = sr
            out[p + "ElbowYaw"][t] = ey
            out[p + "ElbowRoll"][t] = er
            out[p + "Hand"][t] = hand_openness(seq.hands[human_side][t])

            # Diagnostica: quanto i limiti di Pepper deformano il braccio
            c = lambda n, v: pk.clamp_to_limits(p + n, v) if np.isfinite(v) else 0.0
            fk = pk.arm_forward_kinematics(p, c("ShoulderPitch", sp), c("ShoulderRoll", sr),
                                           c("ElbowYaw", ey), c("ElbowRoll", er))
            u_r = _normalize(fk["elbow"] - fk["shoulder"])
            f_r = _normalize(fk["wrist"] - fk["elbow"])
            err_u = np.degrees(np.arccos(np.clip(np.dot(u, u_r), -1, 1)))
            err_f = np.degrees(np.arccos(np.clip(np.dot(f, f_r), -1, 1)))
            direction_error[p][t] = 0.5 * (err_u + err_f)
    return out, direction_error
