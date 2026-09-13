import os
import re
import uuid
import mimetypes
import unicodedata
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from flask import Blueprint, request, jsonify, current_app
from loguru import logger

from ..services.dwpose_service import process_to_skeleton


bp = Blueprint("process", __name__)

SPREADTHESIGN_BASE_URL = "https://spreadthesign.com/it.it"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
DEFAULT_MAX_REMOTE_VIDEO_MB = 300
REQUEST_TIMEOUT_SECONDS = 25


def _safe_slug(value):
    """
    Converte il nome del gesto in un nome file sicuro.
    Esempio:
    "Buon giorno!" -> "buon_giorno"
    """
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or "gesto"


def _extension_from_url_or_content_type(video_url, content_type=None):
    parsed = urlparse(video_url)
    ext = os.path.splitext(parsed.path)[1].lower()

    if ext in ALLOWED_VIDEO_EXTENSIONS:
        return ext

    if content_type:
        clean_content_type = content_type.split(";")[0].strip().lower()
        guessed_ext = mimetypes.guess_extension(clean_content_type)

        if guessed_ext in ALLOWED_VIDEO_EXTENSIONS:
            return guessed_ext

    return ".mp4"


def _build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    })
    return session


def _http_get_text(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _clean_found_url(raw_url, page_url):
    if not raw_url:
        return None

    cleaned = unescape(raw_url).replace("\\/", "/").strip()

    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned

    return urljoin(page_url, cleaned)


def _extract_video_url_from_html(html, page_url):
    """
    Cerca un URL video dentro l'HTML.
    È volutamente flessibile perché la struttura del sito può cambiare.
    """
    patterns = [
        r'(?:src|data-src|data-video|data-url)=["\']([^"\']+\.(?:mp4|mov|avi|mkv|webm)(?:\?[^"\']*)?)["\']',
        r'["\'](https?:\\?/\\?/[^"\']+\.(?:mp4|mov|avi|mkv|webm)(?:\?[^"\']*)?)["\']',
        r'["\']([^"\']+/[^"\']+\.(?:mp4|mov|avi|mkv|webm)(?:\?[^"\']*)?)["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _clean_found_url(match.group(1), page_url)

    return None


def _find_word_page_url(html, search_url, gesture_name):
    """
    Nella pagina di ricerca prova a trovare la scheda del gesto.
    In genere le schede hanno URL simili a:

    /it.it/word/<id>/<parola>/
    """
    links = re.findall(
        r'href=["\']([^"\']*/word/\d+/[^"\']*)["\']',
        html,
        flags=re.IGNORECASE
    )

    if not links:
        return None

    normalized_gesture = _safe_slug(gesture_name).replace("_", "-")
    absolute_links = []

    for link in links:
        absolute_url = _clean_found_url(link, search_url)

        if absolute_url and absolute_url not in absolute_links:
            absolute_links.append(absolute_url)

    # Preferisce il link che contiene la parola cercata nello slug URL.
    for absolute_url in absolute_links:
        parsed_path = urlparse(absolute_url).path.lower()

        if (
            normalized_gesture in parsed_path
            or normalized_gesture.replace("-", "_") in parsed_path
        ):
            return absolute_url

    # Se non riesce a distinguere, prende il primo risultato.
    return absolute_links[0]


def _download_spreadthesign_video(gesture_name, assets_dir, cfg):
    """
    Cerca il gesto su SpreadTheSign, trova il video e lo scarica
    come file temporaneo.

    Restituisce il percorso locale del video scaricato.
    """
    base_url = cfg.get("SPREADTHESIGN_BASE_URL", SPREADTHESIGN_BASE_URL).rstrip("/")
    max_remote_video_mb = int(
        cfg.get("MAX_REMOTE_VIDEO_MB", DEFAULT_MAX_REMOTE_VIDEO_MB)
    )
    max_bytes = max_remote_video_mb * 1024 * 1024

    session = _build_session()
    search_url = f"{base_url}/search/?q={quote_plus(gesture_name)}"

    logger.info(f"[SpreadTheSign] Ricerca gesto: {gesture_name} -> {search_url}")

    search_html = _http_get_text(session, search_url)

    # Alcuni risultati potrebbero avere già il video nella pagina di ricerca.
    video_url = _extract_video_url_from_html(search_html, search_url)

    if not video_url:
        word_page_url = _find_word_page_url(search_html, search_url, gesture_name)

        if not word_page_url:
            raise RuntimeError(
                f"Nessuna scheda trovata su SpreadTheSign per il gesto '{gesture_name}'."
            )

        logger.info(f"[SpreadTheSign] Scheda gesto trovata: {word_page_url}")

        word_html = _http_get_text(session, word_page_url)
        video_url = _extract_video_url_from_html(word_html, word_page_url)

    if not video_url:
        raise RuntimeError(
            f"Scheda trovata per '{gesture_name}', ma non sono riuscito a individuare "
            "il file video. La struttura della pagina SpreadTheSign potrebbe essere cambiata."
        )

    logger.info(f"[SpreadTheSign] Video trovato: {video_url}")

    tmp_dir = os.path.join(assets_dir, "_tmp_spreadthesign")
    os.makedirs(tmp_dir, exist_ok=True)

    with session.get(video_url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        ext = _extension_from_url_or_content_type(video_url, content_type)

        content_length = response.headers.get("Content-Length")

        if content_length and int(content_length) > max_bytes:
            raise RuntimeError(
                f"Il video remoto supera il limite massimo consentito di "
                f"{max_remote_video_mb} MB."
            )

        temp_filename = f"{_safe_slug(gesture_name)}_{uuid.uuid4().hex}{ext}"
        temp_path = os.path.join(tmp_dir, temp_filename)

        downloaded = 0

        with open(temp_path, "wb") as out_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                downloaded += len(chunk)

                if downloaded > max_bytes:
                    try:
                        out_file.close()
                        os.remove(temp_path)
                    except Exception:
                        pass

                    raise RuntimeError(
                        f"Il video remoto supera il limite massimo consentito di "
                        f"{max_remote_video_mb} MB."
                    )

                out_file.write(chunk)

    logger.info(f"[SpreadTheSign] Video scaricato temporaneamente: {temp_path}")

    return temp_path


def _find_local_source_video(assets_dir, gesture_name, gesture_slug):
    """
    Cerca un video sorgente già presente localmente nella cartella assets.

    Esempi cercati:
    - assets/ciao.mp4
    - assets/ciao.mov
    - assets/buon_giorno.mp4

    Il video locale NON viene eliminato dopo la generazione.
    """
    candidate_basenames = {
        gesture_name.strip(),
        gesture_slug,
    }

    for basename in candidate_basenames:
        root, ext = os.path.splitext(basename)

        # Caso: il client manda già "ciao.mp4".
        if ext.lower() in ALLOWED_VIDEO_EXTENSIONS:
            candidate = os.path.join(assets_dir, os.path.basename(basename))

            if os.path.exists(candidate):
                return candidate

        # Caso: il client manda "ciao".
        safe_base = _safe_slug(root or basename)

        for allowed_ext in ALLOWED_VIDEO_EXTENSIONS:
            candidate = os.path.join(assets_dir, safe_base + allowed_ext)

            if os.path.exists(candidate):
                return candidate

    return None


@bp.post("/process")
def process_video():
    cfg = current_app.config["PSCFG"]
    data = request.get_json(silent=True) or {}

    # Nuovo comportamento:
    # riceve il nome del gesto/parola.
    #
    # Esempio JSON:
    # {
    #   "gesture": "ciao"
    # }
    #
    # Accetto più chiavi per essere più flessibile lato frontend.
    gesture_name = (
        data.get("gesture")
        or data.get("gestureName")
        or data.get("word")
        or data.get("filename")  # fallback per compatibilità con il vecchio client
    )

    if not gesture_name:
        return jsonify({
            "error": "Nome gesto mancante nel JSON. Usa ad esempio: {\"gesture\": \"ciao\"}"
        }), 400

    gesture_name = str(gesture_name).strip()
    gesture_slug = _safe_slug(gesture_name)

    assets_dir = cfg["ASSETS_DIR"]
    output_base = cfg["OUTPUT_DIR_BASE"]

    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(output_base, exist_ok=True)

    output_video_path = os.path.join(output_base, f"{gesture_slug}.mp4")
    output_image_path = os.path.join(output_base, f"{gesture_slug}.jpg")

    # 1. Cache:
    # se lo skeleton esiste già, non rigenero nulla.
    if os.path.exists(output_video_path) and os.path.exists(output_image_path):
        return jsonify({
            "status": "success",
            "cached": True,
            "message": "Skeleton già presente localmente",
            "gesture": gesture_name,
            "video_path": output_video_path,
            "image_path": output_image_path,
            "stats": None
        }), 200

    downloaded_temp_path = None
    input_path = None

    try:
        # 2. Prima provo a usare un eventuale video sorgente già presente in assets.
        input_path = _find_local_source_video(
            assets_dir=assets_dir,
            gesture_name=gesture_name,
            gesture_slug=gesture_slug
        )

        # 3. Se il video sorgente non è locale, lo scarico temporaneamente da SpreadTheSign.
        if not input_path:
            downloaded_temp_path = _download_spreadthesign_video(
                gesture_name=gesture_name,
                assets_dir=assets_dir,
                cfg=cfg
            )

            input_path = downloaded_temp_path

        # 4. Genero lo skeleton.
        stats = process_to_skeleton(
            detector=current_app.extensions["dwpose_detector"],
            detector_lock=current_app.extensions["detector_lock"],
            gpu_sem=current_app.extensions["gpu_sem"],
            input_path=input_path,
            output_video_path=output_video_path,
            output_image_path=output_image_path
        )

        return jsonify({
            "status": "success",
            "cached": False,
            "message": "Generazione completata",
            "gesture": gesture_name,
            "source": "local" if downloaded_temp_path is None else "spreadthesign",
            "video_path": output_video_path,
            "image_path": output_image_path,
            "stats": stats
        }), 200

    except Exception as e:
        logger.exception(e)

        return jsonify({
            "status": "error",
            "gesture": gesture_name,
            "error": str(e)
        }), 500

    finally:
        # 5. Cancello solo il video scaricato temporaneamente.
        # Non cancello eventuali video presenti localmente in assets.
        if downloaded_temp_path and os.path.exists(downloaded_temp_path):
            try:
                os.remove(downloaded_temp_path)
                logger.info(
                    f"[SpreadTheSign] Video temporaneo eliminato: {downloaded_temp_path}"
                )
            except Exception as cleanup_error:
                logger.warning(
                    f"Impossibile eliminare il video temporaneo "
                    f"{downloaded_temp_path}: {cleanup_error}"
                )