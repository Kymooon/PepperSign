# -*- coding: utf-8 -*-
"""
Autonomous Life e movimenti autonomi di Pepper.

- Modalita' manuale per la registrazione (disable_stack) e riattivazione (set_life).
- Durante i gesti: Autonomous Life puo' restare attiva; subito prima di ogni
  gesto vengono messi in pausa solo i movimenti autonomi che interferiscono
  con le braccia (e con la testa, se il gesto la usa); subito dopo viene
  ripristinato esattamente lo stato precedente.
"""
from __future__ import absolute_import

import threading
import time

from peppersign.gesture_store import HEAD_JOINTS
from peppersign.utils import safe_unicode

GESTURE_AUTONOMY_MODES = ("pause", "off", "none")

# (nome ability per ALAutonomousLife, attributo del servizio dedicato in RobotSession)
ARM_ABILITIES = [
    ("BackgroundMovement", "background_movement"),
    ("ListeningMovement", "listening_movement"),
    ("SpeakingMovement", "speaking_movement"),
]


class AutonomyManager(object):
    def __init__(self, robot):
        self.robot = robot
        self.cached_life_state = "N/A"
        # azioni di ripristino non riuscite (sessione persa a meta' gesto):
        # vengono rifatte alla connessione successiva (apply_pending_locked)
        self.pending = []
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------ stato
    def get_state(self):
        autonomous_life = self.robot.autonomous_life
        if not autonomous_life:
            return "N/A"
        try:
            return autonomous_life.getState()
        except Exception as exc:
            self.robot.report("life_state", "[AUTO] Stato di Autonomous Life non leggibile: %s" % exc)
            return "ERR"

    def normalized_state(self):
        return safe_unicode(self.get_state()).strip().lower()

    def wait_state(self, expected, timeout=2.0):
        """Rilegge lo stato di Autonomous Life finche' non e' in `expected` o scade il timeout."""
        deadline = time.time() + float(timeout)
        state = self.normalized_state()
        while state not in expected and time.time() < deadline:
            time.sleep(0.2)
            state = self.normalized_state()
        return state

    def refresh_cache(self):
        generation = self.robot.generation
        state = self.get_state()
        if self.robot.generation == generation:      # niente valori di una sessione gia' chiusa
            self.cached_life_state = state

    # ------------------------------------------------------------ modalita' manuale / vita autonoma attiva
    def disable_stack(self):
        """
        Porta Pepper in una modalita' manuale per la registrazione dei gesti.

        Importante: non modifica il meccanismo di cattura delle pose. Serve solo
        a ridurre i movimenti autonomi prima della registrazione.
        """
        robot = self.robot
        log = robot.log
        life_ok = True
        life_msg = ""
        life_state = None
        with robot.lock:
            if robot.behavior:
                try:
                    robot.behavior.stopAllBehaviors()
                    log("[AUTO] stopAllBehaviors OK")
                except Exception as exc:
                    log("[AUTO] stopAllBehaviors FAIL: %s" % str(exc))

            if robot.autonomous_life:
                try:
                    robot.autonomous_life.setState("disabled")
                except Exception as exc:
                    life_ok = False
                    life_msg = "setState('disabled') rifiutato: %s" % str(exc)
                    log("[AUTO] Autonomous Life disable FAIL: %s" % str(exc))
                # Verifica: lo stato viene riletto dal robot, non dato per scontato
                life_state = self.wait_state(("disabled",), 2.0)
                self.cached_life_state = life_state
                if life_state == "disabled":
                    log("[AUTO] Autonomous Life disabled (verificato)")
                else:
                    life_ok = False
                    if life_msg:
                        life_msg += "; stato attuale: %s" % life_state
                    else:
                        life_msg = "stato attuale: %s" % life_state
                    log("[AUTO] Autonomous Life NON disattivata: stato = %s" % life_state)
            else:
                log("[AUTO] ALAutonomousLife non disponibile")

            if robot.basic_awareness:
                try:
                    if robot.basic_awareness.isRunning():
                        robot.basic_awareness.stopAwareness()
                    log("[AUTO] Basic Awareness stopped")
                except Exception as exc:
                    log("[AUTO] Basic Awareness stop FAIL: %s" % str(exc))

            robot.safe_call(robot.background_movement, "setEnabled", "Background Movement OFF", False)
            robot.safe_call(robot.listening_movement, "setEnabled", "Listening Movement OFF", False)
            robot.safe_call(robot.speaking_movement, "setEnabled", "Speaking Movement OFF", False)
            robot.safe_call(robot.autonomous_blinking, "setEnabled", "Autonomous Blinking OFF", False)

            if robot.motion:
                try:
                    robot.motion.setBreathEnabled("Body", False)
                    log("[AUTO] Breath Body OFF")
                except Exception as exc:
                    log("[AUTO] Breath Body OFF FAIL: %s" % str(exc))

                try:
                    robot.motion.setIdlePostureEnabled("Body", False)
                    log("[AUTO] Idle Posture Body OFF")
                except Exception as exc:
                    log("[AUTO] Idle Posture Body OFF FAIL: %s" % str(exc))

        if not life_ok:
            hint = ""
            if life_state == "safeguard":
                hint = (" - Pepper e' in safeguard: controlla sportello di ricarica, "
                        "base bloccata o caduta")
            return False, ("Autonomous Life NON disattivata (%s)%s. "
                           "Altri movimenti autonomi spenti dove possibile" % (life_msg, hint))
        if not robot.autonomous_life:
            return True, ("Modalita' manuale attivata: movimenti autonomi disattivati "
                          "(ALAutonomousLife non disponibile)")
        return True, "Modalita' manuale attivata: Autonomous Life disabled, movimenti autonomi disattivati"

    def set_life(self, enabled):
        if not enabled:
            return self.disable_stack()

        robot = self.robot
        log = robot.log
        with robot.lock:
            try:
                robot.safe_call(robot.background_movement, "setEnabled", "Background Movement ON", True)
                robot.safe_call(robot.listening_movement, "setEnabled", "Listening Movement ON", True)
                robot.safe_call(robot.autonomous_blinking, "setEnabled", "Autonomous Blinking ON", True)

                if robot.motion:
                    try:
                        robot.motion.setBreathEnabled("Body", True)
                        log("[AUTO] Breath Body ON")
                    except Exception as exc:
                        log("[AUTO] Breath Body ON FAIL: %s" % str(exc))

                    try:
                        robot.motion.setIdlePostureEnabled("Body", True)
                        log("[AUTO] Idle Posture Body ON")
                    except Exception as exc:
                        log("[AUTO] Idle Posture Body ON FAIL: %s" % str(exc))

                if not robot.autonomous_life:
                    return False, "ALAutonomousLife non disponibile; movimenti autonomi riabilitati dove possibile"

                try:
                    robot.autonomous_life.setState("interactive")
                except Exception as exc:
                    log("[AUTO] setState('interactive') FAIL: %s - provo 'solitary'" % str(exc))
                    try:
                        robot.autonomous_life.setState("solitary")
                    except Exception as exc2:
                        self.cached_life_state = self.normalized_state()
                        return False, "Errore setState: %s (stato attuale: %s)" % (
                            str(exc2), self.cached_life_state)

                # Verifica: lo stato viene riletto dal robot
                state = self.wait_state(("interactive", "solitary"), 2.0)
                self.cached_life_state = state
                if state in ("interactive", "solitary"):
                    log("[AUTO] Autonomous Life %s (verificato)" % state)
                    return True, "Autonomous Life: %s" % state
                return False, "Autonomous Life NON attivata: stato attuale %s" % state

            except Exception as exc:
                return False, "Errore setState: %s" % str(exc)

    # ------------------------------------------------------------ durante i gesti
    def gesture_mode(self):
        mode = self.robot.config.get("robot_defaults", {}).get("gesture_autonomy", "pause")
        mode = safe_unicode(mode).strip().lower()
        if mode not in GESTURE_AUTONOMY_MODES:
            return "pause"
        return mode

    def get_ability_enabled(self, ability, service_attr):
        """Stato attuale di una autonomous ability (True/False) o None se ignoto."""
        robot = self.robot
        if robot.autonomous_life:
            try:
                return bool(robot.autonomous_life.getAutonomousAbilityEnabled(ability))
            except Exception as exc:
                robot.warn_once("ability_get:" + ability,
                                "[AUTONOMY] getAutonomousAbilityEnabled(%s) non disponibile (%s): "
                                "uso il servizio dedicato" % (ability, exc))
        service = getattr(robot, service_attr, None) if service_attr else None
        if service:
            try:
                value = service.isEnabled()
                if value is not None:
                    return bool(value)
            except Exception as exc:
                robot.warn_once("service_get:" + ability,
                                "[AUTONOMY] Stato di %s non leggibile (%s)" % (ability, exc))
        return None

    def set_ability_enabled(self, ability, service_attr, enabled):
        robot = self.robot
        if robot.autonomous_life:
            try:
                robot.autonomous_life.setAutonomousAbilityEnabled(ability, bool(enabled))
                return True
            except Exception as exc:
                robot.warn_once("ability_set:" + ability,
                                "[AUTONOMY] setAutonomousAbilityEnabled(%s) non disponibile (%s): "
                                "uso il servizio dedicato" % (ability, exc))
        service = getattr(robot, service_attr, None) if service_attr else None
        if service:
            try:
                service.setEnabled(bool(enabled))
                return True
            except Exception as exc:
                robot.report("ability_service_set:" + ability,
                             "[AUTONOMY] %s non modificabile: %s" % (ability, exc))
        return False

    def suspend_for_gesture_locked(self, joints):
        """
        Mette in pausa i movimenti autonomi in conflitto con il gesto.
        Ritorna la lista di azioni di ripristino (da passare a restore_after_gesture_locked).
        Da chiamare tenendo robot.lock. Ogni chiamata e' protetta: se una API non
        esiste su questa versione di NAOqi, il gesto parte comunque.
        """
        robot = self.robot
        motion = robot.motion
        basic_awareness = robot.basic_awareness
        mode = self.gesture_mode()
        restore = []
        paused = []
        if mode == "none":
            return restore

        joint_set = set(joints or [])
        uses_head = bool(joint_set.intersection(HEAD_JOINTS))
        chain = "Body" if mode == "off" else "Arms"

        # 1) respiro e postura di riposo (su braccia, o su tutto il corpo in "off")
        if motion:
            for getter, setter, label in (
                ("getBreathEnabled", "setBreathEnabled", "Breath"),
                ("getIdlePostureEnabled", "setIdlePostureEnabled", "IdlePosture"),
            ):
                try:
                    # tocco solo cio' che e' sicuramente attivo, cosi' il ripristino
                    # non accende mai qualcosa che era spento
                    if getattr(motion, getter)(chain):
                        getattr(motion, setter)(chain, False)
                        restore.append(("motion", setter, chain, True))
                        paused.append("%s %s" % (label, chain))
                except Exception as exc:
                    robot.warn_once("pause:" + label, "[AUTONOMY] %s %s non messo in pausa per i gesti: %s"
                                    % (label, chain, exc))

        # 2) movimenti autonomi che agiscono sulle braccia
        abilities = list(ARM_ABILITIES)
        if mode == "off":
            abilities.append(("AutonomousBlinking", "autonomous_blinking"))
        for ability, service_attr in abilities:
            previous = self.get_ability_enabled(ability, service_attr)
            if previous is False:
                continue
            if self.set_ability_enabled(ability, service_attr, False):
                restore.append(("ability", ability, service_attr, True))
                paused.append(ability)

        # 3) BasicAwareness: in pausa se il gesto usa la testa (o in "off");
        #    altrimenti resta attiva ma solo con la testa, senza ruotare la base.
        if basic_awareness:
            if uses_head or mode == "off":
                previous = self.get_ability_enabled("BasicAwareness", None)
                if previous is None:
                    try:
                        previous = bool(basic_awareness.isRunning())
                    except Exception:
                        previous = None
                if previous:
                    done = self.set_ability_enabled("BasicAwareness", None, False)
                    if not done:
                        try:
                            basic_awareness.pauseAwareness()
                            done = True
                            restore.append(("call", "basic_awareness", "resumeAwareness", ()))
                        except Exception:
                            try:
                                basic_awareness.stopAwareness()
                                done = True
                                restore.append(("call", "basic_awareness", "startAwareness", ()))
                            except Exception as exc:
                                robot.log("[AUTONOMY] BasicAwareness non messa in pausa per il gesto: %s" % exc)
                    else:
                        restore.append(("ability", "BasicAwareness", None, True))
                    if done:
                        paused.append("BasicAwareness")
            else:
                try:
                    previous_mode = basic_awareness.getTrackingMode()
                    if previous_mode and safe_unicode(previous_mode) != u"Head":
                        basic_awareness.setTrackingMode("Head")
                        restore.append(("call", "basic_awareness", "setTrackingMode", (previous_mode,)))
                        paused.append("TrackingMode %s->Head" % safe_unicode(previous_mode))
                except Exception as exc:
                    robot.warn_once("tracking_mode", "[AUTONOMY] Modalita' di tracking di BasicAwareness "
                                    "non modificabile (%s): la base potrebbe ruotare durante i gesti" % exc)

        # 4) la rigidezza piena sui giunti del gesto e' impostata dal GesturePlayer
        #    (anche con gesture_autonomy = none)

        if paused:
            robot.log("[AUTONOMY] Pausa per il gesto (%s): %s" % (mode, ", ".join(paused)))
        return restore

    def restore_after_gesture_locked(self, restore):
        """Ripristina, in ordine inverso, quanto messo in pausa da suspend_for_gesture_locked."""
        if not restore:
            return
        failed = self._restore_items(list(reversed(restore)))
        if failed:
            with self._pending_lock:
                self.pending.extend(failed)
            self.robot.log("[AUTONOMY] %d movimenti autonomi da ripristinare alla prossima connessione" % len(failed))
            return
        self.robot.log("[AUTONOMY] Movimenti autonomi ripristinati")

    def apply_pending_locked(self):
        """Dopo una riconnessione: rifa' i ripristini non riusciti durante un gesto interrotto."""
        with self._pending_lock:
            pending, self.pending = self.pending, []
        if not pending:
            return
        failed = self._restore_items(pending)
        if failed:
            with self._pending_lock:
                self.pending.extend(failed)
            self.robot.log("[AUTONOMY] Ripristino dopo la riconnessione non completo: %d azioni ancora in sospeso"
                           % len(failed))
        else:
            self.robot.log("[AUTONOMY] Movimenti autonomi ripristinati dopo la riconnessione "
                           "(erano rimasti in pausa per un gesto interrotto)")

    def _restore_items(self, items):
        """Esegue le azioni di ripristino (gia' in ordine); ritorna quelle non riuscite."""
        robot = self.robot
        # Se nel frattempo Autonomous Life e' stata disattivata (modalita' manuale),
        # i movimenti autonomi NON vengono riaccesi dopo il gesto.
        life_disabled = self.normalized_state() == "disabled"
        skipped = []
        failed = []
        for item in items:
            if life_disabled and (item[0] == "ability" or
                                  (item[0] == "call" and item[2] in ("startAwareness", "resumeAwareness"))):
                skipped.append(item[1] if item[0] == "ability" else "BasicAwareness")
                continue
            try:
                kind = item[0]
                if kind == "motion":
                    _, setter, chain, value = item
                    getattr(robot.motion, setter)(chain, value)
                elif kind == "ability":
                    _, ability, service_attr, value = item
                    if not self.set_ability_enabled(ability, service_attr, value):
                        raise RuntimeError("servizio non disponibile")
                elif kind == "call":
                    _, service_attr, method, args = item
                    getattr(getattr(robot, service_attr), method)(*args)
            except Exception as exc:
                failed.append(item)
                robot.log("[AUTONOMY] Ripristino non riuscito (%s): %s" % (item[1], str(exc)))
        if skipped:
            robot.log("[AUTONOMY] Autonomous Life disabled: non riattivati %s" % ", ".join(skipped))
        return failed
