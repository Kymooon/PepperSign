#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import sys
import threading
import time

from peppersign.config import build_runtime_config, fake_robot_enabled
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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("config.json", "config.local.json"):
        default_path = os.path.join(base_dir, name)
        if os.path.exists(default_path):
            return default_path
    return None


def main():
    print "[BOOT] Avvio PepperSign Controller + GUI"

    config_path = resolve_config_path(sys.argv)
    config = build_runtime_config(config_path)

    robot_ip = config["robot"]["ip"]
    robot_port = config["robot"]["port"]
    demo_mode = fake_robot_enabled()

    if demo_mode:
        print "[DEMO] Modalita' demo attiva: robot Pepper SIMULATO (PEPPERSIGN_FAKE_ROBOT=1)"
        config["ui"]["window_title"] = config["ui"]["window_title"] + "  [DEMO - robot simulato]"

    # PEPPERSIGN_ROBOT_WAIT: secondi di attesa del robot prima di arrendersi
    # (0 = comportamento originale, esce subito). Utile in Docker, dove il
    # container puo' partire prima che Pepper sia acceso.
    try:
        wait_seconds = int(os.environ.get("PEPPERSIGN_ROBOT_WAIT", "0"))
    except ValueError:
        wait_seconds = 0
    deadline = time.time() + max(0, wait_seconds)
    while not demo_mode and not tcp_check(robot_ip, robot_port, timeout=2):
        if time.time() >= deadline:
            # Non si esce piu': la GUI parte comunque e la riconnessione
            # automatica (controller.monitor_loop) aggancia Pepper appena e' raggiungibile.
            print "[AVVISO] Pepper non raggiungibile su %s:%d: avvio la GUI in attesa del robot" % (robot_ip, robot_port)
            break
        print "[BOOT] Attendo Pepper su %s:%d ..." % (robot_ip, robot_port)
        sys.stdout.flush()
        time.sleep(5)

    gesture_store = GestureStore(config["paths"]["gesture_dir"], log_cb=None)
    gesture_store.reload()

    controller = PepperController(config, gesture_store=gesture_store, log_cb=None)
    gui = PepperGUI(controller, config, gesture_store)
    controller.log_cb = gui.enqueue_log
    gesture_store.log_cb = gui.enqueue_log

    try:
        controller.connect()
    except Exception as exc:
        controller.robot_connected = False
        controller.connection_state = "DISCONNESSO"
        gui.enqueue_log("[ERRORE] Connessione QI fallita: %s" % str(exc))
        gui.enqueue_log("[ROBOT] Riconnessione automatica attiva: riprovo ogni %d s" % int(controller.reconnect_interval))
        print "[ERRORE] Connessione QI fallita:", str(exc)

    monitor_thread = threading.Thread(target=controller.monitor_loop)
    monitor_thread.daemon = True
    monitor_thread.start()

    if demo_mode:
        gui.enqueue_log("[DEMO] Robot simulato: i comandi vengono solo registrati qui, nessun robot si muove.")
    gui.enqueue_log("[OK] WebApp: %s" % config["webapp"]["base_url"])
    gui.enqueue_log("[INFO] NEXT_URL: %s" % config["webapp"]["next_url"])
    gui.enqueue_log("[INFO] Gesture dir: %s" % config["paths"]["gesture_dir"])
    gui.enqueue_log("[HINT] Workflow: Life OFF -> WakeUp -> Free Arms -> Dump Pose -> Hold Arms -> Test -> Salva/Export -> Ricarica")

    poll_thread = threading.Thread(target=controller.poll_webapp_loop)
    poll_thread.daemon = True
    poll_thread.start()

    gui.run()

    controller.running = False
    if config["ui"].get("rest_on_close", True) and controller.robot_connected:
        try:
            controller.rest()
        except Exception:
            pass
    print "[EXIT] Chiusura."


if __name__ == "__main__":
    main()
