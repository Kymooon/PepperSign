# PepperSign — Modulo Process

Servizio **Flask** in Python 3 per l'elaborazione video e audio. La WebApp lo chiama sempre attraverso Tomcat: dal browser non è raggiungibile direttamente.

| Endpoint | Funzione |
|---|---|
| `POST /process` | dato il nome di un gesto, cerca il video sorgente in `assets/` (o lo scarica da SpreadTheSign), genera lo scheletro con **DWPose** e salva `<gesto>.mp4` + `.jpg` nella cartella dati |
| `POST /transcribe` | riconoscimento vocale con **Whisper** (faster-whisper) ed estrazione della parola richiesta |
| `POST /try`, `GET /try/status/<id>`, `GET /try/skeleton/<id>.mp4`, `DELETE /try/<id>` | "Prova gesto": scheletro del video dell'utente (job asincrono) e punteggio di similarità con il modello |
| `GET /health` | stato del servizio (modelli caricati, motore ASR) |

## Struttura

```
Process/VideoGeneration/
├── app/
│   ├── __init__.py          create_app(): carica DWPose e Whisper una sola volta
│   ├── config.py            configurazione da variabili d'ambiente
│   ├── state.py             job /try in memoria
│   ├── routes/              process.py, try_gesture.py, whisper.py, health.py
│   └── services/            dwpose_service.py, asr_service.py, ffmpeg_utils.py
├── assets/                  video sorgente locali (opzionali, es. acqua.mp4)
├── checkpoints/             modelli DWPose .onnx (scaricati da soli se mancano)
├── Dockerfile               immagine CPU (default) o GPU (vedi docker-compose.gpu.yml)
├── requirements.txt
├── run.py                   avvio senza Docker (server di sviluppo Flask)
└── control_panel.py         pannello Tkinter per avviare e monitorare il servizio senza Docker
```

## Avvio

**Con Docker (consigliato):** vedi [DOCKER.md](../DOCKER.md). Il servizio gira con gunicorn, 1 worker e più thread.

**Senza Docker** (Python 3.10+, FFmpeg nel PATH):

```
cd VideoGeneration
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install --no-deps easy-dwpose
pip install huggingface_hub matplotlib omegaconf onnxruntime
python run.py               (oppure: python control_panel.py)
```

Il servizio ascolta su `http://127.0.0.1:5000`. Va avviato prima della WebApp.

## Configurazione

| Variabile | Default | Descrizione |
|---|---|---|
| `PEPPERSIGN_DATA_DIR` | `~/PepperSignData` | cartella condivisa con la WebApp (video e immagini generati) |
| `PEPPERSIGN_ASSETS_DIR` | `assets/` | video sorgente locali |
| `PEPPERSIGN_PORT` | `5000` | porta HTTP |
| `ASR_MODEL` | `base` | modello Whisper (`tiny`, `base`, `small`, `medium`) |
| `TRY_SCORE_THRESHOLD` | `0.65` | soglia del punteggio "Prova gesto" |
| `TRY_TTL_SECONDS` | `900` | durata delle sessioni /try |
| `GPU_CONCURRENCY`, `ASR_CONCURRENCY` | `1` | job contemporanei |
| `FFMPEG_BIN` | `ffmpeg` | eseguibile FFmpeg |
