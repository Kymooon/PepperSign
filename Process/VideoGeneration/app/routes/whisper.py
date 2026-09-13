from flask import Blueprint, request, jsonify, current_app
from loguru import logger

from ..services.asr_service import extract_target_it, transcribe_file_storage


bp = Blueprint("whisper", __name__)


@bp.get("/transcribe/health")
def transcribe_health():
    cfg = current_app.config.get("PSCFG", {})
    asr_ctx = current_app.extensions.get("asr_ctx", {})

    return jsonify({
        "ok": True,
        "service": "asr",
        "engine": asr_ctx.get("engine"),
        "ffmpeg_bin": cfg.get("FFMPEG_BIN"),
        "output_dir_base": cfg.get("OUTPUT_DIR_BASE")
    })


@bp.post("/transcribe")
def transcribe():
    logger.info("[ASR] richiesta /transcribe ricevuta")

    if "audio" not in request.files:
        logger.warning("[ASR] request.files non contiene 'audio'")
        return jsonify({"error": "missing audio"}), 400

    try:
        cfg = current_app.config["PSCFG"]
        asr_ctx = current_app.extensions["asr_ctx"]
        asr_sem = current_app.extensions["asr_sem"]
    except KeyError as e:
        logger.exception("[ASR] configurazione applicativa mancante: {}", e)
        return jsonify({
            "error": "server configuration error",
            "details": str(e)
        }), 500

    audio = request.files["audio"]

    logger.info("[ASR] filename={!r} content_type={!r}",
                getattr(audio, "filename", None),
                getattr(audio, "content_type", None))
    logger.info("[ASR] FFMPEG_BIN={!r}", cfg.get("FFMPEG_BIN"))
    logger.info("[ASR] OUTPUT_DIR_BASE={!r}", cfg.get("OUTPUT_DIR_BASE"))

    try:
        transcript, used = transcribe_file_storage(
            asr_ctx=asr_ctx,
            asr_sem=asr_sem,
            ffmpeg_bin=cfg["FFMPEG_BIN"],
            output_dir_base=cfg["OUTPUT_DIR_BASE"],
            file_storage=audio
        )

        target = extract_target_it(transcript)

        logger.info("[ASR] target estratto={!r} engine={!r}", target, used)

        return jsonify({
            "transcript": transcript,
            "target": target,
            "engine": used
        }), 200

    except Exception as e:
        logger.exception("[ASR] errore in /transcribe: {}", e)
        return jsonify({
            "error": str(e),
            "type": e.__class__.__name__
        }), 500
