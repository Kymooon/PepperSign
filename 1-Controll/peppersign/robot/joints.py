# -*- coding: utf-8 -*-
"""
Giunti di Pepper: liste, limiti, clamp e validazione delle pose.

Le funzioni di questo file non chiamano il robot; solo JointLimits legge i
limiti da ALMotion.getLimits (e li tiene in cache).
"""
from __future__ import absolute_import

from peppersign.compat import string_types
from peppersign.utils import clamp, safe_unicode

LEFT_ARM_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
]

RIGHT_ARM_JOINTS = [
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

# Margine dai fine corsa durante l'esecuzione (rad): un giunto comandato esattamente
# sul fine corsa spinge contro il blocco meccanico (piu' corrente, motore piu' caldo).
EXEC_LIMIT_MARGIN = 0.01
# Sopra questa frazione della velocita' massima di NAOqi un tratto viene segnalato nel log
VELOCITY_WARN_FRACTION = 0.6

# HeadPitch dipende da HeadYaw (collisione con il guscio e il tablet), dalla
# documentazione NAOqi 2.5 "Pepper - Joints": |HeadYaw| (gradi) -> (min, max) HeadPitch (gradi)
HEAD_PITCH_CLAMP = [
    (0.0, -40.5, 25.5),
    (33.33, -40.5, 25.5),
    (61.6, -35.2, 20.9),
    (91.4, -35.1, 13.5),
    (119.5, -35.0, 13.5),
]

RAD_TO_DEG = 57.29577951308232


def native_joint_names(joints):
    """
    Nomi dei giunti come stringhe native (str). In Python 2 i nomi letti dai JSON
    sono unicode: setStiffnesses di NAOqi non li applica (le mani restavano a
    stiffness 0 e non si aprivano/chiudevano durante i gesti).
    """
    if isinstance(joints, string_types):
        joints = [joints]
    return [str(safe_unicode(name).strip()) for name in (joints or [])]


def is_valid_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False

    # Controllo compatibile con Python 2.7: NaN e valori assurdi/non fisici.
    if number != number:
        return False
    if abs(number) > 1000000.0:
        return False
    return True


def head_pitch_limits(head_yaw):
    """Limiti di HeadPitch (rad) per un valore di HeadYaw (rad), tabella della documentazione."""
    yaw = abs(float(head_yaw)) * RAD_TO_DEG
    table = HEAD_PITCH_CLAMP
    if yaw >= table[-1][0]:
        lo, hi = table[-1][1], table[-1][2]
    else:
        lo, hi = table[0][1], table[0][2]
        for (y0, lo0, hi0), (y1, lo1, hi1) in zip(table[:-1], table[1:]):
            if y0 <= yaw <= y1:
                a = (yaw - y0) / (y1 - y0) if y1 > y0 else 0.0
                lo, hi = lo0 + a * (lo1 - lo0), hi0 + a * (hi1 - hi0)
                break
    return lo / RAD_TO_DEG, hi / RAD_TO_DEG


class JointLimits(object):
    """Limiti dei giunti letti dal robot (ALMotion.getLimits), con cache."""

    def __init__(self, robot):
        self.robot = robot
        self.limits = {}       # giunto -> (min, max)
        self.velocity = {}     # giunto -> velocita' massima (rad/s) da getLimits

    def reset(self):
        """Svuota la cache (cambio robot): limiti e velocita' massime vanno riletti dal nuovo robot."""
        self.limits = {}
        self.velocity = {}

    def get(self, joint_name):
        if joint_name in self.limits:
            return self.limits[joint_name]
        if not self.robot.robot_connected:
            return None
        try:
            limits = self.robot.motion.getLimits(joint_name)
            joint_min = limits[0][0]
            joint_max = limits[0][1]
            self.limits[joint_name] = (joint_min, joint_max)
            try:
                self.velocity[joint_name] = float(limits[0][2])
            except (TypeError, ValueError, OverflowError, IndexError):
                pass        # velocita' massima non fornita: il controllo delle velocita' salta il giunto
            return self.limits[joint_name]
        except Exception as exc:
            self.robot.warn_once("limits:" + safe_unicode(joint_name),
                                 "[LIMITI] Limiti di %s non disponibili (%s): il giunto non viene "
                                 "controllato ne' limitato" % (safe_unicode(joint_name), exc))
            return None

    def max_velocity(self, joint_name):
        vmax = self.velocity.get(joint_name)
        if vmax is None:
            self.get(joint_name)
            vmax = self.velocity.get(joint_name)
        return vmax

    def clamp_angles(self, joints, angles, margin=EXEC_LIMIT_MARGIN):
        """
        Limita gli angoli ai fine corsa del robot (getLimits) meno un piccolo margine
        (non per le mani, 0..1) e HeadPitch alla tabella che dipende da HeadYaw.
        Usato solo per l'esecuzione: i frame salvati non vengono modificati.
        """
        if not self.robot.motion:
            return angles
        out = []
        for joint_name, angle in zip(joints, angles):
            limits = self.get(joint_name)
            if not limits:
                out.append(angle)
                continue
            m = 0.0 if joint_name.endswith("Hand") else margin
            out.append(clamp(angle, limits[0] + m, limits[1] - m))
        if "HeadPitch" in joints and "HeadYaw" in joints:
            i_pitch = list(joints).index("HeadPitch")
            i_yaw = list(joints).index("HeadYaw")
            try:
                lo, hi = head_pitch_limits(out[i_yaw])
                out[i_pitch] = clamp(out[i_pitch], lo, hi)
            except (TypeError, ValueError, OverflowError, IndexError):
                pass        # HeadYaw non numerico: HeadPitch resta limitato solo ai fine corsa
        return out

    def validate_frame_pose(self, joints, angles, limit_tolerance=0.03, near_limit_margin=0.05):
        """
        Valida una posa prima di salvarla come frame.

        Non modifica gli angoli e non muove Pepper: serve solo a segnalare
        frame non validi o sospetti durante la registrazione manuale.

        Ritorna:
            (ok, warnings, errors)
        """
        warnings = []
        errors = []

        if not joints:
            errors.append("lista joints vuota")
            return False, warnings, errors

        if angles is None:
            errors.append("angoli mancanti")
            return False, warnings, errors

        try:
            angles_list = list(angles)
        except TypeError:
            errors.append("angoli non convertibili in lista")
            return False, warnings, errors

        if len(angles_list) != len(joints):
            errors.append("numero angoli non coerente: attesi %d, ricevuti %d" % (len(joints), len(angles_list)))
            return False, warnings, errors

        for joint_name, angle in zip(joints, angles_list):
            if not is_valid_number(angle):
                errors.append("%s ha un valore non valido: %s" % (safe_unicode(joint_name), safe_unicode(angle)))
                continue

            value = float(angle)
            limits = self.get(joint_name)
            if not limits:
                # Se Pepper non restituisce i limiti per un giunto, non blocco il salvataggio.
                continue

            joint_min, joint_max = limits

            if value < (joint_min - limit_tolerance) or value > (joint_max + limit_tolerance):
                errors.append(
                    "%s fuori limite: %.4f non in [%.4f, %.4f]"
                    % (safe_unicode(joint_name), value, joint_min, joint_max)
                )
                continue

            # Warning se il giunto e' molto vicino al limite fisico.
            # Il frame resta salvabile, ma l'utente viene avvisato.
            if value <= (joint_min + near_limit_margin):
                warnings.append(
                    "%s vicino al limite minimo: %.4f / min %.4f"
                    % (safe_unicode(joint_name), value, joint_min)
                )
            elif value >= (joint_max - near_limit_margin):
                warnings.append(
                    "%s vicino al limite massimo: %.4f / max %.4f"
                    % (safe_unicode(joint_name), value, joint_max)
                )

        if "HeadPitch" in joints and "HeadYaw" in joints and not errors:
            try:
                yaw = float(angles_list[list(joints).index("HeadYaw")])
                pitch = float(angles_list[list(joints).index("HeadPitch")])
                lo, hi = head_pitch_limits(yaw)
                if pitch < lo - limit_tolerance or pitch > hi + limit_tolerance:
                    warnings.append("HeadPitch %.3f fuori dal range consentito con HeadYaw %.2f ([%.3f, %.3f]): "
                                    "in esecuzione verra' limitato" % (pitch, yaw, lo, hi))
            except (TypeError, ValueError, OverflowError):
                pass        # valori gia' segnalati come non validi sopra

        return len(errors) == 0, warnings, errors
