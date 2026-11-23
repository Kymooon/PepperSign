# -*- coding: utf-8 -*-
"""
Sicurezza: protezioni di ALMotion, ostacoli vicini alle braccia, rallentamenti
delle braccia (evento ALMotion/Safety/ChainVelocityClipped) e temperature dei motori.

I metodi refresh_* leggono il robot senza il lock della sessione (non bloccano
i comandi) e aggiornano valori in cache che la GUI mostra.
"""
from __future__ import absolute_import

import math
import threading
import time

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
    ("smart_stiffness", "Rigidità adattiva (riduce la forza a riposo)", "smart", None, True),
    ("diagnosis", "Riduzione della forza per temperatura/errori", "diagnosis", None, False),
]
SAFETY_CHAINS = ("LArm", "RArm")
OBSTACLE_MAX_DISTANCE = 3.0      # m: oltre, l'ostacolo non viene mostrato


class SafetyMonitor(object):
    def __init__(self, robot):
        self.robot = robot
        self.cached_temperatures = {}    # giunto -> (gradi C, stato NAOqi o None)
        self._temperature_levels = {}    # giunto -> livello gia' segnalato nel log
        self.cached_protections = {}     # chiave -> True/False/None (None = non disponibile)
        self._protection_originals = {}  # chiave -> valore prima delle modifiche dalla GUI
        self.cached_obstacles = {}       # catena -> dict(distance, side, position) oppure None
        self.safety_events = dict((c, {"count": 0, "last": 0.0}) for c in SAFETY_CHAINS)
        self._safety_lock = threading.Lock()
        self._clip_subscriber = None

    def clear_cache(self):
        """Valori in cache azzerati quando il robot si disconnette."""
        self.cached_temperatures = {}
        self.cached_obstacles = {}
        self.cached_protections = {}

    # ------------------------------------------------------------ rallentamenti
    def subscribe_events(self):
        self._clip_subscriber = None
        memory = self.robot.memory
        if not memory:
            return
        try:
            subscriber = memory.subscriber("ALMotion/Safety/ChainVelocityClipped")
            subscriber.signal.connect(self._on_chain_velocity_clipped)
            self._clip_subscriber = subscriber      # va tenuto in vita
        except Exception as exc:
            self.robot.log("[SICUREZZA] Evento dei rallentamenti non disponibile: %s" % str(exc))

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

    # ------------------------------------------------------------ protezioni
    def _read_protection(self, kind, name):
        motion = self.robot.motion
        if kind == "external":
            return bool(motion.getExternalCollisionProtectionEnabled(name))
        if kind == "self":
            return bool(motion.getCollisionProtectionEnabled(name))
        if kind == "smart":
            return bool(motion.getSmartStiffnessEnabled())
        if kind == "diagnosis":
            return bool(motion.getDiagnosisEffectEnabled())
        return None

    def refresh_protections(self):
        """Legge lo stato delle protezioni (senza lock). None = non disponibile su questo robot."""
        if not self.robot.motion:
            return
        generation = self.robot.generation
        result = {}
        for key, _, kind, name, _ in PROTECTIONS:
            try:
                result[key] = self._read_protection(kind, name)
            except Exception:
                result[key] = None
        if self.robot.generation == generation:      # niente valori di una sessione gia' chiusa
            self.cached_protections = result

    def set_protection(self, key, enabled):
        """Attiva/disattiva una protezione; il valore iniziale viene ricordato per il ripristino."""
        robot = self.robot
        spec = dict((p[0], p) for p in PROTECTIONS).get(key)
        if spec is None:
            return False, "protezione sconosciuta: %s" % key
        _, label, kind, name, editable = spec
        if not editable:
            return False, "%s: non modificabile dal pannello (protegge i motori)" % label
        if not robot.motion:
            return False, "ALMotion non disponibile"
        enabled = bool(enabled)
        with robot.lock:
            try:
                if key not in self._protection_originals:
                    try:
                        self._protection_originals[key] = self._read_protection(kind, name)
                    except Exception:
                        self._protection_originals[key] = True
                if kind == "external":
                    robot.motion.setExternalCollisionProtectionEnabled(name, enabled)
                elif kind == "self":
                    robot.motion.setCollisionProtectionEnabled(name, enabled)
                elif kind == "smart":
                    robot.motion.setSmartStiffnessEnabled(enabled)
            except Exception as exc:
                return False, "%s: modifica non riuscita (%s)" % (label, str(exc))
        try:
            actual = self._read_protection(kind, name)
        except Exception:
            actual = None
        self.cached_protections[key] = actual
        if actual is not None and actual != enabled:
            return False, "%s: il robot non ha accettato la modifica (resta %s)" % (label, "attiva" if actual else "disattivata")
        robot.log("[SICUREZZA] %s %s" % (label, "ATTIVATA" if enabled else "DISATTIVATA"))
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

    # ------------------------------------------------------------ ostacoli
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
        generation = self.robot.generation
        motion = self.robot.motion
        if not motion:
            return
        result = {}
        for chain in SAFETY_CHAINS:
            try:
                obstacle = [float(v) for v in motion.getChainClosestObstaclePosition(chain, 2)][:3]
            except Exception:
                result[chain] = None
                continue
            if len(obstacle) < 3 or all(abs(v) < 1e-6 for v in obstacle):
                result[chain] = {"distance": None}
                continue
            try:
                hand = [float(v) for v in motion.getPosition(chain, 2, True)][:3]
            except Exception:
                hand = [0.0, 0.0, obstacle[2]]
            dx, dy = obstacle[0] - hand[0], obstacle[1] - hand[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > OBSTACLE_MAX_DISTANCE:
                result[chain] = {"distance": None}
                continue
            result[chain] = {"distance": distance, "side": self._direction_label(obstacle[0], obstacle[1]),
                             "position": obstacle}
        if self.robot.generation == generation:
            self.cached_obstacles = result

    def simulate_obstacle(self, position):
        """Solo modalita' demo: ostacolo simulato (FRAME_ROBOT, metri) o None per toglierlo."""
        robot = self.robot
        if not robot.is_fake or not robot.session:
            return False, "disponibile solo in modalita' demo"
        robot.qi.simulate_obstacle(robot.session, position)
        return True, ("Ostacolo simulato a (%.2f, %.2f) m" % (position[0], position[1])) if position else "Ostacolo simulato rimosso"

    # ------------------------------------------------------------ temperature
    def refresh_temperatures(self):
        """Legge le temperature dei motori da ALMemory (senza lock: non blocca i comandi)."""
        generation = self.robot.generation
        memory = self.robot.memory
        if not memory:
            return
        keys = ["Device/SubDeviceList/%s/Temperature/Sensor/Value" % j for j in TEMPERATURE_JOINTS]
        status_keys = ["Device/SubDeviceList/%s/Temperature/Sensor/Status" % j for j in TEMPERATURE_JOINTS]
        try:
            values = memory.getListData(keys)
        except Exception as exc:
            self.robot.report("temperature", "[TEMPERATURA] Temperature dei motori non leggibili: %s" % exc)
            return
        try:
            statuses = memory.getListData(status_keys)
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
        if self.robot.generation != generation:
            return
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
                    self.robot.log("[TEMPERATURA] %s %s (%.0f C). Consiglio: Rest e qualche minuto di pausa."
                                   % (joint, label, temperature))
                else:
                    self.robot.log("[TEMPERATURA] %s di nuovo nella norma (%.0f C)" % (joint, temperature))
