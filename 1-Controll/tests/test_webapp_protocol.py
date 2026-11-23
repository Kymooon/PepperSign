# -*- coding: utf-8 -*-
"""
Prova completa del protocollo dei comandi (problema 7): WebApp vera + Controll con robot simulato.

Uso (dalla cartella 1-Controll, con la WebApp avviata):
    python2.7 tests/test_webapp_protocol.py . http://127.0.0.1:8080/PepperSign

Controlla che:
  - senza Controll collegato la WebApp rifiuti subito i comandi ("robot non collegato");
  - con Controll collegato un comando passi da queued/sent a done, con il messaggio di Controll;
  - un comando che fallisce sul robot (gesto inesistente) risulti "failed" con il motivo;
  - quando Controll si ferma, dopo qualche secondo la WebApp lo veda scollegato.
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import json
import os
import sys
import tempfile
import threading
import time
import urllib
import urllib2

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
WEBAPP = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8080/PepperSign").rstrip("/")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"
os.environ["PEPPERSIGN_WEBAPP_URL"] = WEBAPP

from peppersign import fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign.utils import write_json  # noqa: E402

fake_qi.MAX_SIMULATED_SECONDS = 0.3
FAILURES = []
API = WEBAPP + "/api/pepper"


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


def http(method, path, form=None):
    data = urllib.urlencode(form) if form is not None else None
    req = urllib2.Request(API + path, data=data)
    if method == "POST" and data is None:
        req.add_data("")
    try:
        resp = urllib2.urlopen(req, timeout=5)
        return resp.getcode(), json.loads(resp.read())
    except urllib2.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def wait_final(command_id, timeout=15.0):
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        code, data = http("GET", "/command?id=" + urllib.quote(command_id))
        status = data.get("status")
        if not seen or seen[-1] != status:
            seen.append(status)
        if data.get("final"):
            return data, seen
        time.sleep(0.1)
    return data, seen


def wait_until(predicate, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.2)
    return predicate()


def main():
    print("WebApp: %s" % WEBAPP)
    print("1) Senza Controll")
    wait_until(lambda: not http("GET", "/robot")[1].get("online"), 8.0)
    code, data = http("POST", "/gesture", {"gestureId": "ciao"})
    check("gesto rifiutato con 503", code == 503, "%s %s" % (code, data))
    check("motivo: robot non collegato", "non collegato" in data.get("error", ""), str(data))

    print("2) Controll collegato")
    tmp = tempfile.mkdtemp(prefix="ps_proto_")
    write_json(os.path.join(tmp, "ciao.json"), {
        "name": "ciao", "format": "frames_v1",
        "joints": ["RShoulderPitch", "RHand"],
        "frames": [{"angles": [0.5, 1.0], "dt": 0.3}, {"angles": [1.5, 0.3], "dt": 0.3}]})
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    config["robot_defaults"]["gesture_pre_delay"] = 0.0
    config["robot_defaults"]["gesture_post_delay"] = 0.0
    logs = []
    store = GestureStore(tmp, log_cb=logs.append)
    store.reload()
    ctrl = PepperController(config, gesture_store=store, log_cb=logs.append)
    ctrl.connect()
    poll = threading.Thread(target=ctrl.poll_webapp_loop)
    poll.daemon = True
    poll.start()
    check("la WebApp vede Controll collegato", wait_until(lambda: http("GET", "/robot")[1].get("online"), 5.0))

    cases = [
        ("SAY", "/say", {"text": u"Ciao città".encode("utf-8")}, "done", "detto"),
        ("ANIMATED_SAY", "/animated-say", {"text": "buongiorno"}, "done", "animated speech ok"),
        ("PLAY_GESTURE esistente", "/gesture", {"gestureId": "Ciao"}, "done", "gesture eseguita"),
        ("PLAY_GESTURE inesistente", "/gesture", {"gestureId": "nessuno"}, "failed", "non mappato"),
    ]
    for label, path, form, expected, fragment in cases:
        code, data = http("POST", path, form)
        ok = code == 200 and data.get("ok") and data.get("id")
        check("%s accodato con id" % label, ok, "%s %s" % (code, data))
        if not ok:
            continue
        final, seen = wait_final(data["id"])
        check("%s -> %s" % (label, expected), final.get("status") == expected, "%s (stati: %s)" % (final, seen))
        check("%s: messaggio di Controll" % label, fragment in final.get("message", ""), str(final))

    print("3) Comandi in fila mentre il robot esegue un gesto")
    fake_qi.MAX_SIMULATED_SECONDS = 2.0
    ids = []
    for i in range(3):
        code, data = http("POST", "/gesture", {"gestureId": "ciao"})
        check("gesto %d accodato anche mentre il robot e' occupato" % (i + 1), code == 200, "%s %s" % (code, data))
        ids.append(data.get("id"))
        time.sleep(0.3)
    finals = [wait_final(i, 20.0)[0].get("status") for i in ids if i]
    check("tutti e tre eseguiti in ordine", finals == ["done", "done", "done"], str(finals))
    fake_qi.MAX_SIMULATED_SECONDS = 0.3

    print("4) Controll si ferma")
    ctrl.running = False
    check("dopo qualche secondo la WebApp lo vede scollegato",
          wait_until(lambda: not http("GET", "/robot")[1].get("online"), 10.0))
    code, data = http("POST", "/say", {"text": "ciao"})
    check("comando rifiutato con robot scollegato", code == 503 and not data.get("queued"), "%s %s" % (code, data))

    errors = [l for l in logs if "non inviato alla WebApp" in str(l)]
    check("nessun esito perso nell'invio alla WebApp", not errors, str(errors[:2]))
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITI %d controlli: %s" % (len(FAILURES), ", ".join(FAILURES))))
    sys.stdout.flush()
    os._exit(0 if not FAILURES else 1)


if __name__ == "__main__":
    main()
