# PepperSign — Report di sistema (v2)

*Aggiornato al 01/10/2026, dopo la containerizzazione con Docker. Sostituisce come riferimento il report del 30/09 (`PepperSign_Analisi_Codice.md`), che resta come storico.*

**Cosa ho riletto:** tutti i sorgenti attivi dei tre moduli, la configurazione Docker (Dockerfile, compose, Caddy, supervisord, script) e l'inventario completo della cartella. Ho escluso `.git`, `target/`, gli ambienti virtuali `.venv/` e i modelli `.onnx`. Ho anche controllato quali file sono tracciati da Git (84 file sul branch `main`, remote `github.com/Kymooon/PepperSign`).

---

## 1. Sintesi

| Aspetto | Stato |
|---|---|
| Avvio portabile con Docker (4 container) | ✅ funzionante e verificato sul PC (Web, Process CPU, Controll, HTTPS) |
| Modalità demo senza robot | ✅ funzionante (GUI via browser, comandi simulati) |
| Configurazione | ✅ centralizzata in `.env` e variabili d'ambiente, niente più IP o percorsi fissi nel codice |
| Repository Git | ✅ pulita: nessun file pesante o locale tracciato |
| Problemi funzionali del primo report (C1–C4) | ⚠️ ancora aperti: non li ho toccati, lo scopo era la portabilità |
| Ordine della cartella | ✅ riordinata il 01/10/2026 (azioni R1–R8, vedi §5) |

---

## 2. Architettura attuale

```
                     ┌────────────── Tablet Pepper / PC / smartphone ──────────────┐
                     │  https://<IP-PC>:8443/PepperSign/      http://localhost:6080 │
                     └───────────────┬─────────────────────────────────┬───────────┘
                                     │ HTTPS                           │ noVNC (browser)
┌────────────────────────── Docker (rete interna peppersign_default) ──┼─────────────────┐
│  ┌──────────┐   ┌──────────────────────┐  HTTP  ┌─────────────────┐  │                 │
│  │  caddy   │──►│ web  (Tomcat 10.1)   │───────►│ process (Flask) │  │                 │
│  │  :8443   │   │ /PepperSign  :8080   │        │ gunicorn :5000  │  │                 │
│  │ tls int. │   │ servlet + JSP + JS   │        │ DWPose·Whisper  │  │                 │
│  └──────────┘   │ PepperCommandBus     │        └───────┬─────────┘  │                 │
│                 └──────────▲───────────┘                │            │                 │
│                            │ polling /api/pepper/next   │            │                 │
│                 ┌──────────┴──────────────────────────┐ │            │                 │
│                 │ controll (Ubuntu 18.04, Python 2.7) │◄┼────────────┘                 │
│                 │ GUI Tkinter su Xvfb + x11vnc + noVNC│ │                              │
│                 │ NAOqi SDK 2.8.7.4  │  fake_qi (demo)│ │                              │
│                 └──────────┬──────────────────────────┘ │                              │
└────────────────────────────┼────────────────────────────┼──────────────────────────────┘
                             │ NAOqi tcp:9559              │ volumi
                       Robot Pepper           data/media · data/gestures · checkpoints · model-cache
```

### Container

| Servizio | Immagine / base | Porta sul PC | Ruolo |
|---|---|---|---|
| `caddy` | `caddy:2-alpine` | 8443 | HTTPS con CA interna, inoltra tutto a `web` |
| `web` | build Maven → `tomcat:10.1-jdk17` | 8080 | WebApp su `/PepperSign`, API `/api/*`, coda comandi |
| `process` | `python:3.10-slim` (CPU) / `nvidia/cuda:12.4.1` (GPU) | solo interna | Generazione scheletri, ASR, "Prova gesto" |
| `controll` | `ubuntu:18.04` + Python 2.7 + SDK NAOqi Linux | 6080 | GUI del robot, polling comandi, registrazione gesti |

### Flussi principali (invariati rispetto al primo report)
1. **Richiesta vocale (PC/tablet):** microfono → `/api/asr` → Whisper → parola → `/api/lesson` → se manca, `/process` genera lo scheletro.
2. **Catalogo:** `/api/media` + `/media/*` leggono `data/media`.
3. **Prova gesto:** webcam → `/api/try` → job asincrono DWPose → punteggio di similarità.
4. **Esegui gesto su Pepper:** `/api/pepper/say` + `/gesture` → coda → Controll (`/api/pepper/next`) → `angleInterpolation`.
5. **Registrazione gesti:** GUI → Dump Pose → validazione → JSON in `data/gestures`.

### Configurazione (`.env`)

| Variabile | Uso |
|---|---|
| `PEPPER_IP`, `PEPPER_PORT` | robot reale |
| `PEPPERSIGN_FAKE_ROBOT` | `1` = demo con robot simulato, `0` = robot reale |
| `PEPPERSIGN_HOST` | IP del PC per il certificato (lo script di avvio lo rileva da solo) |
| `PEPPERSIGN_MEDIA_DIR`, `PEPPERSIGN_GESTURES_DIR` | cartelle dati sul PC |
| `ASR_MODEL`, `TRY_*`, `GPU_/ASR_CONCURRENCY` | parametri del servizio Process |
| `CONTROLL_SCREEN`, `CONTROLL_WINDOW_SIZE`, `VNC_PASSWORD` | GUI via browser |

Avvio: `avvia-peppersign.bat`. Opzioni: `-Build` dopo modifiche al codice, `-Services web,process,caddy` per avviare senza robot, `-Ip x.x.x.x` per indicare l'IP a mano.

---

## 3. Modifiche fatte dal primo report

| Area | Modifica |
|---|---|
| Web | `AppConfig.java` (URL Process e cartella dati da variabili d'ambiente); servlet senza `127.0.0.1:5000`/`~/PepperSignData` fissi; rimossa la mappatura `C:\multimedia_data` da `context.xml`; messaggio `:5001` corretto |
| Process | `config.py` da variabili d'ambiente; `ASR_MODEL` configurabile; `requirements.txt` corretto; Dockerfile con aggiornamento di pip ed easy-dwpose installato senza `onnxruntime-gpu==1.16.2`; gunicorn al posto del server di sviluppo di Flask |
| Controll | niente percorsi `C:\Python27` né IP fissi; caricamento automatico di `config.local.json`; variabili d'ambiente (IP, URL, cartelle, dimensioni finestra); attesa del robot all'avvio; **modalità demo** (`fake_qi.py`) |
| Infrastruttura | 3 Dockerfile, `docker-compose.yml` + variante GPU, Caddyfile HTTPS, supervisord, script `avvia-peppersign.ps1/.bat`, `.env.example`, `DOCKER.md` |

---

## 4. Stato dei problemi

### Dal primo report

| # | Problema | Stato | Note |
|---|---|---|---|
| C1 | Flusso "microfono di Pepper" incompleto (`/api/pepper/start`, `/status`, `/audio` mancanti; `SAY_AND_LISTEN` non serializzato) | 🔴 Aperto | invariato |
| C2 | `#asrText` e toggle PC/Pepper assenti in `index.jsp`: nessun feedback di stato | 🔴 Aperto | invariato |
| C3 | Parole composte o accentate rifiutate, ID gesto normalizzati in modo diverso nei 3 moduli | 🔴 Aperto | invariato |
| C4 | Metrica di similarità (IoU di pixel, nessun allineamento temporale) | 🔴 Aperto | tema centrale per la tesi |
| I1 | GUI Tkinter bloccata durante i gesti (lock sul thread UI) | 🟠 Aperto | visibile anche in demo |
| I2 | `/process` sincrono (Tomcat attende fino a 10 min) | 🟠 Aperto | |
| I3 | Configurazione fissa nel codice e duplicata | ✅ Risolto | `.env` + `AppConfig` + variabili d'ambiente |
| I4 | Lista dei gesti animabili fissa in Java e diversa dai JSON reali | 🟠 Aperto | `data/gestures` è vuota: vanno copiati i JSON |
| I5 | Polling ogni 0,2–0,3 s | 🟡 Aperto | possibile long-polling |
| I6 | TTL dei job `/try`, cache `/process` non atomica | 🟠 Parziale | dipendenze sistemate; TTL e cache invariati |
| Sic. | Nessuna autenticazione, GET che cambiano stato, CORS `*` | 🟡 Parziale | Flask non è più esposto in rete e gira con gunicorn |
| Pul. | `script_modular_bundle.js` inutilizzato, `old-version/`, nessun test | 🟡 Parziale | codice morto archiviato (§5); test ancora assenti |

### Nuove osservazioni (Docker e infrastruttura)

1. **GUI via browser senza password:** la porta 6080 è raggiungibile da tutta la rete locale e con `VNC_PASSWORD` vuota chiunque può comandare il robot. Conviene impostare una password o pubblicare la porta solo su `127.0.0.1`.
2. **Fine riga:** senza un `.gitattributes`, su un altro PC Windows Git può convertire in CRLF file usati dentro i container Linux (`supervisord.conf`, `Caddyfile`, `.sh`). Gli script `.sh` sono già protetti nel Dockerfile, gli altri no.
3. **Basi software datate (scelta obbligata):** Python 2.7 e Ubuntu 18.04 sono a fine vita, ma sono necessari per l'SDK NAOqi. È un vincolo da citare nella tesi: il container lo isola dal resto del sistema.
4. **easy-dwpose con onnxruntime recente:** ha funzionato al primo avvio (`DWposeDetector pronto`), ma la combinazione non è quella dichiarata dalla libreria. Conviene fissare le versioni (`requirements.lock`) una volta verificata la generazione completa.
5. **Immagine Process pesante** (alcuni GB, per torch, OpenCV e Whisper). La prima build richiede tempo e spazio; la variante GPU non è ancora stata provata.
6. **Editor che sovrascrive i file:** due volte le modifiche fatte da fuori sono state annullate dall'IDE aperto. Va attivata la sincronizzazione dei file esterni.
7. **Documentazione:** `DOCKER.md` e i README di modulo erano incompleti o obsoleti. Sono stati aggiornati con il riordino (§5).
8. **`config.example.json`** usava l'URL `PepperSign_Web_war_exploded` del vecchio setup IntelliJ: aggiornato a `/PepperSign` (§5).

---

## 5. Stato della cartella e riordino

> **Riordino applicato il 01/10/2026** (azioni R1–R8 approvate). Eliminati gli 11 file vuoti, i `.pyc`, la cartella `Controll/packages` e i file vuoti `persistence.xml`/`beans.xml`. Spostati in `_archivio/` (ignorato da Git) `old-version`, `snapshots`, `Controll/README.txt`, il vecchio `Caddyfile`, `single_dwpose.py` e `script_modular_bundle.js`. Aggiunti `README.md` nella radice, i README di Controll e Process riscritti, `DOCKER.md` e `config.example.json` aggiornati, `docs/` con i report e `.gitattributes`. Le tabelle qui sotto descrivono la situazione **prima** del riordino.


### Cosa c'è oggi

| Elemento | Dimensione | In Git? | Valutazione |
|---|---|---|---|
| 11 file vuoti nella radice (`[3`, `[process`, `[web`, `[web]`, `0.8.5`, `2.5.1`, `4.10.0`, `77.0.3`, `CACHED`, `ERROR`, `See`) | 0 B | no | spazzatura: creati incollando log nel prompt dei comandi |
| `Controll/peppersign/*.pyc` (9 file) | ~100 KB | no | compilati Python 2, alcuni più vecchi dei sorgenti |
| `Controll/old-version/` (prova*.py, pepper_interactive_test.py) | 75 KB | no | codice storico |
| `Controll/snapshots/*.ppm` | 0,7 MB | no | foto di prova delle telecamere |
| `Controll/packages/` | vuota | no | inutile |
| `Controll/README.md` ("Progetto-Tirocinio"), `Controll/README.txt` | — | sì | obsoleti |
| `Controll/.venv/`, `Process/.venv/` | ~390 MB | no | ambienti virtuali locali: non servono con Docker, utili solo per l'avvio senza Docker |
| `.idea/` in Controll, Process, Process/VideoGeneration, Web (+ `shelf/` con patch vecchie) | ~120 KB | no | configurazioni IntelliJ/PyCharm |
| `Process/README.md` (cita uno script `generate_media` che non esiste) | — | sì | obsoleto |
| `Process/VideoGeneration/Caddyfile` | — | sì | sostituito da `docker/caddy/Caddyfile` |
| `Process/VideoGeneration/single_dwpose.py` | 1 KB | sì | script di prova (usa `ciao2.jpeg`, che non c'è) |
| `Process/VideoGeneration/control_panel.py`, `run.py` | 13 KB | sì | servono solo per l'avvio senza Docker |
| `checkpoints/Inserire-qui-onnx` | 0 B | sì | segnaposto: utile tenerlo, meglio come README |
| `Web/PepperWebApp/src/main/webapp/js/script_modular_bundle.js` | 34 KB | sì | codice morto, duplicato dei moduli `ps-*.js` |
| `Web/PepperWebApp/target/` | — | no | output di build, rigenerabile |
| `persistence.xml`, `beans.xml` vuoti | — | sì | inutilizzati |
| Nessun README nella radice | — | — | manca un punto d'ingresso per chi apre la repo |

### Struttura proposta

```
PepperSign/
├── README.md                  ← NUOVO: cos'è, architettura, avvio rapido, link alla documentazione
├── DOCKER.md                  ← aggiornato (script, correzioni build, GUI)
├── .env.example  .gitignore  .gitattributes (NUOVO)
├── docker-compose.yml  docker-compose.gpu.yml
├── avvia-peppersign.bat  avvia-peppersign.ps1
├── docker/caddy/Caddyfile
├── docs/                      ← NUOVO: report di analisi, report di sistema, note per la tesi
├── data/                      ← dati runtime (ignorato da Git)
├── Controll/
│   ├── README.md              ← riscritto (struttura modulo, avvio con e senza Docker, modalità demo)
│   ├── Dockerfile  .dockerignore  main.py  config.example.json
│   ├── docker/  (supervisord.conf, *.sh, sdk/)
│   └── peppersign/  (solo .py)
├── Process/
│   ├── README.md              ← riscritto
│   └── VideoGeneration/  (app/, assets/, checkpoints/, Dockerfile, requirements.txt, run.py, control_panel.py)
├── Web/
│   └── PepperWebApp/  (src/, pom.xml, Dockerfile, mvnw)
└── _archivio/                 ← NUOVO, ignorato da Git: old-version, snapshots, single_dwpose.py, vecchio Caddyfile
```

### Azioni proposte (ognuna richiede la tua autorizzazione)

| # | Azione | Tipo |
|---|---|---|
| R1 | Eliminare gli 11 file vuoti nella radice | eliminazione |
| R2 | Eliminare i `.pyc` in `Controll/peppersign` e la cartella vuota `Controll/packages` | eliminazione |
| R3 | Spostare in `_archivio/` (ignorato da Git): `Controll/old-version`, `Controll/snapshots`, `Process/VideoGeneration/Caddyfile`, `single_dwpose.py` | spostamento |
| R4 | Rimuovere `script_modular_bundle.js` (o archiviarlo) e i `persistence.xml`/`beans.xml` vuoti | eliminazione / spostamento |
| R5 | Creare `README.md` nella radice e riscrivere i README di Controll e Process | documentazione |
| R6 | Aggiornare `DOCKER.md` e `config.example.json` | documentazione / config |
| R7 | Aggiungere `.gitattributes` (LF per Dockerfile, `.sh`, `.conf`, `Caddyfile`, `.yml`) e `_archivio/` al `.gitignore` | config Git |
| R8 | Creare `docs/` con i due report | documentazione |

`.idea/`, `.venv/` e `target/` li lascerei dove sono: sono già ignorati da Git e servono all'IDE e all'avvio senza Docker.

---

## 6. Prossimi passi consigliati

1. **Commit e push** del riordino, poi prova di clonazione su un altro PC.
2. **Dati:** copiare i JSON dei gesti in `data/gestures` e verificare "Esegui gesto" in demo e sul robot reale.
3. **Correzioni funzionali rapide:** C2 (feedback in `index.jsp`) e C3 (normalizzazione unica degli ID).
4. **Robustezza:** I1 (GUI non bloccante), I2 (`/process` asincrono), password per noVNC.
5. **Contributo della tesi:** nuova metrica di similarità (keypoint DWPose + DTW) e test automatici.
