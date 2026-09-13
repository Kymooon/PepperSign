# -*- coding: utf-8 -*-
from __future__ import absolute_import

import threading
import time

import qi

from peppersign.audio import get_wav_bytes_from_pepper, record_wav_on_pepper
from peppersign.compat import string_types
from peppersign.gesture_store import ARM_JOINTS, HEAD_JOINTS
from peppersign.http_utils import http_get_json, webapp_upload_audio
from peppersign.utils import clamp, normalize_gesture_id, safe_unicode


LEFT_ARM_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
]

RIGHT_ARM_JOINTS = [
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]


class PepperController(object):
    def __init__(self, config, gesture_store=None, log_cb=None):
        self.config = config
        self.gesture_store = gesture_store
        self.log_cb = log_cb

        self.robot_ip = config["robot"]["ip"]
        self.robot_port = config["robot"]["port"]

        self.session = None
        self.lock = threading.Lock()

        self.tts = None
        self.audio_device = None
        self.animated_speech = None
        self.speaking_movement = None
        self.recorder = None
        self.fileman = None
        self.motion = None
        self.basic_awareness = None
        self.autonomous_life = None
        self.behavior = None
        self.anim_player = None
        self.background_movement = None
        self.listening_movement = None
        self.autonomous_blinking = None

        self.connected_to_webapp = False
        self.last_cmd = None
        self.last_error = ""
        self.running = True
        self.joint_limits = {}

        self.command_handlers = {
            "SAY": self._handle_say,
            "ANIMATED_SAY": self._handle_say_animated,
            "PLAY_GESTURE": self._handle_play_gesture,
            "SAY_AND_LISTEN": self._handle_say_and_listen,
            "WAKEUP": self._handle_wakeup,
            "REST": self._handle_rest,
            "LIFE_ON": self._handle_life_on,
            "LIFE_OFF": self._handle_life_off,
            "NONE": self._handle_none,
        }

    def log(self, message):
        if self.log_cb:
            try:
                self.log_cb(message)
                return
            except Exception:
                pass
        print message

    def set_error(self, message):
        self.last_error = safe_unicode(message)
        if self.last_error:
            self.log("[ERR] %s" % self.last_error)

    def connect(self):
        self.log("[1] Connessione QI...")
        self.session = qi.Session()
        self.session.connect("tcp://%s:%s" % (self.robot_ip, self.robot_port))

        self.tts = self.session.service("ALTextToSpeech")
        self.audio_device = self._try_service("ALAudioDevice")
        self.animated_speech = self._try_service("ALAnimatedSpeech")
        self.speaking_movement = self._try_service("ALSpeakingMovement")
        self.recorder = self.session.service("ALAudioRecorder")
        self.fileman = self.session.service("ALFileManager")
        self.motion = self.session.service("ALMotion")
        self.basic_awareness = self.session.service("ALBasicAwareness")

        self.autonomous_life = self._try_service("ALAutonomousLife")
        self.behavior = self._try_service("ALBehaviorManager")
        self.anim_player = self._try_service("ALAnimationPlayer")
        self.background_movement = self._try_service("ALBackgroundMovement")
        self.listening_movement = self._try_service("ALListeningMovement")
        self.autonomous_blinking = self._try_service("ALAutonomousBlinking")

        with self.lock:
            if self.config["robot_defaults"].get("connect_wakeup", True):
                try:
                    self.motion.wakeUp()
                except Exception as exc:
                    self.log("[WARN] wakeUp fallita in connect: %s" % str(exc))

            if self.config["robot_defaults"].get("stop_basic_awareness_on_connect", True):
                try:
                    if self.basic_awareness.isRunning():
                        self.basic_awareness.stopAwareness()
                except Exception as exc:
                    self.log("[WARN] stopAwareness fallita: %s" % str(exc))

            try:
                self.tts.setLanguage(self.config["robot_defaults"].get("tts_language", "Italian"))
            except Exception as exc:
                self.log("[WARN] setLanguage fallita: %s" % str(exc))

            self._apply_speaking_movement_defaults_locked()

        if self.animated_speech:
            self.log("[OK] ALAnimatedSpeech disponibile")
        else:
            self.log("[WARN] ALAnimatedSpeech non disponibile: ANIMATED_SAY usera il TTS classico")

        if self.audio_device:
            ok, current_volume = self.get_volume()
            if ok:
                self.log("[OK] Volume iniziale: %d%%" % current_volume)
        else:
            self.log("[WARN] ALAudioDevice non disponibile: controlli volume disabilitati")

        self.log("[OK] Pepper connesso. Autonomous Life: %s" % self.get_autonomous_life_state())

    def _try_service(self, service_name):
        try:
            return self.session.service(service_name)
        except Exception as exc:
            self.log("[WARN] Servizio non disponibile %s: %s" % (service_name, str(exc)))
            return None

    def _safe_call(self, service, method_name, label, *args):
        """
        Esegue una chiamata opzionale a un servizio NAOqi senza bloccare il
        programma se il servizio/metodo non esiste su quella versione di Pepper.
        """
        if not service:
            self.log("[AUTO] %s non disponibile" % label)
            return False

        try:
            method = getattr(service, method_name)
            method(*args)
            self.log("[AUTO] %s OK" % label)
            return True
        except Exception as exc:
            self.log("[AUTO] %s FAIL: %s" % (label, str(exc)))
            return False

    def disable_autonomous_stack(self):
        """
        Porta Pepper in una modalita' manuale per la registrazione dei gesti.

        Importante: non modifica il meccanismo di cattura delle pose. Serve solo
        a ridurre i movimenti autonomi prima della registrazione.
        """
        with self.lock:
            if self.behavior:
                try:
                    self.behavior.stopAllBehaviors()
                    self.log("[AUTO] stopAllBehaviors OK")
                except Exception as exc:
                    self.log("[AUTO] stopAllBehaviors FAIL: %s" % str(exc))

            if self.autonomous_life:
                try:
                    self.autonomous_life.setState("disabled")
                    time.sleep(0.3)
                    self.log("[AUTO] Autonomous Life disabled")
                except Exception as exc:
                    self.log("[AUTO] Autonomous Life disable FAIL: %s" % str(exc))
            else:
                self.log("[AUTO] ALAutonomousLife non disponibile")

            if self.basic_awareness:
                try:
                    if self.basic_awareness.isRunning():
                        self.basic_awareness.stopAwareness()
                    self.log("[AUTO] Basic Awareness stopped")
                except Exception as exc:
                    self.log("[AUTO] Basic Awareness stop FAIL: %s" % str(exc))

            self._safe_call(self.background_movement, "setEnabled", "Background Movement OFF", False)
            self._safe_call(self.listening_movement, "setEnabled", "Listening Movement OFF", False)
            self._safe_call(self.speaking_movement, "setEnabled", "Speaking Movement OFF", False)
            self._safe_call(self.autonomous_blinking, "setEnabled", "Autonomous Blinking OFF", False)

            if self.motion:
                try:
                    self.motion.setBreathEnabled("Body", False)
                    self.log("[AUTO] Breath Body OFF")
                except Exception as exc:
                    self.log("[AUTO] Breath Body OFF FAIL: %s" % str(exc))

                try:
                    self.motion.setIdlePostureEnabled("Body", False)
                    self.log("[AUTO] Idle Posture Body OFF")
                except Exception as exc:
                    self.log("[AUTO] Idle Posture Body OFF FAIL: %s" % str(exc))

        return True, "Modalita' manuale attivata: movimenti autonomi disattivati"

    def center_head_forward(self, duration=0.8):
        """
        Porta la testa di Pepper in posizione frontale.

        HeadYaw = 0.0   -> testa centrata, niente rotazione destra/sinistra
        HeadPitch = 0.0 -> sguardo circa dritto davanti a se'

        La funzione viene usata da "Prepara reg." per avere una posa iniziale
        ordinata prima di catturare i frame del gesto.
        """
        if not self.motion:
            return False, "ALMotion non disponibile"

        try:
            duration = float(duration)
        except Exception:
            duration = 0.8
        if duration < 0.2:
            duration = 0.2
        if duration > 3.0:
            duration = 3.0

        joints = list(HEAD_JOINTS)
        target_angles = [0.0, 0.0]
        target_angles = self.clamp_angles_to_limits(joints, target_angles)
        times = [duration for _ in joints]

        with self.lock:
            try:
                # La testa deve avere stiffness attiva per poter raggiungere
                # e mantenere la posizione frontale.
                self.motion.setStiffnesses(joints, 1.0)
                self.motion.angleInterpolation(joints, target_angles, times, True)
                return True, "Testa centrata: guarda dritto davanti a se'"
            except Exception as exc:
                return False, "Errore centratura testa: %s" % str(exc)

    def prepare_gesture_recording(self):
        """
        Prepara Pepper alla registrazione manuale dei keyframe.

        Mantiene il meccanismo originale di registrazione: non blocca pose, non
        corregge gli angoli dei frame e non cambia la logica di Dump Pose.
        In piu' porta la testa in posizione frontale, cosi' la registrazione
        parte da una posa piu' ordinata e ripetibile.
        """
        ok_auto, msg_auto = self.disable_autonomous_stack()

        with self.lock:
            try:
                if self.motion:
                    self.motion.wakeUp()
                    self.log("[REC] wakeUp OK")
            except Exception as exc:
                self.log("[REC] wakeUp FAIL: %s" % str(exc))

        ok_head_center, msg_head_center = self.center_head_forward(duration=0.8)

        # Per le braccia manteniamo il comportamento utile alla registrazione:
        # braccia libere per essere posizionate manualmente.
        ok_arms, msg_arms = self.free_arms()

        # La testa viene lasciata in hold dopo la centratura, altrimenti potrebbe
        # abbassarsi o spostarsi subito dopo "Prepara reg.". Se vuoi muoverla
        # manualmente, puoi comunque premere "Free Head" dalla GUI.
        ok_head, msg_head = self.hold_head()

        ok = ok_auto and ok_head_center and ok_arms and ok_head
        return ok, "Registrazione pronta | %s | %s | %s | %s" % (msg_auto, msg_head_center, msg_arms, msg_head)

    def _to_speech_payload(self, text_u):
        try:
            return text_u.encode("utf-8")
        except Exception:
            return str(text_u)

    def _apply_speaking_movement_defaults_locked(self):
        if not self.speaking_movement:
            return
        defaults = self.config.get("robot_defaults", {})
        if not defaults.get("animated_say_use_speaking_movement", True):
            return
        mode = safe_unicode(defaults.get("animated_say_mode", "contextual")).strip().lower() or "contextual"
        try:
            self.speaking_movement.setMode(mode)
        except Exception as exc:
            self.log("[WARN] ALSpeakingMovement.setMode(%s) fallita: %s" % (mode, str(exc)))

    def _say_plain_locked(self, text_u):
        payload = self._to_speech_payload(text_u)
        try:
            self.tts.say(payload)
            return True
        except Exception:
            try:
                self.tts.say(str(text_u))
                return True
            except Exception as exc:
                self.set_error("TTS fallito: %s" % str(exc))
                return False

    def say(self, text):
        text_u = safe_unicode(text).strip()
        if not text_u:
            return False
        with self.lock:
            return self._say_plain_locked(text_u)

    def say_animated(self, text):
        text_u = safe_unicode(text).strip()
        if not text_u:
            return False, "testo vuoto"

        with self.lock:
            self._apply_speaking_movement_defaults_locked()

            if self.animated_speech:
                try:
                    self.animated_speech.say(self._to_speech_payload(text_u))
                    return True, "animated speech ok"
                except Exception as exc:
                    fallback = self.config["robot_defaults"].get("animated_say_fallback_to_tts", True)
                    if not fallback:
                        self.set_error("Animated speech fallita: %s" % str(exc))
                        return False, "animated speech fallita: %s" % str(exc)

                    self.log("[WARN] AnimatedSpeech fallita, fallback su TTS: %s" % str(exc))
                    if self._say_plain_locked(text_u):
                        return True, "fallback su TTS classico"
                    return False, "animated speech fallita e fallback TTS non riuscito"

            if self._say_plain_locked(text_u):
                return True, "ALAnimatedSpeech non disponibile: usato TTS classico"
            return False, "ALAnimatedSpeech non disponibile e TTS fallito"

    def wakeup(self):
        with self.lock:
            try:
                self.motion.wakeUp()
                return True
            except Exception as exc:
                self.set_error("wakeUp fallito: %s" % str(exc))
                return False

    def rest(self):
        with self.lock:
            try:
                self.motion.rest()
                return True
            except Exception as exc:
                self.set_error("rest fallito: %s" % str(exc))
                return False

    def get_autonomous_life_state(self):
        if not self.autonomous_life:
            return "N/A"
        try:
            return self.autonomous_life.getState()
        except Exception:
            return "ERR"

    def set_autonomous_life(self, enabled):
        if not enabled:
            return self.disable_autonomous_stack()

        with self.lock:
            try:
                self._safe_call(self.background_movement, "setEnabled", "Background Movement ON", True)
                self._safe_call(self.listening_movement, "setEnabled", "Listening Movement ON", True)
                self._safe_call(self.autonomous_blinking, "setEnabled", "Autonomous Blinking ON", True)

                if self.motion:
                    try:
                        self.motion.setBreathEnabled("Body", True)
                        self.log("[AUTO] Breath Body ON")
                    except Exception as exc:
                        self.log("[AUTO] Breath Body ON FAIL: %s" % str(exc))

                    try:
                        self.motion.setIdlePostureEnabled("Body", True)
                        self.log("[AUTO] Idle Posture Body ON")
                    except Exception as exc:
                        self.log("[AUTO] Idle Posture Body ON FAIL: %s" % str(exc))

                if not self.autonomous_life:
                    return False, "ALAutonomousLife non disponibile; movimenti autonomi riabilitati dove possibile"

                try:
                    self.autonomous_life.setState("interactive")
                    return True, "Autonomous Life: interactive"
                except Exception:
                    self.autonomous_life.setState("solitary")
                    return True, "Autonomous Life: solitary"

            except Exception as exc:
                return False, "Errore setState: %s" % str(exc)

    def _get_volume_locked(self):
        value = self.audio_device.getOutputVolume()
        try:
            value = int(round(float(value)))
        except Exception:
            value = int(value)
        return int(clamp(value, 0, 100))

    def _set_volume_locked(self, value):
        volume = int(round(float(value)))
        volume = int(clamp(volume, 0, 100))
        self.audio_device.setOutputVolume(volume)
        return volume

    def _resolve_volume_step(self, step):
        if step is None:
            step = self.config.get("robot_defaults", {}).get("volume_step", 10)
        try:
            step = int(round(float(step)))
        except Exception:
            step = 10
        if step < 1:
            step = 1
        if step > 100:
            step = 100
        return step

    def get_volume(self):
        if not self.audio_device:
            return False, "ALAudioDevice non disponibile"
        with self.lock:
            try:
                return True, self._get_volume_locked()
            except Exception as exc:
                return False, "Errore getOutputVolume: %s" % str(exc)

    def set_volume(self, value):
        if not self.audio_device:
            return False, "ALAudioDevice non disponibile"
        with self.lock:
            try:
                volume = self._set_volume_locked(value)
                return True, "Volume impostato a %d%%" % volume
            except Exception as exc:
                return False, "Errore setOutputVolume: %s" % str(exc)

    def volume_up(self, step=None):
        if not self.audio_device:
            return False, "ALAudioDevice non disponibile"
        delta = self._resolve_volume_step(step)
        with self.lock:
            try:
                current = self._get_volume_locked()
                target = self._set_volume_locked(current + delta)
                return True, "Volume aumentato a %d%%" % target
            except Exception as exc:
                return False, "Errore aumento volume: %s" % str(exc)

    def volume_down(self, step=None):
        if not self.audio_device:
            return False, "ALAudioDevice non disponibile"
        delta = self._resolve_volume_step(step)
        with self.lock:
            try:
                current = self._get_volume_locked()
                target = self._set_volume_locked(current - delta)
                return True, "Volume abbassato a %d%%" % target
            except Exception as exc:
                return False, "Errore riduzione volume: %s" % str(exc)

    def set_stiffness(self, joints, value):
        if not self.motion:
            return False, "ALMotion non disponibile"
        with self.lock:
            try:
                self.motion.setStiffnesses(joints, float(value))
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
        if not self.motion:
            return False, "ALMotion non disponibile"

        hand = safe_unicode(hand_name).strip()
        if hand not in ("LHand", "RHand"):
            return False, "hand non valida: %s" % hand

        with self.lock:
            try:
                if is_open:
                    self.motion.openHand(hand)
                    return True, "%s aperta" % hand
                else:
                    self.motion.closeHand(hand)
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

    def get_pose(self, joints):
        if not self.motion:
            return False, "ALMotion non disponibile"
        with self.lock:
            try:
                angles = self.motion.getAngles(joints, True)
                return True, list(angles)
            except Exception as exc:
                return False, "Errore getAngles: %s" % str(exc)

    def _is_valid_number(self, value):
        try:
            number = float(value)
        except Exception:
            return False

        # Controllo compatibile con Python 2.7: NaN e valori assurdi/non fisici.
        if number != number:
            return False
        if abs(number) > 1000000.0:
            return False
        return True

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
        except Exception:
            errors.append("angoli non convertibili in lista")
            return False, warnings, errors

        if len(angles_list) != len(joints):
            errors.append("numero angoli non coerente: attesi %d, ricevuti %d" % (len(joints), len(angles_list)))
            return False, warnings, errors

        for joint_name, angle in zip(joints, angles_list):
            if not self._is_valid_number(angle):
                errors.append("%s ha un valore non valido: %s" % (safe_unicode(joint_name), safe_unicode(angle)))
                continue

            value = float(angle)
            limits = self._get_joint_limit(joint_name)
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

        return len(errors) == 0, warnings, errors

    def _get_joint_limit(self, joint_name):
        if joint_name in self.joint_limits:
            return self.joint_limits[joint_name]
        try:
            limits = self.motion.getLimits(joint_name)
            joint_min = limits[0][0]
            joint_max = limits[0][1]
            self.joint_limits[joint_name] = (joint_min, joint_max)
            return self.joint_limits[joint_name]
        except Exception:
            return None

    def clamp_angles_to_limits(self, joints, angles):
        if not self.motion:
            return angles
        out = []
        for joint_name, angle in zip(joints, angles):
            limits = self._get_joint_limit(joint_name)
            if not limits:
                out.append(angle)
                continue
            out.append(clamp(angle, limits[0], limits[1]))
        return out

    def _normalize_frame_angles(self, joints, frame_angles):
        normalized = list(frame_angles or [])
        if len(normalized) < len(joints):
            normalized.extend([0.0] * (len(joints) - len(normalized)))
        elif len(normalized) > len(joints):
            normalized = normalized[:len(joints)]
        return self.clamp_angles_to_limits(joints, normalized)

    def build_interpolation_from_frames(self, joints, frames):
        if not joints or not frames:
            return None, None

        total_time = 0.0
        key_times = []
        normalized_frames = []

        for frame in frames:
            dt = frame.get("dt", 0.6)
            try:
                dt = float(dt)
            except Exception:
                dt = 0.6
            if dt < 0.05:
                dt = 0.05
            total_time += dt
            key_times.append(total_time)
            normalized_frames.append(self._normalize_frame_angles(joints, frame.get("angles", [])))

        angles_by_joint = []
        for joint_index in range(len(joints)):
            per_joint = []
            for frame_angles in normalized_frames:
                per_joint.append(frame_angles[joint_index])
            angles_by_joint.append(per_joint)

        times_by_joint = [list(key_times) for _ in joints]
        return times_by_joint, angles_by_joint

    def run_frames_gesture(self, joints, frames):
        if not self.motion:
            return False, "ALMotion non disponibile"
        if not joints or not frames:
            return False, "joints/frames mancanti"

        times_by_joint, angles_by_joint = self.build_interpolation_from_frames(joints, frames)
        if not times_by_joint:
            return False, "frames vuoti"

        with self.lock:
            try:
                self.motion.angleInterpolation(joints, angles_by_joint, times_by_joint, True)
                return True, "gesture eseguita (%d frame)" % len(frames)
            except Exception as exc:
                return False, "Errore angleInterpolation: %s" % str(exc)

    def _sanitize_angle_tracks(self, joints, times, angles):
        sanitized = []
        for joint_name, track in zip(joints, angles):
            limits = self._get_joint_limit(joint_name)
            cleaned_track = []
            for value in track:
                if limits:
                    cleaned_track.append(clamp(value, limits[0], limits[1]))
                else:
                    cleaned_track.append(value)
            sanitized.append(cleaned_track)
        return times, sanitized

    def _play_dict_gesture(self, target):
        joints = target.get("joints", [])
        frames = target.get("frames")
        times = target.get("times")
        angles = target.get("angles")

        if frames and joints:
            return self.run_frames_gesture(joints, frames)

        if joints and times and angles:
            times_clean, angles_clean = self._sanitize_angle_tracks(joints, times, angles)
            with self.lock:
                try:
                    self.motion.angleInterpolation(joints, angles_clean, times_clean, True)
                    return True, "gesture (times/angles) eseguita"
                except Exception as exc:
                    return False, "Errore angleInterpolation: %s" % str(exc)

        return False, "dict gesture non valido (servono joints+frames oppure joints+times+angles)"

    def _play_string_gesture(self, target):
        if self.behavior:
            try:
                if self.behavior.isBehaviorInstalled(target):
                    with self.lock:
                        self.behavior.runBehavior(target)
                    return True, "behavior avviato: %s" % target
            except Exception as exc:
                self.log("[WARN] runBehavior fallita: %s" % str(exc))

        if self.anim_player:
            try:
                with self.lock:
                    self.anim_player.run(target)
                return True, "animazione avviata: %s" % target
            except Exception as exc:
                self.log("[WARN] animazione fallita: %s" % str(exc))

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

    def say_and_listen(self, session_id, prompt):
        sid = safe_unicode(session_id).strip()
        if not sid:
            return False, "sessionId mancante"

        prompt_u = safe_unicode(prompt).strip() or u"Ciao! Dimmi la parola."
        self.say(prompt_u)

        with self.lock:
            try:
                self.log(">>> Registrazione in corso (%d sec)..." % self.config["audio"]["rec_seconds"])
                record_wav_on_pepper(
                    self.recorder,
                    self.config["audio"]["remote_wav"],
                    self.config["audio"]["rec_seconds"],
                )
            except Exception as exc:
                return False, "errore registrazione: %s" % str(exc)

            try:
                wav_bytes = get_wav_bytes_from_pepper(
                    self.fileman,
                    self.config["audio"]["remote_wav"],
                    self.tts,
                )
            except Exception:
                wav_bytes = None

        if (not wav_bytes) or (len(wav_bytes) <= 44):
            self.say("Ho registrato ma l'audio sembra vuoto.")
            return False, "audio vuoto"

        try:
            code, body = webapp_upload_audio(
                self.config["webapp"]["audio_upload_url"],
                sid,
                wav_bytes,
                timeout=self.config["webapp"]["audio_upload_timeout"],
            )
            if code == 200:
                self.say("Audio inviato.")
                return True, "upload ok"
            self.say("Errore durante l'invio dell'audio.")
            return False, "upload status %s, body: %s" % (code, body[:200])
        except Exception as exc:
            self.say("Errore durante l'invio.")
            return False, "upload exc: %s" % str(exc)

    def handle_command(self, cmd):
        action = safe_unicode(cmd.get("action", "")).strip().upper()
        if not action:
            return

        handler = self.command_handlers.get(action)
        if not handler:
            self.log("[POLL] Azione sconosciuta: %s" % action)
            return

        handler(cmd)

    def poll_webapp_loop(self):
        next_url = self.config["webapp"]["next_url"]
        self.log("[POLL] Avviato. Endpoint: %s" % next_url)

        while self.running:
            try:
                cmd = http_get_json(next_url, timeout=self.config["webapp"]["poll_timeout"])
                self.last_cmd = cmd
                if not self.connected_to_webapp:
                    self.say("Connessione alla Web App riuscita. Sono pronto.")
                    self.connected_to_webapp = True
            except Exception as exc:
                if self.connected_to_webapp:
                    self.say("Ho perso la connessione con il computer.")
                self.connected_to_webapp = False
                self.set_error("Polling WebApp fallito: %s" % str(exc))
                time.sleep(self.config["webapp"]["poll_sleep_error"])
                continue

            try:
                self.handle_command(cmd)
            except Exception as exc:
                self.set_error("Errore gestione comando: %s" % str(exc))

            action = safe_unicode(cmd.get("action", "")).strip().upper()
            if not action or action == "NONE":
                time.sleep(self.config["webapp"]["poll_sleep_idle"])
            else:
                time.sleep(self.config["webapp"]["poll_sleep_ok"])

    def _handle_none(self, cmd):
        return

    def _handle_say(self, cmd):
        self.say(cmd.get("text", ""))

    def _handle_say_animated(self, cmd):
        ok, message = self.say_animated(cmd.get("text", ""))
        if not ok:
            self.log("[SAY_ANIMATED] FAIL: %s" % message)

    def _handle_play_gesture(self, cmd):
        ok, message = self.play_gesture(cmd.get("gestureId", ""))
        if not ok:
            self.log("[GESTURE] FAIL: %s" % message)

    def _handle_say_and_listen(self, cmd):
        ok, message = self.say_and_listen(cmd.get("sessionId"), cmd.get("prompt", ""))
        if not ok:
            self.log("[SAY_AND_LISTEN] FAIL: %s" % message)

    def _handle_wakeup(self, cmd):
        self.wakeup()

    def _handle_rest(self, cmd):
        self.rest()

    def _handle_life_on(self, cmd):
        ok, message = self.set_autonomous_life(True)
        if not ok:
            self.log("[LIFE] FAIL: %s" % message)

    def _handle_life_off(self, cmd):
        ok, message = self.set_autonomous_life(False)
        if not ok:
            self.log("[LIFE] FAIL: %s" % message)