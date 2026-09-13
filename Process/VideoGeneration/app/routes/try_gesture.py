import os, time, uuid, json, shutil
from threading import Thread
from flask import Blueprint, request, jsonify, send_file, current_app
from loguru import logger

from ..state import JOBS, JOBS_LOCK
from ..services.ffmpeg_utils import ffmpeg_convert_to_mp4
from ..services.dwpose_service import process_to_skeleton, compute_similarity_percent

bp = Blueprint("try_gesture", __name__)

def _cleanup_session(sid: str):
    with JOBS_LOCK:
        job = JOBS.pop(sid, None)
    if not job:
        return
    job_dir = job.get("paths", {}).get("job_dir")
    if job_dir and os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=True)

def _is_expired(job, ttl_seconds: int) -> bool:
    last = job.get("lastTouch", job.get("createdAt", time.time()))
    return (time.time() - last) > ttl_seconds

def _touch_job(sid: str):
    with JOBS_LOCK:
        job = JOBS.get(sid)
        if job:
            job["lastTouch"] = time.time()

def _start_ttl_guard(sid: str, ttl_seconds: int):
    def _guard():
        time.sleep(ttl_seconds + 1)
        with JOBS_LOCK:
            job = JOBS.get(sid)
        if not job:
            return
        if job.get("status") in ("queued", "running"):
            return
        if _is_expired(job, ttl_seconds):
            logger.info(f"[TRY] TTL scaduto, cleanup sessione {sid}")
            _cleanup_session(sid)
    Thread(target=_guard, daemon=True).start()

def _run_try_job(sid: str):
    cfg = current_app.config["PSCFG"]
    output_base = cfg["OUTPUT_DIR_BASE"]
    threshold = cfg["DEFAULT_SCORE_THRESHOLD"]
    ffmpeg_bin = cfg["FFMPEG_BIN"]

    with JOBS_LOCK:
        job = JOBS.get(sid)
        if not job:
            return
        job["status"] = "running"

    try:
        gesture_id = job["gestureId"]
        job_dir = job["paths"]["job_dir"]

        input_webm = os.path.join(job_dir, "input.webm")
        input_mp4  = os.path.join(job_dir, "input.mp4")
        skeleton_mp4 = os.path.join(job_dir, "skeleton.mp4")
        thumb_jpg    = os.path.join(job_dir, "thumb.jpg")
        result_json  = os.path.join(job_dir, "result.json")

        ffmpeg_convert_to_mp4(ffmpeg_bin, input_webm, input_mp4)

        stats = process_to_skeleton(
            detector=current_app.extensions["dwpose_detector"],
            detector_lock=current_app.extensions["detector_lock"],
            gpu_sem=current_app.extensions["gpu_sem"],
            input_path=input_mp4,
            output_video_path=skeleton_mp4,
            output_image_path=thumb_jpg
        )

        template_mp4 = os.path.join(output_base, f"{gesture_id}.mp4")
        if not os.path.exists(template_mp4):
            raise FileNotFoundError(
                f"Template skeleton non trovato: {template_mp4}. "
                f"Assicurati che esista già in PepperSignData con nome '{gesture_id}.mp4'"
            )

        score, percent = compute_similarity_percent(template_mp4, skeleton_mp4)
        ok = score >= threshold

        feedback = ["Buona esecuzione! Coerenza soddisfacente."] if ok else [
            "Prova a rallentare e mantenere la posa più stabile."
        ]

        result = {
            "sessionId": sid,
            "gestureId": gesture_id,
            "status": "done",
            "score": score,
            "percent": percent,
            "ok": ok,
            "threshold": threshold,
            "feedback": feedback,
            "stats": stats,
            "paths": {
                "skeleton_mp4": skeleton_mp4,
                "thumb_jpg": thumb_jpg
            }
        }

        with open(result_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        with JOBS_LOCK:
            job = JOBS.get(sid)
            if job:
                job["status"] = "done"
                job["result"] = result
                job["lastTouch"] = time.time()

    except Exception as e:
        logger.error(f"[TRY] Errore sessione {sid}: {e}")
        with JOBS_LOCK:
            job = JOBS.get(sid)
            if job:
                job["status"] = "error"
                job["error"] = str(e)
                job["lastTouch"] = time.time()

@bp.post("/try")
def start_try():
    cfg = current_app.config["PSCFG"]
    ttl_seconds = cfg["TTL_SECONDS"]
    tmp_dir = cfg["TMP_DIR"]

    if "video" not in request.files:
        return jsonify({"error": "File video mancante (campo 'video')"}), 400

    gesture_id = request.form.get("gestureId", "").strip()
    if not gesture_id:
        return jsonify({"error": "gestureId mancante"}), 400

    sid = uuid.uuid4().hex
    job_dir = os.path.join(tmp_dir, sid)
    os.makedirs(job_dir, exist_ok=True)

    input_webm = os.path.join(job_dir, "input.webm")
    request.files["video"].save(input_webm)

    with JOBS_LOCK:
        JOBS[sid] = {
            "sessionId": sid,
            "gestureId": gesture_id,
            "status": "queued",
            "createdAt": time.time(),
            "lastTouch": time.time(),
            "paths": {"job_dir": job_dir}
        }

    _start_ttl_guard(sid, ttl_seconds)

    # Thread: serve current_app, quindi usiamo app_context
    app_obj = current_app._get_current_object()
    def runner():
        with app_obj.app_context():
            _run_try_job(sid)

    Thread(target=runner, daemon=True).start()
    return jsonify({"sessionId": sid, "status": "queued"}), 202

@bp.get("/try/status/<sid>")
def try_status(sid):
    cfg = current_app.config["PSCFG"]
    ttl_seconds = cfg["TTL_SECONDS"]
    _touch_job(sid)

    with JOBS_LOCK:
        job = JOBS.get(sid)
    if not job:
        return jsonify({"error": "sessionId non trovato"}), 404

    if job.get("status") not in ("queued", "running") and _is_expired(job, ttl_seconds):
        _cleanup_session(sid)
        return jsonify({"error": "sessione scaduta"}), 410

    resp = {"sessionId": sid, "status": job["status"], "gestureId": job.get("gestureId")}
    if job["status"] == "done":
        resp["result"] = job.get("result", {})
    if job["status"] == "error":
        resp["error"] = job.get("error", "unknown error")
    return jsonify(resp), 200

@bp.get("/try/skeleton/<sid>.mp4")
def get_try_skeleton(sid):
    cfg = current_app.config["PSCFG"]
    ttl_seconds = cfg["TTL_SECONDS"]
    _touch_job(sid)

    with JOBS_LOCK:
        job = JOBS.get(sid)
    if not job:
        return jsonify({"error": "sessionId non trovato"}), 404

    if job.get("status") not in ("queued", "running") and _is_expired(job, ttl_seconds):
        _cleanup_session(sid)
        return jsonify({"error": "sessione scaduta"}), 410

    if job["status"] != "done":
        return jsonify({"error": "skeleton non pronto"}), 409

    path = job["result"]["paths"]["skeleton_mp4"]
    if not os.path.exists(path):
        return jsonify({"error": "file mancante"}), 404

    resp = send_file(path, mimetype="video/mp4", as_attachment=False)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@bp.delete("/try/<sid>")
def delete_try(sid):
    with JOBS_LOCK:
        exists = sid in JOBS
    if not exists:
        return jsonify({"status": "already_deleted"}), 200
    _cleanup_session(sid)
    return jsonify({"status": "deleted"}), 200
