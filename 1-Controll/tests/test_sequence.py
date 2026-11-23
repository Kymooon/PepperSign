# -*- coding: utf-8 -*-
"""
Test della sequenza dei frame senza finestra (ui/sequence.py, refactor della GUI).

Uso (dalla cartella 1-Controll):  python2.7 tests/test_sequence.py .
Non serve un display: il modello non usa Tkinter. La validazione della posa e le
traiettorie arrivano dal controller con il robot simulato.
Esce con codice 1 se un controllo fallisce.
"""
from __future__ import print_function

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sys.path.insert(0, ROOT)
os.environ["PEPPERSIGN_FAKE_ROBOT"] = "1"

from peppersign import fake_qi  # noqa: E402
from peppersign.config import build_runtime_config  # noqa: E402
from peppersign.gesture_store import DEFAULT_JOINTS, GestureStore  # noqa: E402
from peppersign.controller import PepperController  # noqa: E402
from peppersign.robot.interpolation import NO_ARM_COLLISION_KEY  # noqa: E402
from peppersign.ui import sequence as seq  # noqa: E402

fake_qi.MAX_SIMULATED_SECONDS = 0.02
FAILURES = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("OK  " if condition else "FAIL", label,
                           (" - " + detail) if (detail and not condition) else ""))
    if not condition:
        FAILURES.append(label)


def raises(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type as exc:
        return exc
    except Exception as exc:
        return "eccezione diversa: %r" % exc
    return None


def main():
    tmp = tempfile.mkdtemp(prefix="ps_seq_")
    config = build_runtime_config(None)
    config["paths"]["gesture_dir"] = tmp
    store = GestureStore(tmp, log_cb=None)
    ctrl = PepperController(config, gesture_store=store, log_cb=None)
    ctrl.connect()          # robot simulato: limiti dei giunti per la validazione

    joints = seq.with_hands(DEFAULT_JOINTS)
    model = seq.SequenceModel(joints, ctrl.validate_frame_pose)
    rest = [0.0] * len(joints)
    for name, value in (("LShoulderPitch", 1.4), ("RShoulderPitch", 1.4), ("LElbowRoll", -0.5),
                        ("RElbowRoll", 0.5), ("LHand", 0.6), ("RHand", 0.6),
                        ("LShoulderRoll", 0.2), ("RShoulderRoll", -0.2)):
        rest[joints.index(name)] = value
    idx = joints.index

    print("1) Giunti di registrazione")
    check("mani aggiunte una volta", seq.with_hands(["HeadYaw", "LHand"]) == ["HeadYaw", "LHand", "RHand"])

    print("2) Nuovi frame dalla posa")
    check_, index = model.append_pose(rest, 0.6, joints=joints)
    check("posa valida aggiunta", check_.ok and index == 0 and len(model) == 1)
    bad = list(rest)
    bad[idx("LShoulderPitch")] = 5.0
    check_, index = model.append_pose(bad, 0.6)
    check("posa fuori limiti rifiutata", not check_.ok and index is None and len(model) == 1 and check_.errors)
    check("sequenza cambiata durante la lettura: rifiutata",
          isinstance(raises(seq.SequenceChanged, model.append_pose, rest, 0.6, joints[:4]), seq.SequenceChanged)
          and len(model) == 1)
    check_, index = model.append_pose(rest, 0.8, composite=True)
    check("frame composito", index == 1 and model.frames[1].get("composite") is True)

    print("3) Modifiche")
    check("angolo modificato", model.set_angle(0, idx("HeadYaw"), 0.3).ok and model.frames[0]["angles"][idx("HeadYaw")] == 0.3)
    before = list(model.frames[0]["angles"])
    check("angolo fuori limiti non applicato", not model.set_angle(0, idx("HeadYaw"), 9.0).ok
          and model.frames[0]["angles"] == before)
    check("dt limitato a 10 s", model.set_dt(0, 99) == seq.DT_MAX and model.frames[0]["dt"] == seq.DT_MAX)
    check("dt limitato a 0.05 s", model.set_dt(0, 0.0) == seq.DT_MIN)
    model.set_all_dt(0.7)
    check("dt a tutti", [f["dt"] for f in model.frames] == [0.7, 0.7])

    print("4) Specchio e componenti")
    model.frames[0]["angles"][idx("LShoulderRoll")] = 0.3
    model.frames[0]["angles"][idx("LElbowYaw")] = -1.0
    check("SX -> DX", model.mirror(0, seq.LEFT_TO_RIGHT_ARM_MIRROR).ok)
    angles = model.frames[0]["angles"]
    check("roll e yaw cambiano segno, pitch e mano no",
          angles[idx("RShoulderRoll")] == -0.3 and angles[idx("RElbowYaw")] == 1.0
          and angles[idx("RShoulderPitch")] == angles[idx("LShoulderPitch")] and angles[idx("RHand")] == angles[idx("LHand")])
    small = seq.SequenceModel(["HeadYaw", "HeadPitch"], ctrl.validate_frame_pose)
    small.frames = [{"angles": [0.0, 0.0], "dt": 0.6}]
    check("specchio senza giunti del braccio: MissingJoints",
          isinstance(raises(seq.MissingJoints, small.mirror, 0, seq.LEFT_TO_RIGHT_ARM_MIRROR), seq.MissingJoints))
    check("testa nel frame 1", model.apply_component(0, seq.HEAD_COMPONENT_JOINTS, [0.1, -0.1]).ok
          and model.frames[0]["angles"][idx("HeadYaw")] == 0.1 and model.frames[0].get("composite") is True)
    model.frames.append({"angles": [0.1, 0.2], "dt": 0.6})
    exc = raises(seq.AngleCountMismatch, model.apply_component, 2, seq.HEAD_COMPONENT_JOINTS, [0.0, 0.0])
    check("frame incoerente: niente completamento con zeri",
          isinstance(exc, seq.AngleCountMismatch) and exc.count == 2 and model.frames[2]["angles"] == [0.1, 0.2])
    check("rimozione", model.remove(2) and len(model) == 2 and not model.remove(5))

    print("5) Ordine, copia, anti-collisione")
    first, second = model.frames
    check("sposta giu'", model.move(0, 1) == 1 and model.frames == [second, first])
    check("oltre i limiti: niente", model.move(1, 1) is None and model.move(0, -1) is None)
    check("indice per identita'", model.index_of(first) == 1 and model.index_of({"angles": []}) is None)
    check_, new_index = model.copy_to_end(1)
    check("copia in coda con origine", check_.ok and new_index == 2 and model.frames[2]["copied_from_frame"] == 2)
    model.frames[2]["angles"][0] = 0.25
    check("la copia e' indipendente", model.frames[1]["angles"][0] != 0.25)
    model.set_no_collision(1, True)
    check("frame senza anti-collisione", model.frames[1].get(NO_ARM_COLLISION_KEY) is True
          and model.collision_windows() != [] and "NO-COLL" in model.describe(1))
    model.set_no_collision(1, False)
    check("anti-collisione ripristinata", NO_ARM_COLLISION_KEY not in model.frames[1] and model.collision_windows() == [])
    check("riga della lista", model.describe(0) == "Frame 01   dt=0.70s   comp")
    inserted = model.insert_after(0, {"angles": list(rest), "dt": 0.5})
    check("inserito dopo il selezionato", inserted == 1 and model.frames[1]["dt"] == 0.5 and len(model) == 4)
    check("inserito in coda senza selezione", model.insert_after(None, {"angles": list(rest), "dt": 0.6}) == 4)

    print("6) File")
    path = os.path.join(tmp, "seq.json")
    model.save(store, path, "Prova", "LArm")
    data = json.load(open(path))
    check("salvata senza catena se nessun frame la spegne", data.get("arm_collision_chain") is None
          and data["format"] == "frames_v1" and len(data["frames"]) == 5)
    other = seq.SequenceModel(["HeadYaw"], ctrl.validate_frame_pose)
    loaded = other.load_file(path)
    check("ricaricata uguale", other.joints == joints and other.frames == model.frames and loaded["name"] == "Prova")
    with open(os.path.join(tmp, "ready.json"), "w") as handle:
        json.dump({"format": "ready_v1"}, handle)
    check("formato diverso rifiutato", isinstance(raises(seq.UnsupportedFormat, other.load_file,
                                                         os.path.join(tmp, "ready.json")), seq.UnsupportedFormat))
    with open(os.path.join(tmp, "rotto.json"), "w") as handle:
        json.dump({"format": "frames_v1", "joints": joints, "frames": [{"angles": [0.1], "dt": 0.6}]}, handle)
    exc = raises(seq.InvalidSequenceFile, other.load_file, os.path.join(tmp, "rotto.json"))
    check("file rotto rifiutato, sequenza invariata", isinstance(exc, seq.InvalidSequenceFile) and exc.problems
          and other.frames == model.frames)

    print("7) Coerenza della sequenza")
    check("sequenza valida", model.problems() == [])
    model.frames.append({"angles": [0.0], "dt": 0.6})
    check("frame incoerente segnalato", model.problems() != [])
    model.clear()
    check("svuotata (una sequenza vuota non e' salvabile)", len(model) == 0 and model.problems() == ["nessun frame"])

    ctrl.running = False
    shutil.rmtree(tmp, ignore_errors=True)
    print("ESITO: %s" % ("OK" if not FAILURES else "FALLITO (%d)" % len(FAILURES)))
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
