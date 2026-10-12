import os


def _env(name, default):
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def get_settings():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Cartella condivisa con la WebApp (video/immagini degli scheletri).
    # In Docker viene impostata a /data/media tramite PEPPERSIGN_DATA_DIR.
    output_dir_base = _env(
        "PEPPERSIGN_DATA_DIR",
        os.path.join(os.path.expanduser("~"), "PepperSignData"),
    )
    tmp_dir = _env("PEPPERSIGN_TMP_DIR", os.path.join(output_dir_base, "tmp_try"))

    return {
        "OUTPUT_DIR_BASE": output_dir_base,
        "TMP_DIR": tmp_dir,
        "ASSETS_DIR": _env("PEPPERSIGN_ASSETS_DIR", os.path.join(base_dir, "assets")),
        "TTL_SECONDS": int(_env("TRY_TTL_SECONDS", "900")),
        "DEFAULT_SCORE_THRESHOLD": float(_env("TRY_SCORE_THRESHOLD", "0.65")),
        "FFMPEG_BIN": _env("FFMPEG_BIN", "ffmpeg"),
        "GPU_CONCURRENCY": int(_env("GPU_CONCURRENCY", "1")),
        "ASR_CONCURRENCY": int(_env("ASR_CONCURRENCY", "1")),
        "PORT": int(_env("PEPPERSIGN_PORT", "5000")),
        "SPREADTHESIGN_BASE_URL": _env("SPREADTHESIGN_BASE_URL", "https://spreadthesign.com/it.it"),
        "MAX_REMOTE_VIDEO_MB": int(_env("MAX_REMOTE_VIDEO_MB", "300")),
    }
