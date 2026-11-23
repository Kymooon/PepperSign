# -*- coding: utf-8 -*-
"""
Esecuzione dei gesti su Pepper: gesti salvati (frames_v1) e
behavior/animazioni installate sul robot.

Ogni movimento passa da interpolate_locked, che coordina: braccia morbide,
pausa e ripristino dell'autonomia, rigidezza dei giunti, anti-collisione tra
le braccia nelle finestre segnate e segnalazioni di sicurezza.
"""
from __future__ import absolute_import

import time

from peppersign.compat import string_types
from peppersign.robot.interpolation import (
    arm_collision_windows, build_interpolation_from_frames, check_frames, check_gesture, summarize)
from peppersign.robot.joints import VELOCITY_WARN_FRACTION, native_joint_names
from peppersign.robot.safety import SAFETY_CHAINS
from peppersign.utils import normalize_gesture_id


class GesturePlayer(object):
    def __init__(self, robot, limits, autonomy, collision, safety, soft_hold, gesture_store=None):
        self.robot = robot
        self.limits = limits
        self.autonomy = autonomy
        self.collision = collision
        self.safety = safety
        self.soft = soft_hold
        self.gesture_store = gesture_store

    def build_interpolation_from_frames(self, joints, frames):
        return build_interpolation_from_frames(joints, frames, self.limits.clamp_angles)

    def _log_fast_segments(self, joints, times_by_joint, angles_by_joint):
        """Segnala nel log i tratti tra frame che chiedono velocita' vicine al massimo del motore."""
        log = self.robot.log
        try:
            for j, joint in enumerate(joints):
                vmax = self.limits.max_velocity(joint)
                if not vmax:
                    continue
                times = times_by_joint[j]
                values = angles_by_joint[j]
                for k in range(1, len(values)):
                    dt = float(times[k]) - float(times[k - 1])
                    if dt <= 0:
                        continue
                    speed = abs(float(values[k]) - float(values[k - 1])) / dt
                    if speed > VELOCITY_WARN_FRACTION * vmax:
                        log("[LIMITI] Frame %d: %s a %.1f rad/s (%.0f%% del massimo %.1f): "
                            "aumenta il dt di quel frame" % (k + 1, joint, speed, 100 * speed / vmax, vmax))
        except (TypeError, ValueError, OverflowError, IndexError) as exc:
            log("[LIMITI] Controllo delle velocita' non eseguito (dati del gesto non validi: %s)" % exc)

    def _set_gesture_stiffness_locked(self, joints, value=1.0):
        """
        Rigidezza piena sui giunti del gesto, mani comprese. Da chiamare tenendo il lock.
        Gli errori finiscono nel log; per le mani la stiffness viene riletta e, se
        e' ancora bassa, reimpostata giunto per giunto.
        """
        robot = self.robot
        motion = robot.motion
        log = robot.log
        names = native_joint_names(joints)
        if not motion or not names:
            return names
        try:
            motion.setStiffnesses(names, float(value))
        except Exception as exc:
            log("[STIFFNESS] setStiffnesses su %d giunti fallita: %s (riprovo giunto per giunto)"
                % (len(names), str(exc)))
            for name in names:
                try:
                    motion.setStiffnesses(name, float(value))
                except Exception as exc_one:
                    log("[STIFFNESS] %s: %s" % (name, str(exc_one)))
        hands = [name for name in names if name.endswith("Hand")]
        if hands and not robot.is_fake:
            try:
                values = [float(v) for v in motion.getStiffnesses(hands)]
                low = [name for name, v in zip(hands, values) if v < 0.5 * float(value)]
                for name in low:
                    motion.setStiffnesses(name, float(value))
                if low:
                    after = [float(v) for v in motion.getStiffnesses(low)]
                    still = ["%s=%.2f" % (n, v) for n, v in zip(low, after) if v < 0.5 * float(value)]
                    if still:
                        log("[STIFFNESS] Mani ancora senza rigidezza (%s): non si apriranno/chiuderanno"
                            % ", ".join(still))
                    else:
                        log("[STIFFNESS] Rigidezza delle mani reimpostata: %s" % ", ".join(low))
            except Exception as exc:
                log("[STIFFNESS] Verifica rigidezza mani non riuscita: %s" % str(exc))
        return names

    def _gesture_delays(self):
        """Attese (s) prima e dopo il gesto, con l'autonomia gia' in pausa (configurabili)."""
        defaults = self.robot.config.get("robot_defaults", {})
        values = []
        for key, default in (("gesture_pre_delay", 0.8), ("gesture_post_delay", 0.6)):
            try:
                value = float(defaults.get(key, default))
            except (TypeError, ValueError, OverflowError):
                value = default
            values.append(max(0.0, min(value, 5.0)))
        return values[0], values[1]

    def interpolate_locked(self, joints, angles, times, use_buffers=True,
                           collision_windows=None, collision_chain=None):
        """
        angleInterpolation con pausa/ripristino dell'autonomia. Da chiamare tenendo il lock.
        use_buffers: attesa prima (movimenti autonomi fermi, braccia rigide) e dopo il gesto
        (posa finale tenuta) prima di ripristinare l'autonomia.
        """
        robot = self.robot
        log = robot.log
        # braccia morbide attive: le irrigidisco prima di eseguire il gesto
        self.soft.release_for_motion_locked()
        joints = native_joint_names(joints)
        restore = self.autonomy.suspend_for_gesture_locked(joints)
        self._set_gesture_stiffness_locked(joints, 1.0)
        pre_delay, post_delay = self._gesture_delays() if use_buffers else (0.0, 0.0)
        try:
            if pre_delay > 0:
                time.sleep(pre_delay)
            planned = 0.0
            try:
                planned = max(float(t[-1]) if isinstance(t, (list, tuple)) else float(t) for t in times)
            except (TypeError, ValueError, OverflowError, IndexError):
                pass        # durata prevista non calcolabile: salto solo l'avviso sui rallentamenti
            counts_before = self.safety.safety_counts()
            started = time.time()
            scheduler = None
            if collision_windows:
                scheduler = self.collision.start(collision_windows, collision_chain)
            try:
                robot.motion.angleInterpolation(joints, angles, times, True)
            finally:
                if scheduler is not None:
                    self.collision.finish(scheduler)
            elapsed = time.time() - started
            counts_after = self.safety.safety_counts()
            for chain in SAFETY_CHAINS:
                clipped = counts_after.get(chain, 0) - counts_before.get(chain, 0)
                if clipped > 0:
                    obstacle = self.safety.cached_obstacles.get(chain) or {}
                    where = ""
                    if obstacle.get("distance") is not None:
                        where = ": ostacolo a %.0f cm %s" % (100 * obstacle["distance"], obstacle.get("side", ""))
                    log("[SICUREZZA] Durante il gesto il braccio %s e' stato rallentato %d %s%s"
                        % ("SX" if chain == "LArm" else "DX", clipped, "volta" if clipped == 1 else "volte", where))
            if planned > 0 and elapsed > planned + max(0.3, 0.15 * planned):
                hottest = self.safety.hottest_joint()
                log("[GESTO] Durata reale %.1f s invece di %.1f s: il robot e' stato rallentato "
                    "(motori caldi, protezione anti-collisione o velocita' troppo alta)%s"
                    % (elapsed, planned, (" - motore piu' caldo: %s %.0f C" % hottest) if hottest else ""))
            if post_delay > 0:
                time.sleep(post_delay)
        finally:
            self.autonomy.restore_after_gesture_locked(restore)

    def run_frames_gesture(self, joints, frames, collision_chain=None):
        robot = self.robot
        if not robot.motion:
            return False, "ALMotion non disponibile"
        if not joints or not frames:
            return False, "joints/frames mancanti"
        problems = check_frames(joints, frames)
        if problems:
            return self._reject(problems)

        times_by_joint, angles_by_joint = self.build_interpolation_from_frames(joints, frames)
        if not times_by_joint:
            return False, "frames vuoti"
        self._log_fast_segments(joints, times_by_joint, angles_by_joint)
        windows = arm_collision_windows(frames)

        with robot.lock:
            try:
                self.interpolate_locked(joints, angles_by_joint, times_by_joint,
                                        collision_windows=windows, collision_chain=collision_chain)
                return True, "gesture eseguita (%d frame)" % len(frames)
            except Exception as exc:
                return False, "Errore angleInterpolation: %s" % str(exc)

    def _play_dict_gesture(self, target):
        """Gesto salvato (frames_v1, l'unico formato supportato)."""
        problems = check_gesture(target)
        if problems:
            return self._reject(problems)
        return self.run_frames_gesture(target.get("joints", []), target.get("frames"),
                                       collision_chain=target.get("arm_collision_chain"))

    def _reject(self, problems):
        """Gesto non coerente: non viene eseguito niente (nessun valore completato o tagliato)."""
        message = "Gesto non valido, non eseguito: %s" % summarize(problems)
        self.robot.log("[GESTO] %s" % message)
        return False, message

    def _play_string_gesture(self, target):
        robot = self.robot
        if robot.behavior:
            try:
                if robot.behavior.isBehaviorInstalled(target):
                    with robot.lock:
                        robot.behavior.runBehavior(target)
                    return True, "behavior avviato: %s" % target
            except Exception as exc:
                robot.log("[WARN] runBehavior fallita: %s" % str(exc))

        if robot.anim_player:
            try:
                with robot.lock:
                    robot.anim_player.run(target)
                return True, "animazione avviata: %s" % target
            except Exception as exc:
                robot.log("[WARN] animazione fallita: %s" % str(exc))

        return False, "impossibile avviare: %s" % target

    def play_gesture(self, gesture_id):
        gid = normalize_gesture_id(gesture_id)
        if not gid:
            return False, "gestureId vuoto"
        if not self.gesture_store:
            return False, "GestureStore non configurato"

        target = self.gesture_store.get(gid)
        if target is None:
            return False, "gestureId non mappato: %s" % gid

        if isinstance(target, dict):
            return self._play_dict_gesture(target)

        if isinstance(target, string_types):
            return self._play_string_gesture(target)

        return False, "target gesture non supportato"
