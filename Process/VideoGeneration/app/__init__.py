import os
import torch
from flask import Flask
from loguru import logger

from .config import get_settings
from .state import GPU_SEM, ASR_SEM, DETECTOR_LOCK
from threading import Semaphore

from easy_dwpose import DWposeDetector
from .services.asr_service import init_asr

from .routes.process import bp as process_bp
from .routes.try_gesture import bp as try_bp
from .routes.whisper import bp as whisper_bp
from .routes.health import bp as health_bp
from flask_cors import CORS

def create_app():



    app = Flask(__name__)
    CORS(app, resources={r"/*": {"origins": "*"}})
    cfg = get_settings()
    app.config["PSCFG"] = cfg

    # cartelle
    os.makedirs(cfg["OUTPUT_DIR_BASE"], exist_ok=True)
    os.makedirs(cfg["TMP_DIR"], exist_ok=True)

    # semafori
    app.extensions["gpu_sem"] = Semaphore(cfg["GPU_CONCURRENCY"])
    app.extensions["asr_sem"] = Semaphore(cfg["ASR_CONCURRENCY"])
    app.extensions["detector_lock"] = DETECTOR_LOCK

    # carica DWpose UNA volta
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logger.info(f"[APP] Carico DWposeDetector su {device}...")
    app.extensions["dwpose_detector"] = DWposeDetector(device=device)
    app.extensions["device"] = device
    logger.info("[APP] DWposeDetector pronto.")

    # carica ASR UNA volta
    app.extensions["asr_ctx"] = init_asr()

    # route (path identici)
    app.register_blueprint(process_bp)
    app.register_blueprint(try_bp)
    app.register_blueprint(whisper_bp)
    app.register_blueprint(health_bp)

    return app
