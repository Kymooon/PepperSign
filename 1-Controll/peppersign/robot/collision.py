# -*- coding: utf-8 -*-
"""
Anti-collisione tra le braccia spenta solo in alcuni frame del gesto.

Il gesto resta un unico angleInterpolation (movimento fluido); un thread
spegne e riaccende la protezione agli istanti dei frame segnati. Non usa il
lock della sessione (tenuto dal thread del gesto): le chiamate qi sono thread-safe.
"""
from __future__ import absolute_import

import threading
import time

from peppersign.utils import safe_unicode

ARM_COLLISION_CHAINS = ("Arms", "LArm", "RArm")


def normalize_collision_chain(chain):
    chain = safe_unicode(chain or "Arms").strip()
    return str(chain) if chain in ARM_COLLISION_CHAINS else "Arms"


class ArmCollisionScheduler(object):
    def __init__(self, robot):
        self.robot = robot
        # catene la cui anti-collisione non e' stata riattivata (sessione persa a meta' gesto):
        # vengono riattivate alla connessione successiva (apply_pending_locked)
        self.pending = set()
        self._pending_lock = threading.Lock()

    def collision_state(self, chain):
        """'none' | 'near' | 'collision' da ALMotion.isCollision, None se non disponibile."""
        try:
            return safe_unicode(self.robot.motion.isCollision(chain)).strip().lower()
        except Exception as exc:
            self.robot.warn_once("isCollision", "[SICUREZZA] ALMotion.isCollision non disponibile (%s): "
                                 "l'anti-collisione viene riattivata senza attendere che le braccia si separino" % exc)
            return None

    def start(self, windows, chain):
        """Avvia il thread che segue le finestre; ritorna lo stato da passare a finish(), o None."""
        motion = self.robot.motion
        log = self.robot.log
        chain = normalize_collision_chain(chain)
        sides = ["LArm", "RArm"] if chain == "Arms" else [chain]
        previous = {}
        for side in sides:
            try:
                previous[side] = bool(motion.getCollisionProtectionEnabled(side))
            except Exception as exc:
                previous[side] = True        # nel dubbio la considero attiva: a fine gesto viene riattivata
                self.robot.warn_once("getCollisionProtectionEnabled",
                                     "[SICUREZZA] Stato dell'anti-collisione non leggibile (%s): la considero attiva" % exc)
        if not any(previous.values()):
            log("[SICUREZZA] Anti-collisione tra le braccia gia' disattivata: nessun cambio durante il gesto")
            return None
        clean = []
        for window in windows:
            try:
                clean.append((float(window[0]), float(window[1])))
            except (TypeError, ValueError, IndexError):
                log("[SICUREZZA] Finestra senza anti-collisione non valida, ignorata: %r" % (window,))
        if not clean:
            return None
        state = {"chain": chain, "sides": sides, "previous": previous, "windows": clean,
                 "stop": threading.Event(), "off": False, "t0": time.time()}
        log("[SICUREZZA] Anti-collisione braccia (%s) disattivata in: %s" % (
            chain, ", ".join("%.1f-%.1f s" % w for w in clean)))
        thread = threading.Thread(target=self._loop, args=(state,))
        thread.daemon = True
        state["thread"] = thread
        thread.start()
        return state

    def _set(self, state, enabled):
        motion = self.robot.motion
        if enabled:
            for side in state["sides"]:
                if state["previous"].get(side, True):
                    motion.setCollisionProtectionEnabled(side, True)
        else:
            motion.setCollisionProtectionEnabled(state["chain"], False)
        state["off"] = not enabled

    def _loop(self, state):
        log = self.robot.log
        stop = state["stop"]
        t0 = state["t0"]
        windows = state["windows"]
        for index, (start, end) in enumerate(windows):
            if stop.wait(max(0.0, t0 + start - time.time())):
                return
            if not state["off"]:
                try:
                    self._set(state, False)
                    log("[SICUREZZA] Anti-collisione braccia OFF a %.1f s" % (time.time() - t0))
                except Exception as exc:
                    log("[SICUREZZA] Impossibile disattivare l'anti-collisione: %s" % str(exc))
                    continue
            if stop.wait(max(0.0, t0 + end - time.time())):
                return
            # riaccendo solo con le braccia lontane ("none"); se la finestra
            # successiva sta per iniziare resto spento e passo a quella
            next_start = windows[index + 1][0] if index + 1 < len(windows) else None
            keep_off = False
            while not stop.is_set():
                status = self.collision_state(state["chain"])
                if status is None or status == "none":
                    break
                if next_start is not None and time.time() >= t0 + next_start:
                    keep_off = True
                    break
                stop.wait(0.05)
            if stop.is_set():
                return
            if keep_off:
                continue
            try:
                self._set(state, True)
                log("[SICUREZZA] Anti-collisione braccia di nuovo ON a %.1f s" % (time.time() - t0))
            except Exception as exc:
                log("[SICUREZZA] Impossibile riattivare l'anti-collisione: %s" % str(exc))

    def finish(self, state):
        """A fine gesto (anche dopo un errore) riporta la protezione allo stato iniziale."""
        motion = self.robot.motion
        log = self.robot.log
        state["stop"].set()
        state["thread"].join(2.0)
        was_off = state["off"]
        failed = []
        for side in state["sides"]:
            if state["previous"].get(side, True):
                try:
                    motion.setCollisionProtectionEnabled(side, True)
                except Exception as exc:
                    failed.append(side)
                    log("[SICUREZZA] Riattivazione anti-collisione %s non riuscita: %s" % (side, str(exc)))
        if failed:
            with self._pending_lock:
                self.pending.update(failed)
            log("[SICUREZZA] Anti-collisione %s da riattivare alla prossima connessione" % ", ".join(failed))
            return
        state["off"] = False
        if was_off:
            log("[SICUREZZA] Anti-collisione braccia riattivata a fine gesto")
            status = self.collision_state(state["chain"])
            if status not in (None, "none"):
                log("[SICUREZZA] Attenzione: a fine gesto le braccia sono ancora vicine (%s)" % status)

    def apply_pending_locked(self):
        """Dopo una riconnessione: riattiva l'anti-collisione rimasta spenta da un gesto interrotto."""
        with self._pending_lock:
            pending = sorted(self.pending)
        if not pending:
            return
        motion = self.robot.motion
        for side in pending:
            try:
                motion.setCollisionProtectionEnabled(side, True)
                with self._pending_lock:
                    self.pending.discard(side)
                self.robot.log("[SICUREZZA] Anti-collisione %s riattivata dopo la riconnessione "
                               "(era rimasta spenta da un gesto interrotto)" % side)
            except Exception as exc:
                self.robot.log("[SICUREZZA] Riattivazione anti-collisione %s dopo la riconnessione non riuscita: %s"
                               % (side, str(exc)))
