# -*- coding: utf-8 -*-
"""
Collegamento con la WebApp: preleva i comandi da /api/pepper/next (polling),
li esegue tramite il controller e, se il comando ha un id, rimanda l'esito a
/api/pepper/result cosi' il tablet sa se il comando e' stato eseguito.
Con una WebApp vecchia (comandi senza id) l'esito non viene inviato.
"""
from __future__ import absolute_import

import time

from peppersign.http_utils import http_get_json, http_post_json
from peppersign.utils import safe_unicode


class WebAppBridge(object):
    def __init__(self, robot, controller):
        """controller: il PepperController che esegue i comandi (say, play_gesture, ...)."""
        self.robot = robot
        self.controller = controller
        self.connected_to_webapp = False
        self.last_cmd = None
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

    def handle_command(self, cmd):
        """
        Esegue un comando della WebApp. Ritorna (ok, messaggio), oppure None per
        NONE / azione vuota (niente da eseguire e niente esito da riportare).
        """
        action = safe_unicode(cmd.get("action", "")).strip().upper()
        if not action or action == "NONE":
            return None

        handler = self.command_handlers.get(action)
        if not handler:
            self.robot.log("[POLL] Azione sconosciuta: %s" % action)
            return False, "azione sconosciuta: %s" % action

        result = handler(cmd)
        if not (isinstance(result, tuple) and len(result) == 2):
            return True, "eseguito"
        return bool(result[0]), safe_unicode(result[1])

    def report_result(self, cmd, ok, message):
        """Rimanda alla WebApp l'esito di un comando che ha un id (WebApp nuova)."""
        command_id = safe_unicode(cmd.get("id", "")).strip()
        if not command_id:
            return
        url = self.robot.config["webapp"].get("result_url")
        if not url:
            return
        try:
            answer = http_post_json(url, {"id": command_id, "ok": bool(ok), "message": safe_unicode(message)},
                                    timeout=self.robot.config["webapp"].get("result_timeout", 3))
        except Exception as exc:
            self.robot.report("webapp_result", "[POLL] Esito del comando %s non inviato alla WebApp: %s"
                              % (command_id, exc))
            return
        # la WebApp risponde con un JSON anche agli errori (es. 404 se e' stata riavviata
        # e non conosce piu' il comando): non e' un'eccezione, ma l'esito non e' stato registrato
        if not (isinstance(answer, dict) and answer.get("ok")):
            reason = answer.get("error") if isinstance(answer, dict) else answer
            self.robot.report("webapp_result_rejected", "[POLL] La WebApp non ha registrato l'esito del comando "
                              "%s: %s" % (command_id, safe_unicode(reason)))

    def poll_loop(self):
        robot = self.robot
        config = robot.config
        next_url = config["webapp"]["next_url"]
        robot.log("[POLL] Avviato. Endpoint: %s" % next_url)

        while robot.running:
            # Robot disconnesso: non preleva comandi dalla WebApp (andrebbero persi)
            if not robot.robot_connected:
                time.sleep(1.0)
                continue
            try:
                cmd = http_get_json(next_url, timeout=config["webapp"]["poll_timeout"])
                self.last_cmd = cmd
                if not self.connected_to_webapp:
                    self.controller.say("Connessione alla Web App riuscita. Sono pronto.")
                    self.connected_to_webapp = True
            except Exception as exc:
                if self.connected_to_webapp:
                    self.controller.say("Ho perso la connessione con il computer.")
                self.connected_to_webapp = False
                robot.set_error("Polling WebApp fallito: %s" % str(exc))
                time.sleep(config["webapp"]["poll_sleep_error"])
                continue

            try:
                result = self.handle_command(cmd)
            except Exception as exc:
                robot.set_error("Errore gestione comando: %s" % str(exc))
                result = (False, "errore interno di Controll: %s" % exc)
            if result is not None:
                self.report_result(cmd, result[0], result[1])

            action = safe_unicode(cmd.get("action", "")).strip().upper()
            if not action or action == "NONE":
                time.sleep(config["webapp"]["poll_sleep_idle"])
            else:
                time.sleep(config["webapp"]["poll_sleep_ok"])

    # ------------------------------------------------------------ comandi
    def _handle_none(self, cmd):
        return None

    def _handle_say(self, cmd):
        return self.controller.say(cmd.get("text", ""))

    def _handle_say_animated(self, cmd):
        ok, message = self.controller.say_animated(cmd.get("text", ""))
        if not ok:
            self.robot.log("[SAY_ANIMATED] FAIL: %s" % message)
        return ok, message

    def _handle_play_gesture(self, cmd):
        ok, message = self.controller.play_gesture(cmd.get("gestureId", ""))
        if not ok:
            self.robot.log("[GESTURE] FAIL: %s" % message)
        return ok, message

    def _handle_say_and_listen(self, cmd):
        ok, message = self.controller.say_and_listen(cmd.get("sessionId"), cmd.get("prompt", ""))
        if not ok:
            self.robot.log("[SAY_AND_LISTEN] FAIL: %s" % message)
        return ok, message

    def _handle_wakeup(self, cmd):
        return self.controller.wakeup()

    def _handle_rest(self, cmd):
        return self.controller.rest()

    def _handle_life_on(self, cmd):
        ok, message = self.controller.set_autonomous_life(True)
        if not ok:
            self.robot.log("[LIFE] FAIL: %s" % message)
        return ok, message

    def _handle_life_off(self, cmd):
        ok, message = self.controller.set_autonomous_life(False)
        if not ok:
            self.robot.log("[LIFE] FAIL: %s" % message)
        return ok, message
