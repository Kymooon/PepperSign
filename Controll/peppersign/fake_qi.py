# -*- coding: utf-8 -*-
"""
Robot Pepper simulato per la modalita' demo (PEPPERSIGN_FAKE_ROBOT=1).

Sostituisce il modulo "qi" dell'SDK NAOqi con oggetti finti che espongono gli
stessi metodi usati da PepperController. Non serve ne' il robot ne' l'SDK:
in questo modo si possono provare GUI, registrazione/test dei gesti e il
flusso tablet -> WebApp -> controller anche senza Pepper.

Cosa fa il robot simulato:
  - registra in log ogni comando ricevuto ([DEMO] ...);
  - mantiene in memoria la posa corrente dei giunti (getAngles la restituisce,
    angleInterpolation la aggiorna), con i limiti reali dei giunti di Pepper;
  - simula i tempi delle azioni bloccanti (parlato, movimenti), con un tetto
    massimo, cosi' il comportamento in GUI e' realistico;
  - per la registrazione audio restituisce un WAV di silenzio.
"""
from __future__ import absolute_import

import io
import struct
import threading
import time
import wave

IS_FAKE = True

# Simulazione della perdita di connessione (pulsante "Simula disconnessione"
# della GUI in modalita' demo): fino a questo istante il robot e' "spento".
_OFFLINE_UNTIL = [0.0]


def simulate_offline(seconds):
    _OFFLINE_UNTIL[0] = time.time() + float(seconds)


def _is_offline():
    return time.time() < _OFFLINE_UNTIL[0]

# Limiti dei giunti di Pepper (radianti) secondo la documentazione Aldebaran.
# Formato getLimits: [[min, max, velocita' max, coppia max]]
PEPPER_JOINT_LIMITS = {
    "HeadYaw": (-2.0857, 2.0857),
    "HeadPitch": (-0.7068, 0.4451),   # documentazione NAOqi 2.5 (con HeadYaw ~0; si riduce ruotando la testa)
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
    "HipRoll": (-0.5149, 0.5149),
    "HipPitch": (-1.0385, 1.0385),
    "KneePitch": (-0.5149, 0.5149),
}

# Velocita' massime (rad/s) dall'URDF ufficiale (pepper_description)
PEPPER_MAX_VELOCITY = {
    "HeadYaw": 7.34, "HeadPitch": 9.23,
    "LShoulderPitch": 7.34, "LShoulderRoll": 9.23, "LElbowYaw": 7.34, "LElbowRoll": 9.23,
    "LWristYaw": 17.38, "LHand": 12.56,
    "RShoulderPitch": 7.34, "RShoulderRoll": 9.23, "RElbowYaw": 7.34, "RElbowRoll": 9.23,
    "RWristYaw": 17.38, "RHand": 12.56,
}

# Posa iniziale simile alla "StandInit" di Pepper.
INITIAL_POSE = {
    "HeadYaw": 0.0, "HeadPitch": -0.2,
    "LShoulderPitch": 1.5, "LShoulderRoll": 0.15, "LElbowYaw": -1.2,
    "LElbowRoll": -0.5, "LWristYaw": 0.0, "LHand": 0.6,
    "RShoulderPitch": 1.5, "RShoulderRoll": -0.15, "RElbowYaw": 1.2,
    "RElbowRoll": 0.5, "RWristYaw": 0.0, "RHand": 0.6,
    "HipRoll": 0.0, "HipPitch": 0.0, "KneePitch": 0.0,
}

CHAIN_JOINTS = {
    "Head": ["HeadYaw", "HeadPitch"],
    "LArm": ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand"],
    "RArm": ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand"],
    "Leg": ["HipRoll", "HipPitch", "KneePitch"],
}
CHAIN_JOINTS["Body"] = CHAIN_JOINTS["Head"] + CHAIN_JOINTS["LArm"] + CHAIN_JOINTS["RArm"] + CHAIN_JOINTS["Leg"]

# Durata massima simulata di una singola azione bloccante (secondi).
MAX_SIMULATED_SECONDS = 8.0


def _short(value, limit=80):
    try:
        text = value if isinstance(value, str) else repr(value)
    except Exception:
        text = "?"
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _sleep(seconds):
    try:
        seconds = float(seconds)
    except Exception:
        return
    if seconds > 0:
        time.sleep(min(seconds, MAX_SIMULATED_SECONDS))


def _silent_wav_bytes(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    writer = wave.open(buf, "wb")
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(rate)
    writer.writeframes(struct.pack("<h", 0) * int(seconds * rate))
    writer.close()
    return buf.getvalue()


class _RobotState(object):
    """Stato condiviso tra i servizi simulati."""

    def __init__(self):
        self.lock = threading.Lock()
        self.angles = dict(INITIAL_POSE)
        self.stiffness = dict((name, 0.0) for name in INITIAL_POSE)
        self.volume = 60
        self.life_state = "solitary"
        self.awareness_running = True
        self.recorded_files = set()
        self.logger = None
        # Autonomous abilities e movimenti autonomi (come con Autonomous Life attiva)
        self.abilities = {
            "AutonomousBlinking": True,
            "BackgroundMovement": True,
            "BasicAwareness": True,
            "ListeningMovement": True,
            "SpeakingMovement": True,
        }
        self.breath = {"Body": True, "Arms": True, "Head": True, "Legs": True}
        self.idle_posture = {"Body": True, "Arms": True, "Head": True, "Legs": True}
        self.tracking_mode = "BodyRotation"
        # Protezioni di ALMotion (tutte attive come sul robot) e ostacolo simulato
        self.protections = {"external:LArm": True, "external:RArm": True, "external:Arms": True,
                            "self:Arms": True, "smart": True, "diagnosis": True}
        self.obstacle = None          # [x, y, z] in FRAME_ROBOT oppure None
        self.subscribers = {}         # evento ALMemory -> lista di callback

    def fire(self, event, value):
        for callback in list(self.subscribers.get(event, [])):
            try:
                callback(value)
            except Exception:
                pass

    def log(self, message):
        line = "[DEMO] %s" % message
        if self.logger:
            try:
                self.logger(line)
                return
            except Exception:
                pass
        print(line)


def _joint_list(names):
    if isinstance(names, (list, tuple)):
        out = []
        for name in names:
            out.extend(_joint_list(name))
        return out
    name = str(names)
    if name in CHAIN_JOINTS:
        return list(CHAIN_JOINTS[name])
    return [name]


class FakeService(object):
    """Servizio generico: ogni metodo non definito viene accettato e registrato."""

    def __init__(self, name, state):
        self._name = name
        self._state = state

    def _log(self, method, *args):
        shown = ", ".join(_short(a, 60) for a in args)
        self._state.log("%s.%s(%s)" % (self._name, method, shown))

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)

        def _noop(*args, **kwargs):
            self._log(method, *args)
            return None
        return _noop


def _chain_get(table, chain):
    chain = str(chain)
    if chain == "Body":
        return all(table.values())
    return table.get(chain, table.get("Body", True))


def _chain_set(table, chain, value):
    chain = str(chain)
    if chain == "Body":
        for key in table:
            table[key] = bool(value)
    else:
        table[chain] = bool(value)
        table["Body"] = all(v for k, v in table.items() if k != "Body")


class FakeAbilityService(FakeService):
    """Servizi con setEnabled/isEnabled (BackgroundMovement, ListeningMovement, ...)."""

    ABILITY = None

    def isEnabled(self):
        return self._state.abilities.get(self.ABILITY, True)

    def setEnabled(self, enabled):
        self._log("setEnabled", enabled)
        self._state.abilities[self.ABILITY] = bool(enabled)


class FakeBackgroundMovement(FakeAbilityService):
    ABILITY = "BackgroundMovement"


class FakeListeningMovement(FakeAbilityService):
    ABILITY = "ListeningMovement"


class FakeSpeakingMovement(FakeAbilityService):
    ABILITY = "SpeakingMovement"

    def setMode(self, mode):
        self._log("setMode", mode)


class FakeAutonomousBlinking(FakeAbilityService):
    ABILITY = "AutonomousBlinking"


class FakeTextToSpeech(FakeService):
    def say(self, text, *args):
        self._log("say", text)
        # circa 12 caratteri al secondo, come una voce sintetica
        _sleep(0.5 + len(text or "") / 12.0)

    def setLanguage(self, language):
        self._log("setLanguage", language)

    def getLanguage(self):
        return "Italian"


class FakeAnimatedSpeech(FakeTextToSpeech):
    pass


class FakeAudioDevice(FakeService):
    def getOutputVolume(self):
        return self._state.volume

    def setOutputVolume(self, value):
        self._state.volume = int(value)
        self._log("setOutputVolume", value)


class FakeAudioRecorder(FakeService):
    def startMicrophonesRecording(self, path, *args):
        self._log("startMicrophonesRecording", path)
        self._state.recorded_files.add(path)

    def stopMicrophonesRecording(self, *args):
        self._log("stopMicrophonesRecording")


class FakeFileManager(FakeService):
    def fileExists(self, path):
        return path in self._state.recorded_files

    def getFileContents(self, path):
        self._log("getFileContents", path)
        return _silent_wav_bytes(1.0)


class FakeMotion(FakeService):
    def wakeUp(self):
        self._log("wakeUp")
        with self._state.lock:
            for name in self._state.stiffness:
                self._state.stiffness[name] = 1.0
        _sleep(1.0)

    def rest(self):
        self._log("rest")
        with self._state.lock:
            for name in self._state.stiffness:
                self._state.stiffness[name] = 0.0
        _sleep(1.0)

    def setStiffnesses(self, names, value):
        joints = _joint_list(names)
        self._log("setStiffnesses", "%d giunti" % len(joints), value)
        with self._state.lock:
            for name in joints:
                self._state.stiffness[name] = float(value)

    def setAngles(self, names, angles, speed):
        joints = _joint_list(names)
        if not isinstance(angles, (list, tuple)):
            angles = [angles] * len(joints)
        with self._state.lock:
            for name, value in zip(joints, angles):
                self._state.angles[name] = float(value)

    def getAngles(self, names, use_sensors=True):
        joints = _joint_list(names)
        with self._state.lock:
            return [float(self._state.angles.get(name, 0.0)) for name in joints]

    def getLimits(self, name):
        limits = PEPPER_JOINT_LIMITS.get(str(name))
        if not limits:
            raise RuntimeError("Giunto sconosciuto: %s" % name)
        return [[limits[0], limits[1], PEPPER_MAX_VELOCITY.get(str(name), 7.34), 1.0]]

    def angleInterpolation(self, names, angle_lists, time_lists, is_absolute=True):
        joints = _joint_list(names)
        if not isinstance(angle_lists, (list, tuple)):
            angle_lists = [angle_lists]
        if not isinstance(time_lists, (list, tuple)):
            time_lists = [time_lists]

        duration = 0.0
        finals = {}
        for index, name in enumerate(joints):
            angles = angle_lists[index] if index < len(angle_lists) else angle_lists[-1]
            times = time_lists[index] if index < len(time_lists) else time_lists[-1]
            final_angle = angles[-1] if isinstance(angles, (list, tuple)) else angles
            final_time = times[-1] if isinstance(times, (list, tuple)) else times
            finals[name] = float(final_angle)
            duration = max(duration, float(final_time))

        keyframes = 1
        if angle_lists and isinstance(angle_lists[0], (list, tuple)):
            keyframes = len(angle_lists[0])
        self._log("angleInterpolation", "%d giunti" % len(joints),
                  "%d keyframe" % keyframes, "%.2fs" % duration)

        with self._state.lock:
            for name, value in finals.items():
                if is_absolute:
                    self._state.angles[name] = value
                else:
                    self._state.angles[name] = self._state.angles.get(name, 0.0) + value
        # ostacolo simulato: il braccio che si muove viene "rallentato" come sul robot
        obstacle = self._state.obstacle
        if obstacle is not None:
            for chain in ("LArm", "RArm"):
                if any(j in joints for j in CHAIN_JOINTS[chain]) and self._state.protections.get("external:" + chain, True):
                    self._state.fire("ALMotion/Safety/ChainVelocityClipped", [[chain, list(obstacle)]])
                    duration *= 1.5
        _sleep(duration)

    # --- protezioni (stessi metodi di ALMotion) ---
    def getExternalCollisionProtectionEnabled(self, name):
        return self._state.protections.get("external:%s" % name, True)

    def setExternalCollisionProtectionEnabled(self, name, enable):
        self._log("setExternalCollisionProtectionEnabled", name, enable)
        names = ["LArm", "RArm", "Arms"] if name == "Arms" else [name]
        for n in names:
            self._state.protections["external:%s" % n] = bool(enable)

    def getCollisionProtectionEnabled(self, name):
        return self._state.protections.get("self:%s" % name, True)

    def setCollisionProtectionEnabled(self, name, enable):
        self._log("setCollisionProtectionEnabled", name, enable)
        self._state.protections["self:%s" % name] = bool(enable)
        return True

    def getSmartStiffnessEnabled(self):
        return self._state.protections["smart"]

    def setSmartStiffnessEnabled(self, enable):
        self._log("setSmartStiffnessEnabled", enable)
        self._state.protections["smart"] = bool(enable)

    def getDiagnosisEffectEnabled(self):
        return self._state.protections["diagnosis"]

    def getChainClosestObstaclePosition(self, chain, frame):
        obstacle = self._state.obstacle
        return list(obstacle) if obstacle is not None else [0.0, 0.0, 0.0]

    def getPosition(self, name, frame, use_sensors):
        # posizione indicativa della mano nel sistema del robot
        side = 1.0 if str(name).startswith("L") else -1.0
        return [0.15, side * 0.15, 0.85, 0.0, 0.0, 0.0]

    def openHand(self, hand):
        self._log("openHand", hand)
        with self._state.lock:
            self._state.angles[str(hand)] = 1.0

    def closeHand(self, hand):
        self._log("closeHand", hand)
        with self._state.lock:
            self._state.angles[str(hand)] = 0.0

    def getBreathEnabled(self, chain):
        return _chain_get(self._state.breath, chain)

    def setBreathEnabled(self, chain, enabled):
        self._log("setBreathEnabled", chain, enabled)
        _chain_set(self._state.breath, chain, enabled)

    def getIdlePostureEnabled(self, chain):
        return _chain_get(self._state.idle_posture, chain)

    def setIdlePostureEnabled(self, chain, enabled):
        self._log("setIdlePostureEnabled", chain, enabled)
        _chain_set(self._state.idle_posture, chain, enabled)


class FakeBasicAwareness(FakeService):
    def isRunning(self):
        return self._state.abilities.get("BasicAwareness", True)

    def isEnabled(self):
        return self._state.abilities.get("BasicAwareness", True)

    def setEnabled(self, enabled):
        self._log("setEnabled", enabled)
        self._state.abilities["BasicAwareness"] = bool(enabled)

    def getTrackingMode(self):
        return self._state.tracking_mode

    def setTrackingMode(self, mode):
        self._log("setTrackingMode", mode)
        self._state.tracking_mode = str(mode)

    def stopAwareness(self):
        self._log("stopAwareness")
        self._state.abilities["BasicAwareness"] = False

    def startAwareness(self):
        self._log("startAwareness")
        self._state.abilities["BasicAwareness"] = True


class FakeAutonomousLife(FakeService):
    def getState(self):
        return self._state.life_state

    def setState(self, state):
        self._log("setState", state)
        self._state.life_state = str(state)

    def getAutonomousAbilityEnabled(self, ability):
        if ability not in self._state.abilities:
            raise RuntimeError("Ability sconosciuta: %s" % ability)
        return self._state.abilities[ability]

    def setAutonomousAbilityEnabled(self, ability, enabled):
        if ability not in self._state.abilities:
            raise RuntimeError("Ability sconosciuta: %s" % ability)
        self._log("setAutonomousAbilityEnabled", ability, enabled)
        self._state.abilities[ability] = bool(enabled)


class FakeBehaviorManager(FakeService):
    def isBehaviorInstalled(self, name):
        return False


class FakeAnimationPlayer(FakeService):
    def run(self, name, *args):
        self._log("run", name)
        _sleep(2.0)


class FakeMemory(FakeService):
    """Solo le temperature dei motori: salgono lentamente con la stiffness, scendono a riposo."""

    def __init__(self, name, state):
        FakeService.__init__(self, name, state)
        self._temps = {}
        self._last = time.time()

    def _update(self):
        now = time.time()
        dt = min(now - self._last, 60.0)
        self._last = now
        alpha = 1.0 - pow(2.718281828, -dt / 120.0)      # costante di tempo ~2 minuti
        with self._state.lock:
            for joint, stiffness in self._state.stiffness.items():
                current = self._temps.get(joint, 35.0)
                target = 35.0 + 30.0 * float(stiffness)
                self._temps[joint] = current + (target - current) * alpha

    def getListData(self, keys):
        self._update()
        out = []
        for key in keys:
            parts = str(key).split("/")
            joint = parts[2] if len(parts) > 2 else ""
            temperature = self._temps.get(joint)
            if temperature is None:
                out.append(None)
            elif key.endswith("/Status"):
                out.append(0 if temperature < 60 else (1 if temperature < 70 else 2))
            else:
                out.append(round(temperature, 1))
        return out

    def getData(self, key):
        return self.getListData([key])[0]

    def subscriber(self, event):
        state = self._state

        class _Signal(object):
            def connect(self, callback):
                state.subscribers.setdefault(event, []).append(callback)
                return len(state.subscribers[event])

        class _Subscriber(object):
            signal = _Signal()
        return _Subscriber()


def simulate_obstacle(session, position):
    """Solo demo: imposta (o toglie, con None) un ostacolo vicino al robot simulato."""
    session._state.obstacle = list(position) if position is not None else None


SERVICE_CLASSES = {
    "ALTextToSpeech": FakeTextToSpeech,
    "ALAnimatedSpeech": FakeAnimatedSpeech,
    "ALAudioDevice": FakeAudioDevice,
    "ALAudioRecorder": FakeAudioRecorder,
    "ALFileManager": FakeFileManager,
    "ALMotion": FakeMotion,
    "ALMemory": FakeMemory,
    "ALBasicAwareness": FakeBasicAwareness,
    "ALAutonomousLife": FakeAutonomousLife,
    "ALBehaviorManager": FakeBehaviorManager,
    "ALAnimationPlayer": FakeAnimationPlayer,
    "ALBackgroundMovement": FakeBackgroundMovement,
    "ALListeningMovement": FakeListeningMovement,
    "ALSpeakingMovement": FakeSpeakingMovement,
    "ALAutonomousBlinking": FakeAutonomousBlinking,
}


class Session(object):
    """Sostituto di qi.Session: stessi metodi usati da PepperController."""

    def __init__(self):
        self._state = _RobotState()
        self._services = {}
        self._url = None

    def set_logger(self, logger):
        self._state.logger = logger

    def connect(self, url):
        if _is_offline():
            raise RuntimeError("Robot simulato non raggiungibile (disconnessione simulata)")
        self._url = url
        self._state.log("Robot simulato connesso (richiesto %s)" % url)

    def isConnected(self):
        if _is_offline():
            self._url = None
        return self._url is not None

    def close(self):
        self._url = None

    def service(self, name):
        if name not in self._services:
            cls = SERVICE_CLASSES.get(name, FakeService)
            self._services[name] = cls(name, self._state)
        return self._services[name]
