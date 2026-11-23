# -*- coding: utf-8 -*-
"""
Strumenti per la registrazione dei gesti: stiffness, mani, lettura della posa,
"vai alla posa", braccia morbide, preparazione alla registrazione, wakeUp/rest.
"""
from __future__ import absolute_import

import threading

from peppersign.gesture_store import ARM_JOINTS, HEAD_JOINTS
from peppersign.robot.interpolation import check_frames, summarize
from peppersign.robot.joints import LEFT_ARM_JOINTS, RIGHT_ARM_JOINTS, native_joint_names
from peppersign.utils import safe_unicode

# Modalita' "braccia morbide" per la registrazione (vedi SoftHold.start):
# le mani restano escluse (stiffness piena) per non chiudersi da sole.
SOFT_ARM_JOINTS = {
    "both": [j for j in LEFT_ARM_JOINTS + RIGHT_ARM_JOINTS if not j.endswith("Hand")],
    "left": [j for j in LEFT_ARM_JOINTS if not j.endswith("Hand")],
    "right": [j for j in RIGHT_ARM_JOINTS if not j.endswith("Hand")],
}
SOFT_DEFAULT_STIFFNESS = 0.4
SOFT_FOLLOW_THRESHOLD = 0.05     # rad: oltre questo scarto il robot "accetta" la nuova posizione
SOFT_PERIOD = 0.1                # s
SOFT_FOLLOW_SPEED = 0.4          # frazione della velocita' massima per inseguire la mano dell'operatore


class SoftHold(object):
    """
    Braccia "morbide": stiffness ridotta, quanto basta a sostenere il braccio
    contro la gravita', e un ciclo che aggiorna la posizione comandata quando
    l'operatore sposta il braccio oltre una soglia. Cosi' il braccio si lascia
    muovere a mano e resta dove viene lasciato, invece di cadere (stiffness 0)
    o tornare indietro (stiffness piena). Le mani restano rigide.
    """

    def __init__(self, robot):
        self.robot = robot
        self._soft = None            # stato della modalita' "braccia morbide"
        self._soft_lock = threading.Lock()   # protegge _soft (usato da GUI, WebApp e monitor)

    def state(self):
        """None se la modalita' morbida e' spenta, altrimenti (gruppo, stiffness)."""
        soft = self._soft
        if soft is None:
            return None
        return soft["group"], soft["stiffness"]

    def start(self, group="both", stiffness=SOFT_DEFAULT_STIFFNESS, threshold=SOFT_FOLLOW_THRESHOLD):
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"
        joints = SOFT_ARM_JOINTS.get(group)
        if not joints:
            return False, "gruppo non valido: %s" % group
        try:
            stiffness = float(stiffness)
        except (TypeError, ValueError, OverflowError):
            return False, "stiffness non valida"
        stiffness = max(0.05, min(stiffness, 1.0))
        self.stop(final_stiffness=None)
        with robot.lock:
            try:
                current = robot.motion.getAngles(joints, True)
                robot.motion.setAngles(joints, current, 0.1)     # il comando parte dalla posa attuale
                robot.motion.setStiffnesses(joints, stiffness)
            except Exception as exc:
                return False, "Errore attivazione braccia morbide: %s" % str(exc)
        stop = threading.Event()
        with self._soft_lock:
            previous = self._soft
            self._soft = {"group": group, "joints": joints, "stiffness": stiffness, "stop": stop}
        if previous is not None:          # avvio contemporaneo da un altro thread: resta un solo ciclo
            previous["stop"].set()
        thread = threading.Thread(target=self._loop, args=(joints, threshold, stop))
        thread.daemon = True
        thread.start()
        label = {"both": "entrambe le braccia", "left": "braccio SX", "right": "braccio DX"}[group]
        return True, "Braccia morbide: %s (stiffness %.2f). Sposta il braccio e lascialo: resta in posizione." % (label, stiffness)

    def _loop(self, joints, threshold, stop):
        robot = self.robot
        while not stop.is_set() and robot.running:
            if robot.lock.acquire(False):            # mai in attesa: i comandi della GUI hanno la precedenza
                try:
                    if stop.is_set():
                        break
                    motion = robot.motion
                    sensed = motion.getAngles(joints, True)
                    commanded = motion.getAngles(joints, False)
                    names, targets = [], []
                    for name, s, c in zip(joints, sensed, commanded):
                        if abs(float(s) - float(c)) > threshold:
                            names.append(name)
                            targets.append(float(s))
                    if names:
                        motion.setAngles(names, targets, SOFT_FOLLOW_SPEED)
                except Exception as exc:
                    robot.report("soft_loop", "[MORBIDO] Il braccio non segue la mano dell'operatore: %s" % exc)
                finally:
                    robot.lock.release()
            stop.wait(SOFT_PERIOD)

    def stop(self, final_stiffness=1.0):
        """Spegne la modalita' morbida; final_stiffness=None lascia la stiffness com'e'."""
        robot = self.robot
        soft = self._take()
        if soft is None:
            return False, "Braccia morbide gia' disattivate"
        if final_stiffness is not None and robot.motion:
            with robot.lock:
                try:
                    current = robot.motion.getAngles(soft["joints"], True)
                    robot.motion.setAngles(soft["joints"], current, 0.1)   # resta dove si trova
                    robot.motion.setStiffnesses(soft["joints"], float(final_stiffness))
                except Exception as exc:
                    return False, "Errore disattivazione braccia morbide: %s" % str(exc)
        return True, "Braccia morbide disattivate (braccia rigide)"

    def release_for_motion_locked(self):
        """Prima di un movimento: spegne la modalita' morbida e irrigidisce le braccia (lock gia' preso)."""
        soft = self._take()
        if soft is None:
            return
        try:
            self.robot.motion.setStiffnesses(soft["joints"], 1.0)
        except Exception as exc:
            self.robot.log("[MORBIDO] Irrigidimento delle braccia non riuscito: %s" % exc)
        self.robot.log("[MORBIDO] Disattivato per eseguire il movimento (braccia rigide)")

    def cancel(self):
        """Ferma il ciclo senza toccare il robot (robot disconnesso)."""
        self._take()

    def _take(self):
        """Toglie lo stato delle braccia morbide in modo atomico e ferma il suo ciclo; None se spente."""
        with self._soft_lock:
            soft, self._soft = self._soft, None
        if soft is not None:
            soft["stop"].set()
        return soft


class Recording(object):
    def __init__(self, robot, limits, autonomy, soft_hold, player):
        self.robot = robot
        self.limits = limits
        self.autonomy = autonomy
        self.soft = soft_hold
        self.player = player

    # ------------------------------------------------------------ postura
    def wakeup(self):
        robot = self.robot
        self.soft.stop(final_stiffness=None)
        with robot.lock:
            try:
                robot.motion.wakeUp()
                return True, "wakeUp eseguito"
            except Exception as exc:
                robot.set_error("wakeUp fallito: %s" % str(exc))
                return False, "wakeUp fallito: %s" % str(exc)

    def rest(self):
        robot = self.robot
        self.soft.stop(final_stiffness=None)
        with robot.lock:
            try:
                robot.motion.rest()
                return True, "rest eseguito"
            except Exception as exc:
                robot.set_error("rest fallito: %s" % str(exc))
                return False, "rest fallito: %s" % str(exc)

    # ------------------------------------------------------------ stiffness e mani
    def set_stiffness(self, joints, value):
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"
        self.soft.stop(final_stiffness=None)     # un comando esplicito ha la precedenza
        with robot.lock:
            try:
                robot.motion.setStiffnesses(joints, float(value))
                kind = "list" if isinstance(joints, list) else joints
                return True, "Stiffness set a %.2f su %s" % (float(value), kind)
            except Exception as exc:
                return False, "Errore setStiffnesses: %s" % str(exc)

    def free_arms(self):
        return self.set_stiffness(ARM_JOINTS, 0.0)

    def hold_arms(self):
        return self.set_stiffness(ARM_JOINTS, 1.0)

    def free_left_arm(self):
        return self.set_stiffness(LEFT_ARM_JOINTS, 0.0)

    def hold_left_arm(self):
        return self.set_stiffness(LEFT_ARM_JOINTS, 1.0)

    def free_right_arm(self):
        return self.set_stiffness(RIGHT_ARM_JOINTS, 0.0)

    def hold_right_arm(self):
        return self.set_stiffness(RIGHT_ARM_JOINTS, 1.0)

    def move_only_left_arm(self):
        ok_hold, msg_hold = self.hold_right_arm()
        ok_free, msg_free = self.free_left_arm()
        return ok_hold and ok_free, "Solo braccio SX libero | %s | %s" % (msg_hold, msg_free)

    def move_only_right_arm(self):
        ok_hold, msg_hold = self.hold_left_arm()
        ok_free, msg_free = self.free_right_arm()
        return ok_hold and ok_free, "Solo braccio DX libero | %s | %s" % (msg_hold, msg_free)

    def free_head(self):
        return self.set_stiffness(HEAD_JOINTS, 0.0)

    def hold_head(self):
        return self.set_stiffness(HEAD_JOINTS, 1.0)

    def set_hand(self, hand_name, is_open):
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"

        hand = safe_unicode(hand_name).strip()
        if hand not in ("LHand", "RHand"):
            return False, "hand non valida: %s" % hand

        with robot.lock:
            try:
                if is_open:
                    robot.motion.openHand(hand)
                    return True, "%s aperta" % hand
                else:
                    robot.motion.closeHand(hand)
                    return True, "%s chiusa" % hand
            except Exception as exc:
                return False, "Errore controllo mano %s: %s" % (hand, str(exc))

    def open_hand(self, hand_name):
        return self.set_hand(hand_name, True)

    def close_hand(self, hand_name):
        return self.set_hand(hand_name, False)

    def open_both_hands(self):
        ok_left, msg_left = self.open_hand("LHand")
        ok_right, msg_right = self.open_hand("RHand")
        ok = ok_left and ok_right
        return ok, "%s | %s" % (msg_left, msg_right)

    def close_both_hands(self):
        ok_left, msg_left = self.close_hand("LHand")
        ok_right, msg_right = self.close_hand("RHand")
        ok = ok_left and ok_right
        return ok, "%s | %s" % (msg_left, msg_right)

    # ------------------------------------------------------------ pose
    def get_pose(self, joints):
        """Ritorna (ok, angoli, messaggio); angoli e' None se la lettura non riesce."""
        robot = self.robot
        if not robot.motion:
            return False, None, "ALMotion non disponibile"
        with robot.lock:
            try:
                angles = robot.motion.getAngles(joints, True)
                return True, list(angles), "posa letta"
            except Exception as exc:
                return False, None, "Errore getAngles: %s" % str(exc)

    def go_to_pose(self, joints, angles, min_duration=1.0, max_velocity=0.8):
        """
        Porta il robot nella posa di un frame (stiffness piena), con una durata
        proporzionale allo spostamento piu' grande (max_velocity rad/s, almeno min_duration s).
        """
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"
        if not joints or len(joints) != len(angles):
            return False, "joints/angles non validi"
        problems = check_frames(list(joints), [{"angles": list(angles)}])
        if problems:
            return False, "Posa non valida, nessun movimento: %s" % summarize(problems)
        self.soft.stop(final_stiffness=None)
        with robot.lock:
            try:
                names = native_joint_names(joints)
                current = robot.motion.getAngles(names, True)
                delta = max(abs(float(a) - float(c)) for a, c in zip(angles, current)) if current else 0.0
                duration = max(float(min_duration), delta / float(max_velocity))
                self.player.interpolate_locked(names, [[float(a)] for a in angles],
                                               [[duration] for _ in joints], use_buffers=False)
                return True, "Posa raggiunta in %.1f s" % duration
            except Exception as exc:
                return False, "Errore movimento verso la posa: %s" % str(exc)

    def center_head_forward(self, duration=0.8):
        """
        Porta la testa di Pepper in posizione frontale.

        HeadYaw = 0.0   -> testa centrata, niente rotazione destra/sinistra
        HeadPitch = 0.0 -> sguardo circa dritto davanti a se'

        La funzione viene usata da "Prepara registrazione" per avere una posa iniziale
        ordinata prima di catturare i frame del gesto.
        """
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"

        try:
            duration = float(duration)
        except (TypeError, ValueError, OverflowError):
            duration = 0.8
        if duration < 0.2:
            duration = 0.2
        if duration > 3.0:
            duration = 3.0

        joints = list(HEAD_JOINTS)
        target_angles = [0.0, 0.0]
        target_angles = self.limits.clamp_angles(joints, target_angles)
        times = [duration for _ in joints]

        with robot.lock:
            try:
                # La testa deve avere stiffness attiva per poter raggiungere
                # e mantenere la posizione frontale.
                robot.motion.setStiffnesses(joints, 1.0)
                robot.motion.angleInterpolation(joints, target_angles, times, True)
                return True, "Testa centrata: guarda dritto davanti a se'"
            except Exception as exc:
                return False, "Errore centratura testa: %s" % str(exc)

    def prepare_gesture_recording(self):
        """
        Prepara Pepper alla registrazione manuale dei keyframe.

        Mantiene il meccanismo originale di registrazione: non blocca pose, non
        corregge gli angoli dei frame e non cambia la logica di Cattura posa.
        In piu' porta la testa in posizione frontale, cosi' la registrazione
        parte da una posa piu' ordinata e ripetibile.
        """
        robot = self.robot
        ok_auto, msg_auto = self.autonomy.disable_stack()

        with robot.lock:
            try:
                if robot.motion:
                    robot.motion.wakeUp()
                    robot.log("[REC] wakeUp OK")
            except Exception as exc:
                robot.log("[REC] wakeUp FAIL: %s" % str(exc))

        ok_head_center, msg_head_center = self.center_head_forward(duration=0.8)

        # Per le braccia manteniamo il comportamento utile alla registrazione:
        # braccia libere per essere posizionate manualmente.
        ok_arms, msg_arms = self.free_arms()

        # La testa viene lasciata in hold dopo la centratura, altrimenti potrebbe
        # abbassarsi o spostarsi subito dopo "Prepara registrazione". Se vuoi muoverla
        # manualmente, puoi comunque premere "Sblocca testa" dalla GUI.
        ok_head, msg_head = self.hold_head()

        ok = ok_auto and ok_head_center and ok_arms and ok_head
        return ok, "Registrazione pronta | %s | %s | %s | %s" % (msg_auto, msg_head_center, msg_arms, msg_head)
