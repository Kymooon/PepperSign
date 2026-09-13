import os
import re
import uuid
import unicodedata

from loguru import logger

from .ffmpeg_utils import ensure_wav_16k_mono


_PREFIX_PATTERNS = [
    r"^(?:ehi|ciao)\s+",
    r"^voglio\s+imparare\s+",
    r"^vorrei\s+imparare\s+",
    r"^mi\s+fai\s+vedere\s+",
    r"^fammi\s+vedere\s+",
    r"^mostrami\s+",
    r"^insegnami\s+",
    r"^come\s+si\s+fa\s+",
    r"^qual(?:e|’)?\s+è\s+",
    r"^il\s+segno\s+di\s+",
    r"^la\s+parola\s+",
    r"^segno\s+di\s+",
]

_STOPWORDS_START = {
    "il", "lo", "la", "l’", "l'", "un", "uno", "una",
    "del", "dello", "della", "dei", "degli", "delle", "di"
}

_ALLOWED_EXTENSIONS = {
    ".webm", ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".oga", ".aac"
}


def normalize_it(text):
    t = (text or "").strip().lower()
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[?!.,;:()\[\]{}\"“”]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_target_it(transcript):
    t = normalize_it(transcript)

    for pat in _PREFIX_PATTERNS:
        t = re.sub(pat, "", t).strip()

    parts = t.split()
    while parts and parts[0] in _STOPWORDS_START:
        parts = parts[1:]

    # massimo 3 token per gestire anche target composti
    return " ".join(parts[:3]).strip()


def init_asr():
    """
    Inizializza una sola volta il backend ASR.
    Prova nell'ordine:
    1) faster-whisper
    2) openai-whisper
    3) dummy fallback
    """
    try:
        from faster_whisper import WhisperModel
        import torch

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if dev == "cuda" else "int8"

        model = WhisperModel("base", device=dev, compute_type=compute)
        logger.info("[ASR] faster-whisper pronto (device={}, compute={})", dev, compute)

        return {
            "engine": "faster-whisper",
            "model": model
        }

    except Exception as e:
        logger.warning("[ASR] faster-whisper non disponibile: {}", e)

    try:
        import whisper

        model = whisper.load_model("base")
        logger.info("[ASR] openai-whisper pronto (model=base)")

        return {
            "engine": "openai-whisper",
            "model": model
        }

    except Exception as e:
        logger.warning("[ASR] openai-whisper non disponibile: {}", e)

    logger.warning("[ASR] uso dummy transcript")
    return {
        "engine": "dummy",
        "model": None
    }


def _safe_extension(filename):
    if not filename:
        return ".webm"

    _, ext = os.path.splitext(filename)
    ext = (ext or "").strip().lower()

    if ext in _ALLOWED_EXTENSIONS:
        return ext

    return ".webm"


def _safe_content_length(file_storage):
    try:
        pos = file_storage.stream.tell()
        file_storage.stream.seek(0, os.SEEK_END)
        size = file_storage.stream.tell()
        file_storage.stream.seek(pos)
        return size
    except Exception:
        return -1


def transcribe_file_storage(asr_ctx, asr_sem, ffmpeg_bin, output_dir_base, file_storage):
    """
    file_storage: request.files["audio"]
    ritorna: (transcript, engine)
    """
    if file_storage is None:
        raise ValueError("file_storage è None")

    if not ffmpeg_bin:
        raise ValueError("FFMPEG_BIN non configurato")

    if not output_dir_base:
        raise ValueError("OUTPUT_DIR_BASE non configurato")

    engine = asr_ctx["engine"]
    model = asr_ctx["model"]

    os.makedirs(output_dir_base, exist_ok=True)

    original_name = getattr(file_storage, "filename", None) or "audio.webm"
    original_ct = getattr(file_storage, "content_type", None)
    incoming_size = _safe_content_length(file_storage)
    ext = _safe_extension(original_name)

    tmp_input = os.path.join(output_dir_base, "_tmp_asr_{}{}".format(uuid.uuid4().hex, ext))
    tmp_wav = os.path.join(output_dir_base, "_tmp_asr_{}.wav".format(uuid.uuid4().hex))

    logger.info("[ASR] file ricevuto filename={!r} content_type={!r} stream_size={}",
                original_name, original_ct, incoming_size)
    logger.info("[ASR] tmp_input={}", tmp_input)
    logger.info("[ASR] tmp_wav={}", tmp_wav)

    transcript = ""
    used_engine = engine

    try:
        file_storage.save(tmp_input)

        saved_size = os.path.getsize(tmp_input) if os.path.exists(tmp_input) else -1
        logger.info("[ASR] file salvato size={} bytes", saved_size)

        if saved_size <= 0:
            raise ValueError("Il file audio ricevuto è vuoto o non è stato salvato correttamente.")

        logger.info("[ASR] avvio conversione ffmpeg")
        ensure_wav_16k_mono(ffmpeg_bin, tmp_input, tmp_wav)

        wav_size = os.path.getsize(tmp_wav) if os.path.exists(tmp_wav) else -1
        logger.info("[ASR] conversione completata wav_size={} bytes", wav_size)

        if wav_size <= 0:
            raise ValueError("La conversione WAV ha prodotto un file vuoto.")

        with asr_sem:
            logger.info("[ASR] avvio trascrizione engine={}", engine)

            if engine == "faster-whisper":
                segments, info = model.transcribe(
                    tmp_wav,
                    language="it",
                    beam_size=5,
                    vad_filter=True
                )
                transcript = " ".join([seg.text for seg in segments]).strip()
                logger.info("[ASR] faster-whisper completato language={}", getattr(info, "language", "it"))

            elif engine == "openai-whisper":
                result = model.transcribe(
                    tmp_wav,
                    language="it",
                    task="transcribe",
                    temperature=0
                )
                transcript = (result.get("text") or "").strip()
                logger.info("[ASR] openai-whisper completato")

            else:
                transcript = "voglio imparare ciao"
                used_engine = "dummy"
                logger.warning("[ASR] transcript dummy usato")

        logger.info("[ASR] transcript finale={!r}", transcript)

    except Exception as e:
        logger.exception("[ASR] errore in transcribe_file_storage: {}", e)
        raise

    finally:
        for path in (tmp_input, tmp_wav):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info("[ASR] file temporaneo rimosso: {}", path)
            except Exception as cleanup_err:
                logger.warning("[ASR] cleanup fallito per {}: {}", path, cleanup_err)

    return transcript, used_engine
