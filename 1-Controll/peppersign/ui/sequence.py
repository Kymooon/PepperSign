# -*- coding: utf-8 -*-
"""
Sequenza di frame del gesto in registrazione.

Contiene i dati (giunti e frame) e tutte le operazioni della scheda
"Registrazione segni": nessun widget, nessun thread, nessuna chiamata al robot.
La validazione della posa (limiti dei giunti) e la costruzione delle traiettorie
arrivano dal controller come funzioni, cosi' il modello si prova anche da solo.

Va usato solo dal thread della finestra: i thread secondari leggono la posa dal
robot e passano il risultato al thread della finestra (vedi ui.dispatcher).

Un frame e' un dict {"angles": [...], "dt": s} con chiavi facoltative
("composite", NO_ARM_COLLISION_KEY, "copied_from_frame", "source", ...).
"""
from __future__ import absolute_import

import copy

from peppersign.robot.interpolation import NO_ARM_COLLISION_KEY, arm_collision_windows, check_frames
from peppersign.utils import read_json

DT_MIN = 0.05
DT_MAX = 10.0
DEFAULT_DT = 0.6

# Coppie usate per duplicare/specchiare la posa di un braccio sull'altro.
# Per la simmetria fisica di Pepper alcuni giunti devono cambiare segno.
LEFT_TO_RIGHT_ARM_MIRROR = [
    ("LShoulderPitch", "RShoulderPitch", 1.0),
    ("LShoulderRoll", "RShoulderRoll", -1.0),
    ("LElbowYaw", "RElbowYaw", -1.0),
    ("LElbowRoll", "RElbowRoll", -1.0),
    ("LWristYaw", "RWristYaw", -1.0),
    ("LHand", "RHand", 1.0),
]

RIGHT_TO_LEFT_ARM_MIRROR = [
    ("RShoulderPitch", "LShoulderPitch", 1.0),
    ("RShoulderRoll", "LShoulderRoll", -1.0),
    ("RElbowYaw", "LElbowYaw", -1.0),
    ("RElbowRoll", "LElbowRoll", -1.0),
    ("RWristYaw", "LWristYaw", -1.0),
    ("RHand", "LHand", 1.0),
]

# Gruppi usati per costruire un frame composito: nello stesso frame la posa del
# braccio sinistro, del braccio destro e della testa, acquisite in momenti diversi.
LEFT_ARM_COMPONENT_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
]

RIGHT_ARM_COMPONENT_JOINTS = [
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

HEAD_COMPONENT_JOINTS = ["HeadYaw", "HeadPitch"]


def clamp_dt(dt):
    return min(max(float(dt), DT_MIN), DT_MAX)


def with_hands(joints):
    """Giunti di registrazione: quelli dati piu' le due mani, se mancano."""
    joints = list(joints)
    for hand in ("LHand", "RHand"):
        if hand not in joints:
            joints.append(hand)
    return joints


class AngleCountMismatch(Exception):
    """Il frame non ha esattamente un angolo per giunto (niente completamento con zeri)."""

    def __init__(self, index, count, expected):
        Exception.__init__(self, "frame %d: %d angoli invece di %d" % (index + 1, count, expected))
        self.index, self.count, self.expected = index, count, expected


class MissingJoints(Exception):
    """La sequenza non contiene i giunti richiesti dall'operazione."""

    def __init__(self, joints):
        Exception.__init__(self, ", ".join(joints))
        self.joints = list(joints)


class SequenceChanged(Exception):
    """La sequenza e' cambiata mentre si leggeva la posa dal robot (es. caricato un altro file)."""


class UnsupportedFormat(Exception):
    """Il file non e' una sequenza frames_v1."""


class InvalidSequenceFile(Exception):
    """Il file e' una sequenza frames_v1 ma i frame non sono coerenti."""

    def __init__(self, problems):
        Exception.__init__(self, "; ".join(problems[:3]))
        self.problems = list(problems)


class PoseCheck(object):
    """Esito della validazione di una posa: ok, avvisi, errori."""

    def __init__(self, ok, warnings, errors):
        self.ok, self.warnings, self.errors = bool(ok), list(warnings or []), list(errors or [])


class SequenceModel(object):
    """
    validate_pose(joints, angles) -> (ok, warnings, errors)   (controller.validate_frame_pose)
    """

    def __init__(self, joints, validate_pose):
        self.joints = list(joints)
        self.frames = []
        self._validate_pose = validate_pose

    # ------------------------------------------------------------ lettura

    def __len__(self):
        return len(self.frames)

    def is_index(self, index):
        return index is not None and 0 <= index < len(self.frames)

    def index_of(self, frame):
        """Posizione attuale di un frame (per identita'), None se non c'e' piu'."""
        for index, item in enumerate(self.frames):
            if item is frame:
                return index
        return None

    def joint_index(self, joint):
        try:
            return self.joints.index(joint)
        except ValueError:
            return None

    def angles_checked(self, index):
        """Copia degli angoli del frame; AngleCountMismatch se non sono uno per giunto."""
        angles = list(self.frames[index].get("angles", []))
        if len(angles) != len(self.joints):
            raise AngleCountMismatch(index, len(angles), len(self.joints))
        return angles

    def check_pose(self, angles, joints=None):
        ok, warnings, errors = self._validate_pose(self.joints if joints is None else joints, angles)
        return PoseCheck(ok, warnings, errors)

    def problems(self):
        """Problemi di coerenza della sequenza (lista vuota se valida)."""
        return check_frames(self.joints, self.frames)

    def collision_windows(self, frames=None):
        return arm_collision_windows(self.frames if frames is None else frames)

    def describe(self, index):
        """Riga della lista dei frame."""
        frame = self.frames[index]
        dt = frame.get("dt", DEFAULT_DT)
        suffix = "   comp" if frame.get("composite") else ""
        if frame.get(NO_ARM_COLLISION_KEY):
            suffix += "   NO-COLL"
        return "Frame %02d   dt=%.2fs%s" % (index + 1, float(dt) if dt else 0.0, suffix)

    # ------------------------------------------------------- nuovi frame

    def append_pose(self, angles, dt, joints=None, composite=False):
        """
        Aggiunge in coda la posa letta dal robot, se valida.
        `joints` sono i giunti con cui e' stata letta: se nel frattempo la sequenza
        e' cambiata (es. caricato un file con altri giunti) la posa non viene aggiunta.
        Ritorna (PoseCheck, indice nuovo o None).
        """
        if joints is not None and list(joints) != self.joints:
            raise SequenceChanged()
        check = self.check_pose(list(angles))
        if not check.ok:
            return check, None
        frame = {"angles": list(angles), "dt": dt}
        if composite:
            frame["composite"] = True
        self.frames.append(frame)
        return check, len(self.frames) - 1

    def insert_after(self, index, frame):
        """Inserisce dopo `index` (in coda se None). Ritorna l'indice del nuovo frame."""
        if index is None:
            self.frames.append(frame)
            return len(self.frames) - 1
        self.frames.insert(index + 1, frame)
        return index + 1

    def copy_to_end(self, index):
        """Duplica il frame in coda (se la sua posa e' valida). Ritorna (PoseCheck, nuovo indice o None)."""
        new_frame = copy.deepcopy(self.frames[index])
        new_frame["copied_from_frame"] = index + 1
        check = self.check_pose(new_frame.get("angles", []))
        if not check.ok:
            return check, None
        self.frames.append(new_frame)
        return check, len(self.frames) - 1

    # --------------------------------------------------------- modifiche

    def _commit_angles(self, index, angles):
        check = self.check_pose(angles)
        if check.ok:
            self.frames[index]["angles"] = angles
        return check

    def set_angle(self, index, joint_index, value):
        angles = self.angles_checked(index)
        angles[joint_index] = value
        return self._commit_angles(index, angles)

    def mirror(self, index, pairs):
        """Copia speculare di un braccio sull'altro. MissingJoints se manca una coppia."""
        angles = self.angles_checked(index)
        for source_joint, target_joint, sign in pairs:
            if source_joint not in self.joints or target_joint not in self.joints:
                raise MissingJoints([source_joint, target_joint])
            angles[self.joints.index(target_joint)] = float(angles[self.joints.index(source_joint)]) * float(sign)
        return self._commit_angles(index, angles)

    def missing_joints(self, joints):
        return [joint for joint in joints if joint not in self.joints]

    def apply_component(self, index, joints, values):
        """Sostituisce nel frame gli angoli di un gruppo (braccio o testa) e lo marca composito."""
        missing = self.missing_joints(joints)
        if missing:
            raise MissingJoints(missing)
        angles = self.angles_checked(index)
        for joint, value in zip(joints, values):
            angles[self.joints.index(joint)] = value
        check = self._commit_angles(index, angles)
        if check.ok:
            self.frames[index]["composite"] = True
        return check

    def set_dt(self, index, dt):
        dt = clamp_dt(dt)
        self.frames[index]["dt"] = dt
        return dt

    def set_all_dt(self, dt):
        for frame in self.frames:
            frame["dt"] = dt

    def set_no_collision(self, index, enabled):
        if enabled:
            self.frames[index][NO_ARM_COLLISION_KEY] = True
        else:
            self.frames[index].pop(NO_ARM_COLLISION_KEY, None)

    def move(self, index, delta):
        """Scambia il frame con il vicino. Ritorna il nuovo indice, None se fuori dai limiti."""
        new_index = index + delta
        if new_index < 0 or new_index >= len(self.frames):
            return None
        self.frames[index], self.frames[new_index] = self.frames[new_index], self.frames[index]
        return new_index

    def remove(self, index):
        if not self.is_index(index):
            return False
        self.frames.pop(index)
        return True

    def clear(self):
        self.frames = []

    # ------------------------------------------------------------- file

    def load_file(self, path):
        """
        Carica una sequenza frames_v1. Rifiuto totale: se i frame non sono coerenti
        la sequenza attuale resta com'e' (InvalidSequenceFile). I giunti sono quelli
        del file. Ritorna il dict letto (nome, catena anti-collisione, ...).
        """
        data = read_json(path)
        if not isinstance(data, dict) or data.get("format") != "frames_v1":
            raise UnsupportedFormat(path)
        joints = data.get("joints")
        frames = data.get("frames")
        problems = check_frames(joints, frames)
        if problems:
            raise InvalidSequenceFile(problems)
        self.joints = list(joints)
        self.frames = list(frames)
        return data

    def save(self, store, path, name, chain):
        """Salva la sequenza; la catena anti-collisione solo se qualche frame la spegne."""
        store.save_frames_sequence(path, name, self.joints, self.frames,
                                   arm_collision_chain=chain if self.collision_windows() else None)
