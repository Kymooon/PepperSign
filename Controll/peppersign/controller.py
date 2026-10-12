# -*- coding: utf-8 -*-
from __future__ import absolute_import

import math
import threading
import time

from peppersign.config import fake_robot_enabled

import socket


def load_qi(fake):
    """
    Modulo qi da usare: robot simulato (fake_qi.py, modalita' demo) oppure
    SDK NAOqi reale. L'import e' fatto qui e non all'avvio del file, cosi'
    dalla GUI si puo' passare da demo a robot reale senza riavviare.
    """
    if fake:
        from peppersign import fake_qi
        return fake_qi
    import qi
    return qi


def validate_robot_address(ip, port):
    """Ritorna (ok, ip, port, messaggio). Accetta un IP o un nome host."""
    ip = safe_unicode(ip).strip()
    if not ip:
        return False, ip, port, "Indirizzo del robot vuoto"
    if " " in ip or "/" in ip or ":" in ip:
        return False, ip, port, "Indirizzo non valido: %s (scrivi solo l'IP, es. 192.168.0.110)" % ip
    try:
        port = int(safe_unicode(port).strip())
    except Exception:
        return False, ip, port, "Porta non valida: %s" % safe_unicode(port)
    if port < 1 or port > 65535:
        return False, ip, port, "Porta fuori intervallo: %d" % port
    try:
        socket.getaddrinfo(str(ip), port)
    except Exception:
        return False, ip, port, "Indirizzo non risolvibile: %s" % ip
    return True, ip, port, ""

from peppersign.audio import get_wav_bytes_from_pepper, record_wav_on_pepper
from peppersign.compat import string_types
from peppersign.gesture_store import ARM_JOINTS, HEAD_JOINTS
from peppersign.http_utils import http_get_json, webapp_upload_audio
from peppersign.utils import clamp, normalize_gesture_id, safe_unicode, tcp_check


LEFT_ARM_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
]

RIGHT_ARM_JOINTS = [
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]

# Modalita' "braccia morbide" per la registrazione (vedi start_soft_hold):
# le mani restano escluse (stiffness piena) per non chiudersi da sole.
SOFT_ARM_JOINTS = {
    "both": [j for j in LEFT_ARM_JOINTS + RIGHT_ARM_JOINTS if not j.endswith("Hand")],
    "left": [j for j in LEFT_ARM_JOINTS if not j.endswith("Hand")],
    "right": [j for j in RIGHT_ARM_JOINTS if not j.endswith("Hand")],
}
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

# Temperatura dei motori (letta da ALMemory nel thread di monitoraggio)
TEMPERATURE_JOINTS = [
    "HeadYaw", "HeadPitch",
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
]
TEMPERATURE_PERIOD_TICKS = 3        # lettura ogni ~3 s
# Soglie indicative (gradi C) usate solo se NAOqi non fornisce lo stato del sensore
TEMPERATURE_WARM = 60.0
TEMPERATURE_HOT = 70.0

# Protezioni di ALMotion mostrate nella scheda "Sicurezza e motori":
# chiave -> (etichetta, tipo, nome NAOqi, disattivabile dalla GUI)
PROTECTIONS = [
    ("external_LArm", "Anti-collisione esterna braccio SX", "external", "LArm", True),
    ("external_RArm", "Anti-collisione esterna braccio DX", "external", "RArm", True),
    ("self_Arms", "Anti-collisione con il proprio corpo (braccia)", "self", "Arms", True),
    ("smart_stiffness", "Smart stiffness (riduce la forza a riposo)", "smart", None, True),
    ("diagnosis", "Riduzione della forza per temperatura/errori", "diagnosis", None, False),
]
SAFETY_CHAINS = ("LArm", "RArm")
OBSTACLE_MAX_DISTANCE = 3.0      # m: oltre, l'ostacolo non viene mostrato

SOFT_DEFAULT_STIFFNESS = 0.4
SOFT_FOLLOW_THRESHOLD = 0.05     # rad: oltre questo scarto il robot "accetta" la nuova posizione
SOFT_PERIOD = 0.1                # s
SOFT_FOLLOW_SPEED = 0.4          # frazione della velocita' massima per inseguire la mano dell'operatore


class PepperController(object):
    def __init__(self, config, gesture_store=None, log_cb=None):
        self.config = config
        self.gesture_store = gesture_store
        self.log_cb = log_cb

        self.robot_ip = config["robot"]["ip"]
        self.robot_port = config["robot"]["port"]

        # Robot simulato (demo) o reale: modificabile dalla GUI (configure_target)
        self.fake_robot = fake_robot_enabled()
        self.qi = load_qi(self.fake_robot)

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

        # Stato della connessione con il robot (aggiornato da monitor_loop).
        # La GUI legge solo questi valori in cache: non chiama mai il robot
        # dal thread grafico, cosi' la finestra non si blocca.
        self.robot_connected = False
        self.connection_state = "NON CONNESSO"
        self.cached_volume = None
        self.cached_life_state = "N/A"
        self.reconnect_interval = float(config["robot"].get("reconnect_interval", 5))
        self._monitor_wake = threading.Event()
        self._reconnect_requested = False
        self._reconnect_failures = 0
        self._soft = None            # stato della modalita' "braccia morbide"
        self.memory = None
        self.cached_temperatures = {}    # giunto -> (gradi C, stato NAOqi o None)
        self._temperature_levels = {}    # giunto -> livello gia' segnalato nel log
        self.joint_velocity = {}         # giunto -> velocita' massima (rad/s) da getLimits
        # Sicurezza: protezioni, ostacoli vicini alle braccia, rallentamenti
        self.cached_protections = {}     # chiave -> True/False/None (None = non disponibile)
        self._protection_originals = {}  # chiave -> valore prima delle modifiche dalla GUI
        self.cached_obstacles = {}       # catena -> dict(distance, side, position) oppure None
        self.safety_events = dict((c, {"count": 0, "last": 0.0}) for c in SAFETY_CHAINS)
        self._safety_lock = threading.Lock()
        self._clip_subscriber = None

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
        self.connection_state = "CONNESSIONE..."
        self._close_session()
        self.session = self.qi.Session()
        if getattr(self.qi, "IS_FAKE", False):
            # I comandi ricevuti dal robot simulato compaiono nel log della GUI.
            self.session.set_logger(self.log)
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
        self.memory = self._try_service("ALMemory")
        self._subscribe_safety_events()

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

        self.cached_life_state = self.get_autonomous_life_state()
        self.robot_connected = True
        self.connection_state = "CONNESSO"
        self._reconnect_failures = 0
        self.log("[OK] Pepper connesso. Autonomous Life: %s" % self.cached_life_state)
        self.log("[INFO] Autonomia durante i gesti: %s" % self._gesture_autonomy_mode())

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
        self.stop_soft_hold(final_stiffness=None)
        with self.lock:
            try:
                self.motion.wakeUp()
                return True
            except Exception as exc:
                self.set_error("wakeUp fallito: %s" % str(exc))
                return False

    def rest(self):
        self.stop_soft_hold(final_stiffness=None)
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
        value = int(clamp(value, 0, 100))
        self.cached_volume = value
        return value

    def _set_volume_locked(self, value):
        volume = int(round(float(value)))
        volume = int(clamp(volume, 0, 100))
        self.audio_device.setOutputVolume(volume)
        self.cached_volume = volume
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
        self.stop_soft_hold(final_stiffness=None)     # un comando esplicito ha la precedenza
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

    # ------------------------------------------------------------------
    # Registrazione: andare alla posa di un frame e braccia "morbide"
    # ------------------------------------------------------------------

    def go_to_pose(self, joints, angles, min_duration=1.0, max_velocity=0.8):
        """
        Porta il robot nella posa di un frame (stiffness piena), con una durata
        proporzionale allo spostamento piu' grande (max_velocity rad/s, almeno min_duration s).
        """
        if not self.motion:
            return False, "ALMotion non disponibile"
        if not joints or len(joints) != len(angles):
            return False, "joints/angles non validi"
        self.stop_soft_hold(final_stiffness=None)
        with self.lock:
            try:
                current = self.motion.getAngles(list(joints), True)
                delta = max(abs(float(a) - float(c)) for a, c in zip(angles, current)) if current else 0.0
                duration = max(float(min_duration), delta / float(max_velocity))
                self.motion.setStiffnesses(list(joints), 1.0)
                self._interpolate_gesture_locked(list(joints), [[float(a)] for a in angles],
                                                 [[duration] for _ in joints], use_buffers=False)
                return True, "Posa raggiunta in %.1f s" % duration
            except Exception as exc:
                return False, "Errore movimento verso la posa: %s" % str(exc)

    def soft_hold_state(self):
        """None se la modalita' morbida e' spenta, altrimenti (gruppo, stiffness)."""
        soft = self._soft
        if soft is None:
            return None
        return soft["group"], soft["stiffness"]

    def start_soft_hold(self, group="both", stiffness=SOFT_DEFAULT_STIFFNESS, threshold=SOFT_FOLLOW_THRESHOLD):
        """
        Braccia "morbide": stiffness ridotta, quanto basta a sostenere il braccio
        contro la gravita', e un ciclo che aggiorna la posizione comandata quando
        l'operatore sposta il braccio oltre `threshold`. Cosi' il braccio si lascia
        muovere a mano e resta dove viene lasciato, invece di cadere (stiffness 0)
        o tornare indietro (stiffness piena). Le mani restano rigide.
        """
        if not self.motion:
            return False, "ALMotion non disponibile"
        joints = SOFT_ARM_JOINTS.get(group)
        if not joints:
            return False, "gruppo non valido: %s" % group
        try:
            stiffness = float(stiffness)
        except Exception:
            return False, "stiffness non valida"
        stiffness = max(0.05, min(stiffness, 1.0))
        self.stop_soft_hold(final_stiffness=None)
        with self.lock:
            try:
                current = self.motion.getAngles(joints, True)
                self.motion.setAngles(joints, current, 0.1)     # il comando parte dalla posa attuale
                self.motion.setStiffnesses(joints, stiffness)
            except Exception as exc:
                return False, "Errore attivazione braccia morbide: %s" % str(exc)
        stop = threading.Event()
        self._soft = {"group": group, "joints": joints, "stiffness": stiffness, "stop": stop}
        thread = threading.Thread(target=self._soft_hold_loop, args=(joints, threshold, stop))
        thread.daemon = True
        thread.start()
        label = {"both": "entrambe le braccia", "left": "braccio SX", "right": "braccio DX"}[group]
        return True, "Braccia morbide: %s (stiffness %.2f). Sposta il braccio e lascialo: resta in posizione." % (label, stiffness)

    def _soft_hold_loop(self, joints, threshold, stop):
        while not stop.is_set() and self.running:
            if self.lock.acquire(False):            # mai in attesa: i comandi della GUI hanno la precedenza
                try:
                    if stop.is_set():
                        break
                    sensed = self.motion.getAngles(joints, True)
                    commanded = self.motion.getAngles(joints, False)
                    names, targets = [], []
                    for name, s, c in zip(joints, sensed, commanded):
                        if abs(float(s) - float(c)) > threshold:
                            names.append(name)
                            targets.append(float(s))
                    if names:
                        self.motion.setAngles(names, targets, SOFT_FOLLOW_SPEED)
                except Exception:
                    pass
                finally:
                    self.lock.release()
            stop.wait(SOFT_PERIOD)

    def stop_soft_hold(self, final_stiffness=1.0):
        """Spegne la modalita' morbida; final_stiffness=None lascia la stiffness com'e'."""
        soft = self._soft
        if soft is None:
            return False, "Braccia morbide gia' disattivate"
        soft["stop"].set()
        self._soft = None
        if final_stiffness is not None and self.motion:
            with self.lock:
                try:
                    current = self.motion.getAngles(soft["joints"], True)
                    self.motion.setAngles(soft["joints"], current, 0.1)   # resta dove si trova
                    self.motion.setStiffnesses(soft["joints"], float(final_stiffness))
                except Exception as exc:
                    return False, "Errore disattivazione braccia morbide: %s" % str(exc)
        return True, "Braccia morbide disattivate (braccia rigide)"

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

        if "HeadPitch" in joints and "HeadYaw" in joints and not errors:
            try:
                yaw = float(angles_list[list(joints).index("HeadYaw")])
                pitch = float(angles_list[list(joints).index("HeadPitch")])
                lo, hi = self.head_pitch_limits(yaw)
                if pitch < lo - limit_tolerance or pitch > hi + limit_tolerance:
                    warnings.append("HeadPitch %.3f fuori dal range consentito con HeadYaw %.2f ([%.3f, %.3f]): "
                                    "in esecuzione verra' limitato" % (pitch, yaw, lo, hi))
            except Exception:
                pass

        return len(errors) == 0, warnings, errors

    def _get_joint_limit(self, joint_name):
        if joint_name in self.joint_limits:
            return self.joint_limits[joint_name]
        if not self.robot_connected:
            return None
        try:
            limits = self.motion.getLimits(joint_name)
            joint_min = limits[0][0]
            joint_max = limits[0][1]
            self.joint_limits[joint_name] = (joint_min, joint_max)
            try:
                self.joint_velocity[joint_name] = float(limits[0][2])
            except Exception:
                pass
            return self.joint_limits[joint_name]
        except Exception:
            return None

    @staticmethod
    def head_pitch_limits(head_yaw):
        """Limiti di HeadPitch (rad) per un valore di HeadYaw (rad), tabella della documentazione."""
        yaw = abs(float(head_yaw)) * 57.29577951308232
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
        return lo / 57.29577951308232, hi / 57.29577951308232

    def clamp_angles_to_limits(self, joints, angles, margin=EXEC_LIMIT_MARGIN):
        """
        Limita gli angoli ai fine corsa del robot (getLimits) meno un piccolo margine
        (non per le mani, 0..1) e HeadPitch alla tabella che dipende da HeadYaw.
        Usato solo per l'esecuzione: i frame salvati non vengono modificati.
        """
        if not self.motion:
            return angles
        out = []
        for joint_name, angle in zip(joints, angles):
            limits = self._get_joint_limit(joint_name)
            if not limits:
                out.append(angle)
                continue
            m = 0.0 if joint_name.endswith("Hand") else margin
            out.append(clamp(angle, limits[0] + m, limits[1] - m))
        if "HeadPitch" in joints and "HeadYaw" in joints:
            i_pitch = list(joints).index("HeadPitch")
            i_yaw = list(joints).index("HeadYaw")
            try:
                lo, hi = self.head_pitch_limits(out[i_yaw])
                out[i_pitch] = clamp(out[i_pitch], lo, hi)
            except Exception:
                pass
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

    # ------------------------------------------------------------------
    # Autonomia durante i gesti
    # ------------------------------------------------------------------
    # Autonomous Life puo' restare attiva: subito prima di ogni gesto vengono
    # messi in pausa solo i movimenti autonomi che interferiscono con le
    # braccia (e con la testa, se il gesto la usa); subito dopo viene
    # ripristinato esattamente lo stato precedente.

    GESTURE_AUTONOMY_MODES = ("pause", "off", "none")

    # (nome ability per ALAutonomousLife, attributo del servizio dedicato)
    ARM_ABILITIES = [
        ("BackgroundMovement", "background_movement"),
        ("ListeningMovement", "listening_movement"),
        ("SpeakingMovement", "speaking_movement"),
    ]

    def _log_fast_segments(self, joints, times_by_joint, angles_by_joint):
        """Segnala nel log i tratti tra frame che chiedono velocita' vicine al massimo del motore."""
        try:
            for j, joint in enumerate(joints):
                vmax = self.joint_velocity.get(joint)
                if vmax is None:
                    self._get_joint_limit(joint)
                    vmax = self.joint_velocity.get(joint)
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
                        self.log("[LIMITI] Frame %d: %s a %.1f rad/s (%.0f%% del massimo %.1f): "
                                 "aumenta il dt di quel frame" % (k + 1, joint, speed, 100 * speed / vmax, vmax))
        except Exception:
            pass

    def _gesture_autonomy_mode(self):
        mode = self.config.get("robot_defaults", {}).get("gesture_autonomy", "pause")
        mode = safe_unicode(mode).strip().lower()
        if mode not in self.GESTURE_AUTONOMY_MODES:
            return "pause"
        return mode

    def _get_ability_enabled(self, ability, service_attr):
        """Stato attuale di una autonomous ability (True/False) o None se ignoto."""
        if self.autonomous_life:
            try:
                return bool(self.autonomous_life.getAutonomousAbilityEnabled(ability))
            except Exception:
                pass
        service = getattr(self, service_attr, None) if service_attr else None
        if service:
            try:
                value = service.isEnabled()
                if value is not None:
                    return bool(value)
            except Exception:
                pass
        return None

    def _set_ability_enabled(self, ability, service_attr, enabled):
        if self.autonomous_life:
            try:
                self.autonomous_life.setAutonomousAbilityEnabled(ability, bool(enabled))
                return True
            except Exception:
                pass
        service = getattr(self, service_attr, None) if service_attr else None
        if service:
            try:
                service.setEnabled(bool(enabled))
                return True
            except Exception:
                pass
        return False

    def _suspend_autonomy_locked(self, joints):
        """
        Mette in pausa i movimenti autonomi in conflitto con il gesto.
        Ritorna la lista di azioni di ripristino (da passare a _restore_autonomy_locked).
        Da chiamare tenendo self.lock. Ogni chiamata e' protetta: se una API non
        esiste su questa versione di NAOqi, il gesto parte comunque.
        """
        mode = self._gesture_autonomy_mode()
        restore = []
        paused = []
        if mode == "none":
            return restore

        joint_set = set(joints or [])
        uses_head = bool(joint_set.intersection(HEAD_JOINTS))
        chain = "Body" if mode == "off" else "Arms"

        # 1) respiro e postura di riposo (su braccia, o su tutto il corpo in "off")
        if self.motion:
            for getter, setter, label in (
                ("getBreathEnabled", "setBreathEnabled", "Breath"),
                ("getIdlePostureEnabled", "setIdlePostureEnabled", "IdlePosture"),
            ):
                try:
                    # tocco solo cio' che e' sicuramente attivo, cosi' il ripristino
                    # non accende mai qualcosa che era spento
                    if getattr(self.motion, getter)(chain):
                        getattr(self.motion, setter)(chain, False)
                        restore.append(("motion", setter, chain, True))
                        paused.append("%s %s" % (label, chain))
                except Exception:
                    pass

        # 2) movimenti autonomi che agiscono sulle braccia
        abilities = list(self.ARM_ABILITIES)
        if mode == "off":
            abilities.append(("AutonomousBlinking", "autonomous_blinking"))
        for ability, service_attr in abilities:
            previous = self._get_ability_enabled(ability, service_attr)
            if previous is False:
                continue
            if self._set_ability_enabled(ability, service_attr, False):
                restore.append(("ability", ability, service_attr, True))
                paused.append(ability)

        # 3) BasicAwareness: in pausa se il gesto usa la testa (o in "off");
        #    altrimenti resta attiva ma solo con la testa, senza ruotare la base.
        if self.basic_awareness:
            if uses_head or mode == "off":
                previous = self._get_ability_enabled("BasicAwareness", None)
                if previous is None:
                    try:
                        previous = bool(self.basic_awareness.isRunning())
                    except Exception:
                        previous = None
                if previous:
                    done = self._set_ability_enabled("BasicAwareness", None, False)
                    if not done:
                        try:
                            self.basic_awareness.pauseAwareness()
                            done = True
                            restore.append(("call", self.basic_awareness, "resumeAwareness", ()))
                        except Exception:
                            try:
                                self.basic_awareness.stopAwareness()
                                done = True
                                restore.append(("call", self.basic_awareness, "startAwareness", ()))
                            except Exception:
                                pass
                    else:
                        restore.append(("ability", "BasicAwareness", None, True))
                    if done:
                        paused.append("BasicAwareness")
            else:
                try:
                    previous_mode = self.basic_awareness.getTrackingMode()
                    if previous_mode and safe_unicode(previous_mode) != u"Head":
                        self.basic_awareness.setTrackingMode("Head")
                        restore.append(("call", self.basic_awareness, "setTrackingMode", (previous_mode,)))
                        paused.append("TrackingMode %s->Head" % safe_unicode(previous_mode))
                except Exception:
                    pass

        # 4) rigidezza piena sui giunti del gesto
        if self.motion and joints:
            try:
                self.motion.setStiffnesses(list(joints), 1.0)
            except Exception:
                pass

        if paused:
            self.log("[AUTONOMY] Pausa per il gesto (%s): %s" % (mode, ", ".join(paused)))
        return restore

    def _restore_autonomy_locked(self, restore):
        """Ripristina, in ordine inverso, quanto messo in pausa da _suspend_autonomy_locked."""
        if not restore:
            return
        for item in reversed(restore):
            try:
                kind = item[0]
                if kind == "motion":
                    _, setter, chain, value = item
                    getattr(self.motion, setter)(chain, value)
                elif kind == "ability":
                    _, ability, service_attr, value = item
                    self._set_ability_enabled(ability, service_attr, value)
                elif kind == "call":
                    _, service, method, args = item
                    getattr(service, method)(*args)
            except Exception as exc:
                self.log("[AUTONOMY] Ripristino non riuscito (%s): %s" % (item[1], str(exc)))
        self.log("[AUTONOMY] Movimenti autonomi ripristinati")

    def _gesture_delays(self):
        """Attese (s) prima e dopo il gesto, con l'autonomia gia' in pausa (configurabili)."""
        defaults = self.config.get("robot_defaults", {})
        values = []
        for key, default in (("gesture_pre_delay", 0.8), ("gesture_post_delay", 0.6)):
            try:
                value = float(defaults.get(key, default))
            except Exception:
                value = default
            values.append(max(0.0, min(value, 5.0)))
        return values[0], values[1]

    def _interpolate_gesture_locked(self, joints, angles, times, use_buffers=True):
        """
        angleInterpolation con pausa/ripristino dell'autonomia. Da chiamare tenendo self.lock.
        use_buffers: attesa prima (movimenti autonomi fermi, braccia rigide) e dopo il gesto
        (posa finale tenuta) prima di ripristinare l'autonomia.
        """
        soft = self._soft
        if soft is not None:
            # braccia morbide attive: le irrigidisco prima di eseguire il gesto
            soft["stop"].set()
            self._soft = None
            try:
                self.motion.setStiffnesses(soft["joints"], 1.0)
            except Exception:
                pass
            self.log("[MORBIDO] Disattivato per eseguire il movimento (braccia rigide)")
        restore = self._suspend_autonomy_locked(joints)
        pre_delay, post_delay = self._gesture_delays() if use_buffers else (0.0, 0.0)
        try:
            if pre_delay > 0:
                time.sleep(pre_delay)
            planned = 0.0
            try:
                planned = max(float(t[-1]) if isinstance(t, (list, tuple)) else float(t) for t in times)
            except Exception:
                pass
            counts_before = self.safety_counts()
            started = time.time()
            self.motion.angleInterpolation(joints, angles, times, True)
            elapsed = time.time() - started
            counts_after = self.safety_counts()
            for chain in SAFETY_CHAINS:
                clipped = counts_after.get(chain, 0) - counts_before.get(chain, 0)
                if clipped > 0:
                    obstacle = self.cached_obstacles.get(chain) or {}
                    where = ""
                    if obstacle.get("distance") is not None:
                        where = ": ostacolo a %.0f cm %s" % (100 * obstacle["distance"], obstacle.get("side", ""))
                    self.log("[SICUREZZA] Durante il gesto il braccio %s e' stato rallentato %d %s%s"
                             % ("SX" if chain == "LArm" else "DX", clipped, "volta" if clipped == 1 else "volte", where))
            if planned > 0 and elapsed > planned + max(0.3, 0.15 * planned):
                hottest = self.hottest_joint()
                self.log("[GESTO] Durata reale %.1f s invece di %.1f s: il robot e' stato rallentato "
                         "(motori caldi, protezione anti-collisione o velocita' troppo alta)%s"
                         % (elapsed, planned, (" - motore piu' caldo: %s %.0f C" % hottest) if hottest else ""))
            if post_delay > 0:
                time.sleep(post_delay)
        finally:
            self._restore_autonomy_locked(restore)

    def run_frames_gesture(self, joints, frames):
        if not self.motion:
            return False, "ALMotion non disponibile"
        if not joints or not frames:
            return False, "joints/frames mancanti"

        times_by_joint, angles_by_joint = self.build_interpolation_from_frames(joints, frames)
        if not times_by_joint:
            return False, "frames vuoti"
        self._log_fast_segments(joints, times_by_joint, angles_by_joint)

        with self.lock:
            try:
                self._interpolate_gesture_locked(joints, angles_by_joint, times_by_joint)
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
                    self._interpolate_gesture_locked(joints, angles_clean, times_clean)
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

    # ------------------------------------------------------------------
    # Monitor della connessione: rileva la disconnessione del robot,
    # aggiorna i valori di stato in cache e riconnette automaticamente.
    # Gira in un thread separato (avviato da main.py).
    # ------------------------------------------------------------------

    def _close_session(self):
        session = self.session
        if session is None:
            return
        try:
            session.close()
        except Exception:
            pass

    def _session_alive(self, check_tcp):
        try:
            if self.session is None or not self.session.isConnected():
                return False
        except Exception:
            return False
        if check_tcp and not getattr(self.qi, "IS_FAKE", False):
            return tcp_check(self.robot_ip, self.robot_port, timeout=2)
        return True

    # ------------------------------------------------------------------
    # Sicurezza: protezioni di ALMotion, ostacoli vicini alle braccia,
    # rallentamenti delle braccia (evento ALMotion/Safety/ChainVelocityClipped)
    # ------------------------------------------------------------------

    def _subscribe_safety_events(self):
        self._clip_subscriber = None
        if not self.memory:
            return
        try:
            subscriber = self.memory.subscriber("ALMotion/Safety/ChainVelocityClipped")
            subscriber.signal.connect(self._on_chain_velocity_clipped)
            self._clip_subscriber = subscriber      # va tenuto in vita
        except Exception as exc:
            self.log("[SICUREZZA] Evento dei rallentamenti non disponibile: %s" % str(exc))

    def _on_chain_velocity_clipped(self, value):
        """Callback NAOqi: value = [[nome catena, posizione ostacolo], ...]."""
        now = time.time()
        try:
            items = list(value or [])
        except Exception:
            items = []
        with self._safety_lock:
            for item in items:
                try:
                    chain = str(item[0])
                except Exception:
                    continue
                if chain in ("LArm", "RArm"):
                    chains = [chain]
                elif chain in ("Arms", "Body", "All"):
                    chains = list(SAFETY_CHAINS)
                else:
                    continue
                for c in chains:
                    event = self.safety_events.setdefault(c, {"count": 0, "last": 0.0})
                    event["count"] += 1
                    event["last"] = now

    def safety_counts(self):
        with self._safety_lock:
            return dict((c, self.safety_events.get(c, {}).get("count", 0)) for c in SAFETY_CHAINS)

    def reset_safety_counts(self):
        with self._safety_lock:
            for event in self.safety_events.values():
                event["count"] = 0
                event["last"] = 0.0

    def _read_protection(self, kind, name):
        if kind == "external":
            return bool(self.motion.getExternalCollisionProtectionEnabled(name))
        if kind == "self":
            return bool(self.motion.getCollisionProtectionEnabled(name))
        if kind == "smart":
            return bool(self.motion.getSmartStiffnessEnabled())
        if kind == "diagnosis":
            return bool(self.motion.getDiagnosisEffectEnabled())
        return None

    def refresh_protections(self):
        """Legge lo stato delle protezioni (senza lock). None = non disponibile su questo robot."""
        if not self.motion:
            return
        result = {}
        for key, _, kind, name, _ in PROTECTIONS:
            try:
                result[key] = self._read_protection(kind, name)
            except Exception:
                result[key] = None
        self.cached_protections = result

    def set_protection(self, key, enabled):
        """Attiva/disattiva una protezione; il valore iniziale viene ricordato per il ripristino."""
        spec = dict((p[0], p) for p in PROTECTIONS).get(key)
        if spec is None:
            return False, "protezione sconosciuta: %s" % key
        _, label, kind, name, editable = spec
        if not editable:
            return False, "%s: non modificabile dal pannello (protegge i motori)" % label
        if not self.motion:
            return False, "ALMotion non disponibile"
        enabled = bool(enabled)
        with self.lock:
            try:
                if key not in self._protection_originals:
                    try:
                        self._protection_originals[key] = self._read_protection(kind, name)
                    except Exception:
                        self._protection_originals[key] = True
                if kind == "external":
                    self.motion.setExternalCollisionProtectionEnabled(name, enabled)
                elif kind == "self":
                    self.motion.setCollisionProtectionEnabled(name, enabled)
                elif kind == "smart":
                    self.motion.setSmartStiffnessEnabled(enabled)
            except Exception as exc:
                return False, "%s: modifica non riuscita (%s)" % (label, str(exc))
        try:
            actual = self._read_protection(kind, name)
        except Exception:
            actual = None
        self.cached_protections[key] = actual
        if actual is not None and actual != enabled:
            return False, "%s: il robot non ha accettato la modifica (resta %s)" % (label, "attiva" if actual else "disattivata")
        self.log("[SICUREZZA] %s %s" % (label, "ATTIVATA" if enabled else "DISATTIVATA"))
        return True, "%s %s" % (label, "attivata" if enabled else "disattivata")

    def restore_protections(self):
        """Riporta le protezioni modificate dal pannello al valore che avevano prima."""
        if not self._protection_originals:
            return True, "Nessuna protezione da ripristinare"
        messages = []
        ok_all = True
        for key, original in list(self._protection_originals.items()):
            if original is None:
                original = True
            ok, message = self.set_protection(key, original)
            ok_all = ok_all and ok
            messages.append(message)
        if ok_all:
            self._protection_originals = {}
        return ok_all, "Protezioni ripristinate: " + "; ".join(messages)

    @staticmethod
    def _direction_label(x, y):
        angle = math.degrees(math.atan2(y, x))
        sectors = [(-22.5, 22.5, "davanti"), (22.5, 67.5, "davanti a sinistra"), (67.5, 112.5, "a sinistra"),
                   (112.5, 157.5, "dietro a sinistra"), (-67.5, -22.5, "davanti a destra"),
                   (-112.5, -67.5, "a destra"), (-157.5, -112.5, "dietro a destra")]
        for lo, hi, label in sectors:
            if lo <= angle < hi:
                return label
        return "dietro"

    def refresh_obstacles(self):
        """Ostacolo piu' vicino a ciascun braccio (FRAME_ROBOT), distanza dalla mano. Senza lock."""
        if not self.motion:
            return
        result = {}
        for chain in SAFETY_CHAINS:
            try:
                obstacle = [float(v) for v in self.motion.getChainClosestObstaclePosition(chain, 2)][:3]
            except Exception:
                result[chain] = None
                continue
            if len(obstacle) < 3 or all(abs(v) < 1e-6 for v in obstacle):
                result[chain] = {"distance": None}
                continue
            try:
                hand = [float(v) for v in self.motion.getPosition(chain, 2, True)][:3]
            except Exception:
                hand = [0.0, 0.0, obstacle[2]]
            dx, dy = obstacle[0] - hand[0], obstacle[1] - hand[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > OBSTACLE_MAX_DISTANCE:
                result[chain] = {"distance": None}
                continue
            result[chain] = {"distance": distance, "side": self._direction_label(obstacle[0], obstacle[1]),
                             "position": obstacle}
        self.cached_obstacles = result

    def simulate_obstacle(self, position):
        """Solo modalita' demo: ostacolo simulato (FRAME_ROBOT, metri) o None per toglierlo."""
        if not getattr(self.qi, "IS_FAKE", False) or not self.session:
            return False, "disponibile solo in modalita' demo"
        self.qi.simulate_obstacle(self.session, position)
        return True, ("Ostacolo simulato a (%.2f, %.2f) m" % (position[0], position[1])) if position else "Ostacolo simulato rimosso"

    def refresh_temperatures(self):
        """Legge le temperature dei motori da ALMemory (senza lock: non blocca i comandi)."""
        if not self.memory:
            return
        keys = ["Device/SubDeviceList/%s/Temperature/Sensor/Value" % j for j in TEMPERATURE_JOINTS]
        status_keys = ["Device/SubDeviceList/%s/Temperature/Sensor/Status" % j for j in TEMPERATURE_JOINTS]
        try:
            values = self.memory.getListData(keys)
        except Exception:
            return
        try:
            statuses = self.memory.getListData(status_keys)
        except Exception:
            statuses = [None] * len(keys)
        result = {}
        for joint, value, status in zip(TEMPERATURE_JOINTS, values, statuses):
            try:
                temperature = float(value)
            except Exception:
                continue
            try:
                status = int(status) if status is not None else None
            except Exception:
                status = None
            result[joint] = (temperature, status)
        self.cached_temperatures = result
        self._log_temperature_changes(result)

    @staticmethod
    def temperature_level(temperature, status):
        """0 = normale, 1 = calda, 2 = molto calda (stato NAOqi se presente, altrimenti soglie indicative)."""
        if status is not None:
            return 0 if status <= 0 else (1 if status == 1 else 2)
        if temperature >= TEMPERATURE_HOT:
            return 2
        if temperature >= TEMPERATURE_WARM:
            return 1
        return 0

    def hottest_joint(self):
        temps = self.cached_temperatures
        if not temps:
            return None
        joint = max(temps, key=lambda j: temps[j][0])
        return joint, temps[joint][0]

    def _log_temperature_changes(self, temps):
        for joint, (temperature, status) in temps.items():
            level = self.temperature_level(temperature, status)
            previous = self._temperature_levels.get(joint, 0)
            if level != previous:
                self._temperature_levels[joint] = level
                if level > previous:
                    label = "calda" if level == 1 else "MOLTO CALDA: la forza del motore viene ridotta"
                    self.log("[TEMPERATURA] %s %s (%.0f C). Consiglio: Rest e qualche minuto di pausa."
                             % (joint, label, temperature))
                else:
                    self.log("[TEMPERATURA] %s di nuovo nella norma (%.0f C)" % (joint, temperature))

    def _refresh_status_cache(self):
        self.cached_life_state = self.get_autonomous_life_state()
        if not self.audio_device:
            return
        # Il volume si legge solo se il robot non sta eseguendo un altro comando:
        # niente attese sul lock (era la causa del blocco della finestra).
        if self.lock.acquire(False):
            try:
                self._get_volume_locked()
            except Exception:
                pass
            finally:
                self.lock.release()

    def _mark_disconnected(self, reason, as_error=True):
        soft = self._soft
        if soft is not None:
            soft["stop"].set()
            self._soft = None
        was_connected = self.robot_connected
        self.robot_connected = False
        self.connection_state = "DISCONNESSO"
        self.cached_volume = None
        self.cached_life_state = "N/A"
        self.cached_temperatures = {}
        self.cached_obstacles = {}
        self.cached_protections = {}
        self._close_session()
        if was_connected and as_error:
            self.set_error("Connessione con il robot persa (%s). Riconnessione automatica attiva." % reason)

    def _try_reconnect(self):
        if not getattr(self.qi, "IS_FAKE", False) and not tcp_check(self.robot_ip, self.robot_port, timeout=2):
            self._reconnect_failures += 1
            self.connection_state = "DISCONNESSO - nuovo tentativo ogni %d s" % int(self.reconnect_interval)
            if self._reconnect_failures == 1 or self._reconnect_failures % 12 == 0:
                self.log("[ROBOT] Pepper non raggiungibile su %s:%d, riprovo..." % (self.robot_ip, self.robot_port))
            return False
        try:
            self.connect()
            self.log("[ROBOT] Riconnessione riuscita.")
            self.last_error = ""
            return True
        except Exception as exc:
            self._reconnect_failures += 1
            self.robot_connected = False
            self.connection_state = "DISCONNESSO - nuovo tentativo ogni %d s" % int(self.reconnect_interval)
            if self._reconnect_failures == 1 or self._reconnect_failures % 12 == 0:
                self.log("[ROBOT] Riconnessione fallita: %s" % str(exc))
            return False

    def configure_target(self, fake, ip, port):
        """
        Cambia robot di destinazione (demo/reale, IP, porta) e riconnette.
        Ritorna (ok, messaggio). Le impostazioni valgono fino al riavvio del
        controller: all'avvio successivo si torna ai valori del file .env.
        """
        fake = bool(fake)
        if fake:
            ok, ip, port, message = True, safe_unicode(ip).strip() or self.robot_ip, port, ""
            try:
                port = int(port)
            except Exception:
                port = self.robot_port
        else:
            ok, ip, port, message = validate_robot_address(ip, port)
        if not ok:
            return False, message
        try:
            new_qi = load_qi(fake)
        except Exception as exc:
            return False, "SDK NAOqi non disponibile (%s): impossibile usare il robot reale" % str(exc)

        self.log("[ROBOT] Nuova destinazione: %s (%s:%d)" % ("DEMO - robot simulato" if fake else "robot reale", ip, port))
        self._mark_disconnected("cambio robot", as_error=False)
        self.joint_limits = {}
        self.fake_robot = fake
        self.qi = new_qi
        self.robot_ip = ip
        self.robot_port = port
        self.config["robot"]["ip"] = ip
        self.config["robot"]["port"] = port
        self.request_reconnect(manual=False)
        return True, "Connessione a %s %s:%d in corso..." % ("robot simulato" if fake else "Pepper", ip, port)

    def request_reconnect(self, manual=True):
        """Forza una nuova connessione (pulsante 'Riconnetti ora' della GUI)."""
        if manual:
            self._reconnect_requested = True
        self._reconnect_failures = 0
        self._monitor_wake.set()

    def simulate_disconnect(self, seconds=15):
        """Solo modalita' demo: simula la perdita del robot per qualche secondo."""
        if not getattr(self.qi, "IS_FAKE", False):
            return False, "disponibile solo in modalita' demo"
        self.qi.simulate_offline(seconds)
        self._monitor_wake.set()
        return True, "Robot simulato offline per %d s" % seconds

    def monitor_loop(self):
        tick = 0
        while self.running:
            tick += 1
            if self._reconnect_requested:
                self._reconnect_requested = False
                self.log("[ROBOT] Riconnessione richiesta dall'utente...")
                self._mark_disconnected("riconnessione manuale", as_error=False)
                self._reconnect_failures = 0
            if self.robot_connected:
                if self._session_alive(check_tcp=(tick % 3 == 0)):
                    try:
                        self._refresh_status_cache()
                    except Exception:
                        pass
                    if tick % TEMPERATURE_PERIOD_TICKS == 1:
                        try:
                            self.refresh_temperatures()
                        except Exception:
                            pass
                    try:
                        self.refresh_obstacles()
                    except Exception:
                        pass
                    if tick % 5 == 2:
                        try:
                            self.refresh_protections()
                        except Exception:
                            pass
                    wait = 1.0
                else:
                    self.log("[ROBOT] Connessione con Pepper persa.")
                    self._mark_disconnected("sessione NAOqi chiusa")
                    wait = 1.0
            else:
                self._try_reconnect()
                wait = 1.0 if self.robot_connected else self.reconnect_interval
            self._monitor_wake.wait(wait)
            self._monitor_wake.clear()

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
            # Robot disconnesso: non preleva comandi dalla WebApp (andrebbero persi)
            if not self.robot_connected:
                time.sleep(1.0)
                continue
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