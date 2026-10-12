"""
Cinematica inversa (IK) sulla posizione del polso di Pepper.

Perche': Pepper non piega il gomito oltre ~90 gradi e ha spalle e braccia in
proporzioni diverse da una persona. Copiando solo le direzioni dei segmenti
(retarget.py) la mano puo' finire lontana dal punto del corpo in cui il segno
e' eseguito (es. davanti al mento). Per la LIS conta soprattutto DOVE si trova
la mano rispetto a corpo e viso, quindi qui si cerca la configurazione del
braccio che porta il polso di Pepper il piu' vicino possibile al bersaglio.

Problema risolto per ogni frame e per ogni braccio (q = SP, SR, EY, ER):

    min_q   sum_i w_i (p_i(q) - t_i)^2          errore del polso, pesato per asse
          + lam * ||q - q_geo||^2              resta vicino alla soluzione geometrica
          + mu  * sum_k pen_k(q)^2             penetrazione nel tablet
    con     q_min <= q <= q_max                 limiti dei giunti

 - p(q): posizione del polso (cinematica diretta, pepper_kinematics)
 - t: bersaglio ricavato dal polso umano (target_from_human)
 - w: peso maggiore su laterale/altezza (cio' che vede chi guarda il robot) e
   minore sulla profondita' (meno affidabile e spesso irraggiungibile): se il
   bersaglio e' troppo vicino al corpo la soluzione lo "spinge" in avanti.
Metodo: Levenberg-Marquardt con jacobiano numerico e proiezione sui limiti
(solo numpy).
"""
import numpy as np

from . import pepper_kinematics as pk

ARM_SUFFIXES = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll")

# Pesi dell'errore del polso: x (profondita'), y (laterale), z (altezza)
DEFAULT_AXIS_WEIGHTS = np.array([0.1, 1.0, 1.0])
DEFAULT_REG = 0.002       # m^2 / rad^2: quanto restare vicino alla soluzione geometrica
DEFAULT_TABLET_WEIGHT = 50.0

# Tablet di Pepper approssimato come scatola nel sistema del torso (metri):
# davanti al petto, sotto le spalle. Stessa posizione rispetto alle spalle del
# modello precedente (spalle ora in x = -0.057 come nell'URDF). L'URDF non
# contiene la forma del tablet (solo il riferimento del sensore, a x = 0.084,
# z = 0.063, inclinato di 30 gradi): misure da confermare sul robot.
TABLET_BOX_MIN = np.array([-0.027, -0.135, -0.13])
TABLET_BOX_MAX = np.array([0.073, 0.135, 0.04])
TABLET_MARGIN = 0.03

# I giunti non vengono portati esattamente a fine corsa (margine di sicurezza, rad)
JOINT_SAFETY_MARGIN = 0.02


def arm_points(side, q, wrist_yaw=0.0):
    """Punti del braccio per il controllo collisioni: gomito, meta' avambraccio, polso, mano."""
    if len(q) > 4:
        wrist_yaw = q[4]
    fk = pk.arm_forward_kinematics(side, q[0], q[1], q[2], q[3], wrist_yaw)
    mid = 0.5 * (fk["elbow"] + fk["wrist"])
    return fk, [fk["elbow"], mid, fk["wrist"], fk["hand"]]


def box_penetration(p, margin=TABLET_MARGIN):
    """Profondita' di penetrazione (m) di un punto nella scatola del tablet allargata del margine."""
    lo = TABLET_BOX_MIN - margin
    hi = TABLET_BOX_MAX + margin
    inside = np.minimum(p - lo, hi - p)
    if np.all(inside > 0):
        return float(np.min(inside))
    return 0.0


def tablet_collision(side, q, margin=0.0):
    """Massima penetrazione (m) del braccio nel tablet (0 = nessuna collisione)."""
    _, pts = arm_points(side, q)
    return max(box_penetration(p, margin) for p in pts)


def _limits(side):
    lo = np.array([pk.JOINT_LIMITS[side + s][0] for s in ARM_SUFFIXES]) + JOINT_SAFETY_MARGIN
    hi = np.array([pk.JOINT_LIMITS[side + s][1] for s in ARM_SUFFIXES]) - JOINT_SAFETY_MARGIN
    return lo, hi


def _residual(side, q, target, q_ref, axis_w, reg, tablet_w):
    fk, pts = arm_points(side, q)
    r = [np.sqrt(axis_w) * (fk["wrist"] - target), np.sqrt(reg) * (q - q_ref)]
    if tablet_w > 0:
        r.append(np.sqrt(tablet_w) * np.array([box_penetration(p) for p in pts]))
    return np.concatenate(r)


def solve_arm(side, target, q_init, q_ref=None, axis_weights=DEFAULT_AXIS_WEIGHTS,
              reg=DEFAULT_REG, tablet_weight=DEFAULT_TABLET_WEIGHT, iterations=40):
    """
    Ritorna (q, info). q_init: punto di partenza (es. soluzione del frame precedente);
    q_ref: soluzione geometrica verso cui regolarizzare (default q_init).
    """
    lo, hi = _limits(side)
    q = np.clip(np.asarray(q_init, dtype=float), lo, hi)
    q_ref = q.copy() if q_ref is None else np.clip(np.asarray(q_ref, dtype=float), lo, hi)
    target = np.asarray(target, dtype=float)
    damping = 1e-3
    r = _residual(side, q, target, q_ref, axis_weights, reg, tablet_weight)
    cost = float(r.dot(r))
    for _ in range(iterations):
        J = np.empty((r.size, 4))
        for k in range(4):
            dq = np.zeros(4)
            dq[k] = 1e-5
            J[:, k] = (_residual(side, q + dq, target, q_ref, axis_weights, reg, tablet_weight) - r) / 1e-5
        g = J.T.dot(r)
        H = J.T.dot(J)
        improved = False
        for _ in range(8):
            step = -np.linalg.solve(H + damping * np.diag(np.diag(H) + 1e-9), g)
            q_new = np.clip(q + step, lo, hi)
            r_new = _residual(side, q_new, target, q_ref, axis_weights, reg, tablet_weight)
            c_new = float(r_new.dot(r_new))
            if c_new < cost:
                q, r, cost = q_new, r_new, c_new
                damping = max(damping / 3.0, 1e-7)
                improved = True
                break
            damping *= 4.0
        if not improved or np.linalg.norm(step) < 1e-6:
            break
    fk = pk.arm_forward_kinematics(side, *q)
    err = fk["wrist"] - target
    return q, {
        "error_3d": float(np.linalg.norm(err)),
        "error_frontal": float(np.linalg.norm(err[1:])),
        "tablet_penetration": tablet_collision(side, q),
    }


def target_from_human(side, shoulder_h, wrist_h, k_lateral, k_arm):
    """
    Bersaglio del polso di Pepper (sistema del torso) dai punti umani gia' espressi
    nel sistema del torso della persona (origine = centro delle spalle).
      - laterale (y): rispetto alla linea mediana, scalato sulle larghezze delle spalle
        (centro del petto -> centro del petto, spalla -> spalla);
      - avanti/alto (x, z): rispetto alla spalla, scalati sulla lunghezza del braccio.
    """
    S = pk.shoulder_position(side)
    rel = wrist_h - shoulder_h
    return np.array([
        S[0] + k_arm * rel[0],
        k_lateral * wrist_h[1],
        S[2] + k_arm * rel[2],
    ])


# ---------------------------------------------------------------------------
# Passo 2: posizione E orientamento della mano (5 giunti: SP, SR, EY, ER, WristYaw)
# ---------------------------------------------------------------------------
#
#   min_q   sum_i w_i (p_i(q) - t_i)^2                 posizione (polso o centro mano)
#         + w_palm    || R_hand(q) n_palm - n* ||^2      direzione del palmo
#         + w_fingers || R_hand(q) x     - d* ||^2      direzione delle dita
#         + lam || q - q_ref ||^2 + mu * sum pen_k(q)^2  regolarizzazione, tablet
#   con  q_min <= q <= q_max
#
# E' la stessa formulazione del solutore inverseKinematics di MATLAB usato da
# Botta et al. (errore pesato di posizione e orientamento entro i limiti dei
# giunti), con l'orientamento espresso come direzioni (palmo, dita) invece che
# come rotazione completa: e' piu' naturale per descrivere un segno e Pepper,
# con 5 giunti, non puo' comunque imporre posizione e rotazione completa insieme.
# Le direzioni sono vettori (anche non unitari) nel sistema del torso; la
# differenza tra versori vale circa l'angolo in radianti, quindi con
# w = 0.0025 un errore di 1 rad "pesa" come 5 cm di posizione.

ARM5_SUFFIXES = ARM_SUFFIXES + ("WristYaw",)
DEFAULT_ORIENT_WEIGHT = 0.0025
DEFAULT_POSE_AXIS_WEIGHTS = np.array([1.0, 1.0, 1.0])


def _limits5(side):
    lo = np.array([pk.JOINT_LIMITS[side + s][0] for s in ARM5_SUFFIXES]) + JOINT_SAFETY_MARGIN
    hi = np.array([pk.JOINT_LIMITS[side + s][1] for s in ARM5_SUFFIXES]) - JOINT_SAFETY_MARGIN
    return lo, hi


def _unit(v):
    if v is None:
        return None
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None


def _pose_residual(side, q, spec):
    fk = pk.arm_forward_kinematics(side, *q)
    r = []
    if spec["target"] is not None:
        r.append(np.sqrt(spec["axis_w"]) * (fk[spec["point"]] - spec["target"]))
    axes = pk.hand_axes(side, fk)
    if spec["palm"] is not None:
        r.append(np.sqrt(spec["w_palm"]) * (axes["palm"] - spec["palm"]))
    if spec["fingers"] is not None:
        r.append(np.sqrt(spec["w_fingers"]) * (axes["fingers"] - spec["fingers"]))
    r.append(np.sqrt(spec["reg"]) * (q - spec["q_ref"]))
    if spec["tablet_w"] > 0:
        pts = [fk["elbow"], 0.5 * (fk["elbow"] + fk["wrist"]), fk["wrist"], fk["hand"]]
        r.append(np.sqrt(spec["tablet_w"]) * np.array([box_penetration(p) for p in pts]))
    return np.concatenate(r)


def _lm(fun, q, lo, hi, iterations):
    damping = 1e-3
    r = fun(q)
    cost = float(r.dot(r))
    n = q.size
    for _ in range(iterations):
        J = np.empty((r.size, n))
        for k in range(n):
            dq = np.zeros(n)
            dq[k] = 1e-6
            J[:, k] = (fun(q + dq) - r) / 1e-6
        g = J.T.dot(r)
        H = J.T.dot(J)
        improved = False
        step = np.zeros(n)
        for _ in range(10):
            step = -np.linalg.solve(H + damping * np.diag(np.diag(H) + 1e-9), g)
            q_new = np.clip(q + step, lo, hi)
            r_new = fun(q_new)
            c_new = float(r_new.dot(r_new))
            if c_new < cost:
                q, r, cost = q_new, r_new, c_new
                damping = max(damping / 3.0, 1e-9)
                improved = True
                break
            damping *= 4.0
        if not improved or np.linalg.norm(step) < 1e-8:
            break
    return q, cost


def _default_starts(side):
    """Punti di partenza per evitare minimi locali (braccio sinistro; il destro e' speculare)."""
    sg = 1.0 if side == "L" else -1.0
    rest = [pk.REST_POSE[side + s] for s in ARM5_SUFFIXES]
    starts = [rest]
    for sp, sr, ey, er, wy in ((0.6, 0.15, -1.0, -1.2, 0.0),      # mano davanti al petto
                               (-0.3, 0.2, -1.4, -1.3, 0.0),      # mano davanti al viso
                               (0.2, 0.6, -0.5, -0.5, 0.0),       # braccio di lato
                               (0.9, 0.1, -1.6, -1.4, 1.0),
                               (0.4, 0.3, 0.3, -0.8, -1.0)):
        starts.append([sp, sg * sr, sg * ey, sg * er, sg * wy])
    return [np.array(s, dtype=float) for s in starts]


def solve_arm_pose(side, target=None, palm=None, fingers=None, point="hand", q_init=None, q_ref=None,
                   axis_weights=DEFAULT_POSE_AXIS_WEIGHTS, w_palm=DEFAULT_ORIENT_WEIGHT,
                   w_fingers=DEFAULT_ORIENT_WEIGHT, reg=1e-6, tablet_weight=DEFAULT_TABLET_WEIGHT,
                   iterations=60, multi_start=True):
    """
    Cinematica inversa del braccio con 5 giunti: posizione di `point` ("hand" = centro
    della mano, "wrist" = polso) e, se dati, direzione del palmo e delle dita (torso).
    Ritorna (q5, info). q_init: partenza (es. frame precedente); con multi_start si
    provano anche alcune pose tipiche e si tiene la soluzione migliore.
    """
    lo, hi = _limits5(side)
    spec = {
        "target": None if target is None else np.asarray(target, dtype=float),
        "palm": _unit(palm), "fingers": _unit(fingers), "point": point,
        "axis_w": np.asarray(axis_weights, dtype=float), "w_palm": float(w_palm),
        "w_fingers": float(w_fingers), "reg": float(reg), "tablet_w": float(tablet_weight),
    }
    starts = []
    if q_init is not None:
        starts.append(np.clip(np.asarray(q_init, dtype=float), lo, hi))
    if multi_start or not starts:
        starts += [np.clip(s, lo, hi) for s in _default_starts(side)]
    best = None
    for q0 in starts:
        spec["q_ref"] = np.clip(np.asarray(q_ref, dtype=float), lo, hi) if q_ref is not None else q0
        q, cost = _lm(lambda x: _pose_residual(side, x, spec), q0.copy(), lo, hi, iterations)
        if best is None or cost < best[1] - 1e-12:
            best = (q, cost)
    q = best[0]
    return q, pose_info(side, q, spec["target"], spec["palm"], spec["fingers"], point)


def pose_info(side, q, target=None, palm=None, fingers=None, point="hand"):
    """Errori di posizione (m) e di orientamento (gradi) e contatto col tablet di una soluzione."""
    fk = pk.arm_forward_kinematics(side, *q)
    axes = pk.hand_axes(side, fk)
    info = {"position": fk[point].tolist(), "palm": axes["palm"].tolist(),
            "fingers": axes["fingers"].tolist(), "tablet_penetration": tablet_collision(side, q)}
    if target is not None:
        info["error_position"] = float(np.linalg.norm(fk[point] - target))
    for key, want in (("palm", _unit(palm)), ("fingers", _unit(fingers))):
        if want is not None:
            c = float(np.clip(np.dot(axes[key], want), -1.0, 1.0))
            info["error_" + key + "_deg"] = float(np.degrees(np.arccos(c)))
    return info
