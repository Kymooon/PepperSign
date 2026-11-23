"""
Modello cinematico delle braccia di Pepper, dall'URDF ufficiale.

Fonte: URDF di Pepper generato da Aldebaran/SoftBank (pacchetto ROS
`pepper_description`, file pepper1.0_generated_urdf/pepper.urdf, repository
ros-naoqi/pepper_robot), confrontato con la documentazione NAOqi 2.5
("Pepper - Links" e "Joints"). I parametri sono riportati qui sotto: il file
URDF non serve a runtime.

Catena di un braccio (sistema del torso: x avanti, y a sinistra del robot, z in alto;
metri, radianti):

    torso --[ShoulderPitch: origine (-0.057, +-0.14974, 0.08682), asse y]-->
          --[ShoulderRoll:  asse z]-->
          --[ElbowYaw:  origine (0.1812, +-0.015, 0.00013), rotazione fissa
                         pitch -0.157079 (gomito inclinato di ~9 gradi), asse x]-->
          --[ElbowRoll: asse z]-->
          --[WristYaw:  origine (0.15, 0, 0), asse x]-->
          --[centro della mano: (0.0695, 0, -0.0303), da documentazione NAOqi]

    ShoulderPitch  0 = braccio orizzontale in avanti, + = verso il basso
    ShoulderRoll   + = verso sinistra
    ElbowYaw       rotazione attorno all'asse del braccio
    ElbowRoll      piega del gomito
    WristYaw       rotazione attorno all'asse dell'avambraccio
I segni +- valgono per il braccio sinistro / destro.

Differenze note tra le due fonti ufficiali (da verificare sul robot):
  - la documentazione mette il polso 23.6 mm piu' verso l'interno (y) rispetto
    all'URDF; qui si usa l'URDF (WRIST_OFFSET_Y = 0);
  - il centro della mano non e' nell'URDF (solo la pinza a 25 mm dal polso):
    si usa l'offset della documentazione.

Versione precedente (fino al 07/10/2026): modello semplificato con spalla in
x = 0, senza offset del gomito e senza l'inclinazione di 9 gradi; e' ancora
disponibile come `arm_forward_kinematics_simple` per confronto.
"""
import numpy as np

# Parametri dall'URDF (metri, radianti)
SHOULDER_OFFSET_X = -0.057
SHOULDER_OFFSET_Y = 0.14974
SHOULDER_OFFSET_Z = 0.08682
UPPER_ARM_LENGTH = 0.1812
ELBOW_OFFSET_Y = 0.015           # verso l'esterno: +y braccio sx, -y braccio dx
ELBOW_OFFSET_Z = 0.00013
ELBOW_PITCH_OFFSET = -0.157079   # rotazione fissa del giunto ElbowYaw (rpy pitch)
LOWER_ARM_LENGTH = 0.150
WRIST_OFFSET_Y = 0.0             # documentazione: 0.0236 verso l'interno (vedi sopra)
# Centro della mano nel sistema del polso (documentazione NAOqi: HandOffsetX, HandOffsetZ)
HAND_OFFSET_X = 0.0695
HAND_OFFSET_Z = -0.0303

# Limiti dei giunti (radianti), documentazione Aldebaran / Pepper 1.8
JOINT_LIMITS = {
    "HeadYaw": (-2.0857, 2.0857),
    "HeadPitch": (-0.7068, 0.4451),   # documentazione NAOqi 2.5 (URDF: 0.637); si riduce con HeadYaw
    "LShoulderPitch": (-2.0857, 2.0857),
    "LShoulderRoll": (0.0087, 1.5620),
    "LElbowYaw": (-2.0857, 2.0857),
    "LElbowRoll": (-1.5620, -0.0087),
    "LWristYaw": (-1.8239, 1.8239),
    "LHand": (0.0, 1.0),
    "RShoulderPitch": (-2.0857, 2.0857),
    "RShoulderRoll": (-1.5620, -0.0087),
    "RElbowYaw": (-2.0857, 2.0857),
    "RElbowRoll": (0.0087, 1.5620),
    "RWristYaw": (-1.8239, 1.8239),
    "RHand": (0.0, 1.0),
}

# Stesso ordine dei giunti usato dalla GUI di Controll (gesture_store.DEFAULT_JOINTS)
DEFAULT_JOINTS = [
    "HeadYaw", "HeadPitch",
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

ARM_JOINT_SUFFIXES = ["ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw", "Hand"]

# Posa di riposo (simile a StandInit), usata per riempire i giunti non stimati
REST_POSE = {
    "HeadYaw": 0.0, "HeadPitch": -0.15,
    "LShoulderPitch": 1.5, "LShoulderRoll": 0.15, "LElbowYaw": -1.2,
    "LElbowRoll": -0.5, "LWristYaw": 0.0, "LHand": 0.6,
    "RShoulderPitch": 1.5, "RShoulderRoll": -0.15, "RElbowYaw": 1.2,
    "RElbowRoll": 0.5, "RWristYaw": 0.0, "RHand": 0.6,
}


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def shoulder_position(side):
    """Posizione della spalla nel sistema del torso. side: 'L' o 'R'."""
    sign = 1.0 if side == "L" else -1.0
    return np.array([SHOULDER_OFFSET_X, sign * SHOULDER_OFFSET_Y, SHOULDER_OFFSET_Z])


def arm_forward_kinematics(side, shoulder_pitch, shoulder_roll, elbow_yaw, elbow_roll, wrist_yaw=0.0):
    """
    Cinematica diretta di un braccio (modello URDF).
    Ritorna dict con le posizioni (torso) di spalla, gomito, polso e centro della mano,
    e le matrici di rotazione del braccio, dell'avambraccio e della mano.
    """
    sign = 1.0 if side == "L" else -1.0
    s = shoulder_position(side)
    r_upper = rot_y(shoulder_pitch).dot(rot_z(shoulder_roll))
    elbow = s + r_upper.dot([UPPER_ARM_LENGTH, sign * ELBOW_OFFSET_Y, ELBOW_OFFSET_Z])
    r_fore = r_upper.dot(rot_y(ELBOW_PITCH_OFFSET)).dot(rot_x(elbow_yaw)).dot(rot_z(elbow_roll))
    wrist = elbow + r_fore.dot([LOWER_ARM_LENGTH, -sign * WRIST_OFFSET_Y, 0.0])
    r_hand = r_fore.dot(rot_x(wrist_yaw))
    hand = wrist + r_hand.dot([HAND_OFFSET_X, 0.0, HAND_OFFSET_Z])
    return {
        "shoulder": s, "elbow": elbow, "wrist": wrist, "hand": hand,
        "r_upper": r_upper, "r_fore": r_fore, "r_hand": r_hand,
    }


def arm_forward_kinematics_simple(side, shoulder_pitch, shoulder_roll, elbow_yaw, elbow_roll, wrist_yaw=0.0):
    """Modello semplificato usato fino al 07/10/2026 (solo per confronto)."""
    sign = 1.0 if side == "L" else -1.0
    s = np.array([0.0, sign * SHOULDER_OFFSET_Y, SHOULDER_OFFSET_Z])
    r_upper = rot_y(shoulder_pitch).dot(rot_z(shoulder_roll))
    elbow = s + r_upper.dot([UPPER_ARM_LENGTH, 0.0, 0.0])
    r_fore = r_upper.dot(rot_x(elbow_yaw)).dot(rot_z(elbow_roll))
    wrist = elbow + r_fore.dot([LOWER_ARM_LENGTH, 0.0, 0.0])
    r_hand = r_fore.dot(rot_x(wrist_yaw))
    hand = wrist + r_hand.dot([HAND_OFFSET_X, 0.0, 0.0])
    return {
        "shoulder": s, "elbow": elbow, "wrist": wrist, "hand": hand,
        "r_upper": r_upper, "r_fore": r_fore, "r_hand": r_hand,
    }


def forward_kinematics_pose(angles_by_joint):
    """FK di entrambe le braccia da un dict {giunto: angolo}."""
    out = {}
    for side in ("L", "R"):
        a = lambda name: float(angles_by_joint.get(side + name, REST_POSE[side + name]))
        out[side] = arm_forward_kinematics(
            side, a("ShoulderPitch"), a("ShoulderRoll"), a("ElbowYaw"), a("ElbowRoll"), a("WristYaw"))
    return out


def clamp_to_limits(name, value):
    lo, hi = JOINT_LIMITS[name]
    return float(min(max(value, lo), hi))


# Assi della mano nel sistema della mano (r_hand), uguali per i due lati salvo il pollice:
#   x = direzione delle dita (prolungamento dell'avambraccio)
#   -z = normale del palmo (lato verso cui il palmo "guarda"): il centro della mano
#        e' spostato verso -z (HandOffsetZ = -30.3 mm) e con la posa di riposo il
#        palmo e' rivolto verso la coscia
#   lato del pollice: +y braccio destro, -y braccio sinistro
HAND_FINGERS_LOCAL = np.array([1.0, 0.0, 0.0])
HAND_PALM_LOCAL = np.array([0.0, 0.0, -1.0])
HAND_THUMB_LOCAL = {"L": np.array([0.0, -1.0, 0.0]), "R": np.array([0.0, 1.0, 0.0])}


def hand_axes(side, fk):
    """Direzioni (torso) di dita, palmo e pollice dalla FK di un braccio."""
    r = fk["r_hand"]
    return {"fingers": r.dot(HAND_FINGERS_LOCAL), "palm": r.dot(HAND_PALM_LOCAL),
            "thumb": r.dot(HAND_THUMB_LOCAL[side])}


# Giunti che cambiano segno passando da un braccio all'altro (specchio sul piano sagittale)
MIRROR_SIGN = {"ShoulderPitch": 1.0, "ShoulderRoll": -1.0, "ElbowYaw": -1.0,
               "ElbowRoll": -1.0, "WristYaw": -1.0, "Hand": 1.0}


def mirror_arm_angles(angles, from_side):
    """Angoli {suffisso: valore} del braccio from_side -> angoli {giunto: valore} dell'altro braccio."""
    to_side = "R" if from_side == "L" else "L"
    return dict((to_side + s, MIRROR_SIGN[s] * float(v)) for s, v in angles.items() if s in MIRROR_SIGN)
