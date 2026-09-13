from flask import Blueprint, jsonify, current_app
from ..state import JOBS, JOBS_LOCK

bp = Blueprint("health", __name__)

@bp.get("/health")
def health():
    with JOBS_LOCK:
        n = len(JOBS)

    asr_engine = current_app.extensions.get("asr_ctx", {}).get("engine", "unknown")
    device = current_app.extensions.get("device", "unknown")

    return jsonify({
        "ok": True,
        "device": device,
        "dwpose_loaded": True,
        "asr_engine": asr_engine,
        "try_sessions": n
    }), 200
