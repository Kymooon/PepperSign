"""
Frame di Pepper da coordinate (BETA): servizio per la GUI di Controll.

    GET  /retarget/landmarks  -> punti del corpo e direzioni disponibili
    POST /retarget/pose       -> calcola un frame (vedi retarget.pose.solve_request)

Il calcolo e' leggero (numpy, ~50 ms) e non usa DWPose ne' la GPU.
"""
from flask import Blueprint, jsonify, request
from loguru import logger

from retarget import landmarks as lm
from retarget import pose as pose_mod

bp = Blueprint("retarget_pose", __name__)


@bp.get("/retarget/landmarks")
def landmarks():
    return jsonify({"ok": True, "landmarks": lm.as_dicts(), "directions": lm.DIRECTION_CHOICES}), 200


@bp.post("/retarget/pose")
def pose():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "corpo JSON mancante"}), 400
    try:
        result = pose_mod.solve_request(payload)
    except (ValueError, KeyError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # errore inatteso: lo registro e lo restituisco alla GUI
        logger.exception("[RETARGET] errore /retarget/pose")
        return jsonify({"ok": False, "error": "errore interno: %s" % exc}), 500
    return jsonify(result), 200
