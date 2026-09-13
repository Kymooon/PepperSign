#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import sys
import threading

from peppersign.config import build_runtime_config
from peppersign.controller import PepperController
from peppersign.gesture_store import GestureStore
from peppersign.gui import PepperGUI
from peppersign.utils import tcp_check


def resolve_config_path(argv):
    if len(argv) > 1:
        return argv[1]
    env_path = os.environ.get("PEPPERSIGN_CONFIG")
    if env_path:
        return env_path
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(default_path):
        return default_path
    return None


def main():
    print "[BOOT] Avvio PepperSign Controller + GUI"

    config_path = resolve_config_path(sys.argv)
    config = build_runtime_config(config_path)

    robot_ip = config["robot"]["ip"]
    robot_port = config["robot"]["port"]

    if not tcp_check(robot_ip, robot_port, timeout=2):
        print "[ERRORE] Pepper non raggiungibile su %s:%d" % (robot_ip, robot_port)
        sys.exit(1)

    gesture_store = GestureStore(config["paths"]["gesture_dir"], log_cb=None)
    gesture_store.reload()

    controller = PepperController(config, gesture_store=gesture_store, log_cb=None)
    gui = PepperGUI(controller, config, gesture_store)
    controller.log_cb = gui.enqueue_log
    gesture_store.log_cb = gui.enqueue_log

    try:
        controller.connect()
    except Exception as exc:
        gui.enqueue_log("[ERRORE] Connessione QI fallita: %s" % str(exc))
        print "[ERRORE] Connessione QI fallita:", str(exc)
        gui.run()
        sys.exit(1)

    gui.enqueue_log("[OK] WebApp: %s" % config["webapp"]["base_url"])
    gui.enqueue_log("[INFO] NEXT_URL: %s" % config["webapp"]["next_url"])
    gui.enqueue_log("[INFO] Gesture dir: %s" % config["paths"]["gesture_dir"])
    gui.enqueue_log("[HINT] Workflow: Life OFF -> WakeUp -> Free Arms -> Dump Pose -> Hold Arms -> Test -> Salva/Export -> Ricarica")

    poll_thread = threading.Thread(target=controller.poll_webapp_loop)
    poll_thread.daemon = True
    poll_thread.start()

    gui.run()

    controller.running = False
    if config["ui"].get("rest_on_close", True):
        try:
            controller.rest()
        except Exception:
            pass
    print "[EXIT] Chiusura."


if __name__ == "__main__":
    main()
