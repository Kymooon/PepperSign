# -*- coding: utf-8 -*-
"""
PepperController: unico punto d'accesso al robot per GUI, main.py e WebApp.

Il controller non contiene piu' la logica: crea i componenti di
peppersign/robot/ e delega a loro, mantenendo gli stessi metodi e attributi
pubblici di prima (la GUI e main.py non cambiano).

    robot       RobotSession: connessione, servizi NAOqi, lock, log, stato
    monitor     ConnectionMonitor: controllo della connessione e riconnessione
    limits      JointLimits: limiti dei giunti, clamp, validazione dei frame
    autonomy    AutonomyManager: Autonomous Life, pausa durante i gesti
    collision   ArmCollisionScheduler: anti-collisione spenta in parti del gesto
    safety      SafetyMonitor: temperature, ostacoli, protezioni, rallentamenti
    soft        SoftHold: braccia morbide
    player      GesturePlayer: esecuzione dei gesti
    recording   Recording: stiffness, mani, pose, preparazione della registrazione
    speech      Speech: voce, volume, registrazione audio
    webapp      WebAppBridge: polling dei comandi della WebApp

I nomi a livello di modulo (costanti e funzioni) restano importabili da qui.
"""
from __future__ import absolute_import

from peppersign.gesture_store import ARM_JOINTS, HEAD_JOINTS  # noqa: F401 (riesportati)
from peppersign.robot.autonomy import ARM_ABILITIES, GESTURE_AUTONOMY_MODES, AutonomyManager
from peppersign.robot.collision import (  # noqa: F401 (riesportati)
    ARM_COLLISION_CHAINS, ArmCollisionScheduler, normalize_collision_chain)
from peppersign.robot.interpolation import (  # noqa: F401 (riesportati)
    NO_ARM_COLLISION_KEY, InvalidGesture, arm_collision_windows, check_frames, check_gesture,
    frame_dt, summarize)
from peppersign.robot.joints import (  # noqa: F401 (riesportati)
    EXEC_LIMIT_MARGIN, HEAD_PITCH_CLAMP, LEFT_ARM_JOINTS, RIGHT_ARM_JOINTS, VELOCITY_WARN_FRACTION,
    JointLimits, head_pitch_limits, native_joint_names)
from peppersign.robot.player import GesturePlayer
from peppersign.robot.recording import (  # noqa: F401 (riesportati)
    SOFT_ARM_JOINTS, SOFT_DEFAULT_STIFFNESS, SOFT_FOLLOW_SPEED, SOFT_FOLLOW_THRESHOLD, SOFT_PERIOD,
    Recording, SoftHold)
from peppersign.robot.safety import (  # noqa: F401 (riesportati)
    OBSTACLE_MAX_DISTANCE, PROTECTIONS, SAFETY_CHAINS, TEMPERATURE_HOT, TEMPERATURE_JOINTS,
    TEMPERATURE_PERIOD_TICKS, TEMPERATURE_WARM, SafetyMonitor)
from peppersign.robot.session import (  # noqa: F401 (riesportati)
    SERVICE_ATTRS, ConnectionMonitor, RobotSession, load_qi, validate_robot_address)
from peppersign.robot.speech import Speech
from peppersign.robot.webapp import WebAppBridge
from peppersign.utils import safe_unicode


def _forward(component, name, doc=None, writable=True):
    """Proprieta' che legge (e scrive) l'attributo `name` del componente `component`."""
    def getter(self):
        return getattr(getattr(self, component), name)

    def setter(self, value):
        setattr(getattr(self, component), name, value)

    return property(getter, setter if writable else None, doc=doc)


class PepperController(object):
    GESTURE_AUTONOMY_MODES = GESTURE_AUTONOMY_MODES
    ARM_ABILITIES = ARM_ABILITIES

    def __init__(self, config, gesture_store=None, log_cb=None):
        self.config = config

        self.robot = RobotSession(config, log_cb=log_cb)
        self.limits = JointLimits(self.robot)
        self.autonomy = AutonomyManager(self.robot)
        self.collision = ArmCollisionScheduler(self.robot)
        self.safety = SafetyMonitor(self.robot)
        self.soft = SoftHold(self.robot)
        self.player = GesturePlayer(self.robot, self.limits, self.autonomy, self.collision,
                                    self.safety, self.soft, gesture_store=gesture_store)
        self.recording = Recording(self.robot, self.limits, self.autonomy, self.soft, self.player)
        self.speech = Speech(self.robot)
        self.webapp = WebAppBridge(self.robot, self)
        self.monitor = ConnectionMonitor(self.robot, {
            "connect": self.connect,
            "refresh_status": self._refresh_status_cache,
            "refresh_temperatures": self.safety.refresh_temperatures,
            "refresh_obstacles": self.safety.refresh_obstacles,
            "refresh_protections": self.safety.refresh_protections,
            "on_disconnect": self._on_disconnect,
        })

    # ------------------------------------------------------------------
    # Stato pubblico (letto dalla GUI e da main.py)
    # ------------------------------------------------------------------
    log_cb = _forward("robot", "log_cb")
    robot_ip = _forward("robot", "robot_ip")
    robot_port = _forward("robot", "robot_port")
    fake_robot = _forward("robot", "fake_robot")
    qi = _forward("robot", "qi")
    session = _forward("robot", "session")
    lock = _forward("robot", "lock", writable=False)
    running = _forward("robot", "running")
    robot_connected = _forward("robot", "robot_connected")
    connection_state = _forward("robot", "connection_state")
    last_error = _forward("robot", "last_error")
    reconnect_interval = _forward("monitor", "reconnect_interval")
    joint_limits = _forward("limits", "limits")
    joint_velocity = _forward("limits", "velocity")
    cached_life_state = _forward("autonomy", "cached_life_state")
    cached_volume = _forward("speech", "cached_volume")
    cached_temperatures = _forward("safety", "cached_temperatures")
    cached_obstacles = _forward("safety", "cached_obstacles")
    cached_protections = _forward("safety", "cached_protections")
    safety_events = _forward("safety", "safety_events")
    gesture_store = _forward("player", "gesture_store")
    connected_to_webapp = _forward("webapp", "connected_to_webapp")
    last_cmd = _forward("webapp", "last_cmd")
    command_handlers = _forward("webapp", "command_handlers")

    def log(self, message):
        self.robot.log(message)

    def set_error(self, message):
        self.robot.set_error(message)

    # ------------------------------------------------------------------
    # Connessione
    # ------------------------------------------------------------------
    def connect(self):
        with self.robot.connection_lock:
            self._connect_locked()

    def _connect_locked(self):
        robot = self.robot
        robot.log("[1] Connessione QI...")
        robot.connection_state = "CONNESSIONE..."
        robot.open()
        self.safety.subscribe_events()

        defaults = self.config["robot_defaults"]
        with robot.lock:
            if defaults.get("connect_wakeup", True):
                try:
                    robot.motion.wakeUp()
                except Exception as exc:
                    robot.log("[WARN] wakeUp fallita in connect: %s" % str(exc))

            if defaults.get("stop_basic_awareness_on_connect", True):
                try:
                    if robot.basic_awareness.isRunning():
                        robot.basic_awareness.stopAwareness()
                except Exception as exc:
                    robot.log("[WARN] stopAwareness fallita: %s" % str(exc))

            try:
                robot.tts.setLanguage(defaults.get("tts_language", "Italian"))
            except Exception as exc:
                robot.log("[WARN] setLanguage fallita: %s" % str(exc))

            self.speech.apply_speaking_movement_defaults_locked()

            # Gesto interrotto da una disconnessione: riattivo cio' che non e' stato ripristinato
            self.collision.apply_pending_locked()
            self.autonomy.apply_pending_locked()

        if robot.animated_speech:
            robot.log("[OK] ALAnimatedSpeech disponibile")
        else:
            robot.log("[WARN] ALAnimatedSpeech non disponibile: ANIMATED_SAY usera il TTS classico")

        if robot.audio_device:
            ok, current_volume = self.speech.get_volume()
            if ok:
                robot.log("[OK] Volume iniziale: %d%%" % current_volume)
        else:
            robot.log("[WARN] ALAudioDevice non disponibile: controlli volume disabilitati")

        self.autonomy.refresh_cache()
        robot.robot_connected = True
        robot.connection_state = "CONNESSO"
        self.monitor.reconnect_failures = 0
        robot.log("[OK] Pepper connesso. Autonomous Life: %s" % self.autonomy.cached_life_state)
        robot.log("[INFO] Autonomia durante i gesti: %s" % self.autonomy.gesture_mode())

    def _refresh_status_cache(self):
        self.autonomy.refresh_cache()
        self.speech.refresh_volume_cache()

    def _on_disconnect(self):
        self.soft.cancel()
        self.speech.cached_volume = None
        self.autonomy.cached_life_state = "N/A"
        self.safety.clear_cache()

    def configure_target(self, fake, ip, port):
        """
        Cambia robot di destinazione (demo/reale, IP, porta) e riconnette.
        Ritorna (ok, messaggio). Le impostazioni valgono fino al riavvio del
        controller: all'avvio successivo si torna ai valori del file .env.
        """
        with self.robot.connection_lock:
            return self._configure_target_locked(fake, ip, port)

    def _configure_target_locked(self, fake, ip, port):
        robot = self.robot
        fake = bool(fake)
        if fake:
            ok, ip, port, message = True, safe_unicode(ip).strip() or robot.robot_ip, port, ""
            try:
                port = int(port)
            except Exception:
                port = robot.robot_port
        else:
            ok, ip, port, message = validate_robot_address(ip, port)
        if not ok:
            return False, message
        try:
            new_qi = load_qi(fake)
        except Exception as exc:
            return False, "SDK NAOqi non disponibile (%s): impossibile usare il robot reale" % str(exc)

        robot.log("[ROBOT] Nuova destinazione: %s (%s:%d)" % ("DEMO - robot simulato" if fake else "robot reale", ip, port))
        self.monitor.mark_disconnected("cambio robot", as_error=False)
        self.limits.reset()
        robot.set_target(fake, new_qi, ip, port)
        self.monitor.request_reconnect(manual=False)
        return True, "Connessione a %s %s:%d in corso..." % ("robot simulato" if fake else "Pepper", ip, port)

    def request_reconnect(self, manual=True):
        """Forza una nuova connessione (pulsante 'Riconnetti ora' della GUI)."""
        self.monitor.request_reconnect(manual)

    def simulate_disconnect(self, seconds=15):
        """Solo modalita' demo: simula la perdita del robot per qualche secondo."""
        if not self.robot.is_fake:
            return False, "disponibile solo in modalita' demo"
        self.robot.qi.simulate_offline(seconds)
        self.monitor.wake()
        return True, "Robot simulato offline per %d s" % seconds

    def monitor_loop(self):
        self.monitor.loop()

    # ------------------------------------------------------------------
    # WebApp
    # ------------------------------------------------------------------
    def handle_command(self, cmd):
        """Esegue un comando della WebApp; ritorna (ok, messaggio) o None per NONE."""
        return self.webapp.handle_command(cmd)

    def poll_webapp_loop(self):
        self.webapp.poll_loop()

    # ------------------------------------------------------------------
    # Voce e volume
    # ------------------------------------------------------------------
    def say(self, text):
        return self.speech.say(text)

    def say_animated(self, text):
        return self.speech.say_animated(text)

    def say_and_listen(self, session_id, prompt):
        return self.speech.say_and_listen(session_id, prompt)

    def get_volume(self):
        return self.speech.get_volume()

    def set_volume(self, value):
        return self.speech.set_volume(value)

    def volume_up(self, step=None):
        return self.speech.volume_up(step)

    def volume_down(self, step=None):
        return self.speech.volume_down(step)

    # ------------------------------------------------------------------
    # Autonomous Life
    # ------------------------------------------------------------------
    def get_autonomous_life_state(self):
        return self.autonomy.get_state()

    def set_autonomous_life(self, enabled):
        return self.autonomy.set_life(enabled)

    def disable_autonomous_stack(self):
        return self.autonomy.disable_stack()

    # ------------------------------------------------------------------
    # Postura, stiffness, mani, pose (registrazione)
    # ------------------------------------------------------------------
    def wakeup(self):
        return self.recording.wakeup()

    def rest(self):
        return self.recording.rest()

    def set_stiffness(self, joints, value):
        return self.recording.set_stiffness(joints, value)

    def free_arms(self):
        return self.recording.free_arms()

    def hold_arms(self):
        return self.recording.hold_arms()

    def free_left_arm(self):
        return self.recording.free_left_arm()

    def hold_left_arm(self):
        return self.recording.hold_left_arm()

    def free_right_arm(self):
        return self.recording.free_right_arm()

    def hold_right_arm(self):
        return self.recording.hold_right_arm()

    def move_only_left_arm(self):
        return self.recording.move_only_left_arm()

    def move_only_right_arm(self):
        return self.recording.move_only_right_arm()

    def free_head(self):
        return self.recording.free_head()

    def hold_head(self):
        return self.recording.hold_head()

    def set_hand(self, hand_name, is_open):
        return self.recording.set_hand(hand_name, is_open)

    def open_hand(self, hand_name):
        return self.recording.open_hand(hand_name)

    def close_hand(self, hand_name):
        return self.recording.close_hand(hand_name)

    def open_both_hands(self):
        return self.recording.open_both_hands()

    def close_both_hands(self):
        return self.recording.close_both_hands()

    def get_pose(self, joints):
        return self.recording.get_pose(joints)

    def go_to_pose(self, joints, angles, min_duration=1.0, max_velocity=0.8):
        return self.recording.go_to_pose(joints, angles, min_duration, max_velocity)

    def center_head_forward(self, duration=0.8):
        return self.recording.center_head_forward(duration)

    def prepare_gesture_recording(self):
        return self.recording.prepare_gesture_recording()

    def soft_hold_state(self):
        return self.soft.state()

    def start_soft_hold(self, group="both", stiffness=SOFT_DEFAULT_STIFFNESS, threshold=SOFT_FOLLOW_THRESHOLD):
        return self.soft.start(group, stiffness, threshold)

    def stop_soft_hold(self, final_stiffness=1.0):
        return self.soft.stop(final_stiffness)

    # ------------------------------------------------------------------
    # Limiti e validazione
    # ------------------------------------------------------------------
    def validate_frame_pose(self, joints, angles, limit_tolerance=0.03, near_limit_margin=0.05):
        return self.limits.validate_frame_pose(joints, angles, limit_tolerance, near_limit_margin)

    head_pitch_limits = staticmethod(head_pitch_limits)

    def clamp_angles_to_limits(self, joints, angles, margin=EXEC_LIMIT_MARGIN):
        return self.limits.clamp_angles(joints, angles, margin)

    def build_interpolation_from_frames(self, joints, frames):
        return self.player.build_interpolation_from_frames(joints, frames)

    # ------------------------------------------------------------------
    # Esecuzione dei gesti
    # ------------------------------------------------------------------
    def run_frames_gesture(self, joints, frames, collision_chain=None):
        return self.player.run_frames_gesture(joints, frames, collision_chain=collision_chain)

    def play_gesture(self, gesture_id):
        return self.player.play_gesture(gesture_id)

    # ------------------------------------------------------------------
    # Sicurezza e motori
    # ------------------------------------------------------------------
    def safety_counts(self):
        return self.safety.safety_counts()

    def reset_safety_counts(self):
        self.safety.reset_safety_counts()

    def refresh_protections(self):
        self.safety.refresh_protections()

    def set_protection(self, key, enabled):
        return self.safety.set_protection(key, enabled)

    def restore_protections(self):
        return self.safety.restore_protections()

    def refresh_obstacles(self):
        self.safety.refresh_obstacles()

    def simulate_obstacle(self, position):
        return self.safety.simulate_obstacle(position)

    def refresh_temperatures(self):
        self.safety.refresh_temperatures()

    temperature_level = staticmethod(SafetyMonitor.temperature_level)

    def hottest_joint(self):
        return self.safety.hottest_joint()


# Servizi NAOqi (tts, motion, memory, ...) leggibili come prima: controller.motion
for _attr in SERVICE_ATTRS:
    setattr(PepperController, _attr, _forward("robot", _attr, writable=False))
del _attr
