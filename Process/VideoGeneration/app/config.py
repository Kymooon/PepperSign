import os

def get_settings():
    output_dir_base = os.path.join(os.path.expanduser("~"), "PepperSignData")
    tmp_dir = os.path.join(output_dir_base, "tmp_try")

    return {
        "OUTPUT_DIR_BASE": output_dir_base,
        "TMP_DIR": tmp_dir,
        "ASSETS_DIR": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"),
        "TTL_SECONDS": int(os.environ.get("TRY_TTL_SECONDS", "900")),
        "DEFAULT_SCORE_THRESHOLD": float(os.environ.get("TRY_SCORE_THRESHOLD", "0.65")),
        "FFMPEG_BIN": os.environ.get("FFMPEG_BIN", "ffmpeg"),
        "GPU_CONCURRENCY": int(os.environ.get("GPU_CONCURRENCY", "1")),
        "ASR_CONCURRENCY": int(os.environ.get("ASR_CONCURRENCY", "1")),
        "PORT": int(os.environ.get("PEPPERSIGN_PORT", "5000")),
    }
