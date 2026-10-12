# PepperSign con Docker

Con Docker l'intero sistema (WebApp, servizio Python di elaborazione, controller del robot e proxy HTTPS) si avvia su qualunque PC con un solo comando, senza installare Java, Tomcat, Python 3, Python 2.7, FFmpeg o l'SDK NAOqi.

## Architettura dei container

| Container | Contenuto | Porta sul PC |
|---|---|---|
| `caddy` | Proxy HTTPS (serve per microfono e webcam sul tablet) | **8443** |
| `web` | Tomcat 10.1 + Java 17, WebApp su `/PepperSign` | 8080 |
| `process` | Flask + DWPose + Whisper + FFmpeg (CPU o GPU) | interna (5000) |
| `controll` | Python 2.7 + NAOqi + GUI Tkinter, visibile nel browser | **6080** |

```
 Tablet Pepper / PC ──HTTPS:8443──► caddy ──► web:8080 ──► process:5000
                                               ▲
 Browser ──HTTP:6080──► controll (GUI noVNC) ──┘ polling /api/pepper/next
                          │
                          └──NAOqi tcp:9559──► Robot Pepper
```

I dati restano sul PC, nelle cartelle montate come volumi:

| Cartella sul PC | Contenuto | Usata da |
|---|---|---|
| `data/media` | video e immagini degli scheletri | web, process |
| `data/gestures` | gesture JSON registrate | controll |
| `Process/VideoGeneration/checkpoints` | modelli DWPose `.onnx` | process |
| `Process/VideoGeneration/assets` | video sorgente locali | process |

## Requisiti

- **Docker Desktop** (Windows/macOS) con backend WSL2, oppure Docker Engine con il plugin Compose (Linux).
- Solo per la GPU: scheda NVIDIA con driver aggiornati (Windows) oppure NVIDIA Container Toolkit (Linux).
- **SDK NAOqi Python 2.7 per Linux 64 bit**: vedi [Controll/docker/sdk/README.md](Controll/docker/sdk/README.md).

## Primo avvio

1. **SDK NAOqi**: copia `pynaoqi-python2.7-<versione>-linux64-<data>.tar.gz` (in uso: 2.8.7.4) in `Controll/docker/sdk/`, senza estrarlo e senza prefissi nel nome.
2. **Modelli DWPose** (opzionale): se hai già `yolox_l.onnx` e `dw-ll_ucoco_384.onnx`, lasciali in `Process/VideoGeneration/checkpoints/`. Se mancano, vengono scaricati automaticamente al primo avvio (~350 MB).
3. **Configurazione**: copia `.env.example` in `.env` e imposta almeno:
   - `PEPPER_IP`: IP del robot;
   - `PEPPERSIGN_HOST`: IP di questo PC visto dal tablet (con l'hotspot di Windows di solito `192.168.137.1`). Con lo script di avvio non serve: lo rileva da solo;
   - `PEPPERSIGN_FAKE_ROBOT=1` se vuoi partire in modalità demo, senza robot.
4. **Avvio** su Windows, dalla cartella principale del progetto:

   ```
   avvia-peppersign.bat -Build
   ```

   Lo script controlla Docker, rileva l'IP del PC (hotspot di Windows se attivo, altrimenti la scheda di rete con gateway), lo passa a Caddy e avvia i container. Opzioni:

   | Opzione | Uso |
   |---|---|
   | *(nessuna)* | avvio normale (doppio clic sul `.bat`) |
   | `-Build` | ricostruisce le immagini, da usare dopo modifiche al codice |
   | `-Services web,process,caddy` | avvia solo alcuni servizi (es. senza Controll) |
   | `-Ip 192.168.0.50` | usa questo IP invece di quello rilevato |

   In alternativa, o su Linux/macOS, con Docker Compose:

   ```bash
   # CPU (funziona ovunque)
   docker compose up -d --build

   # oppure GPU NVIDIA
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
   ```

   La prima build richiede parecchi minuti (scarica torch, i modelli e le immagini base). Le successive sono molto più rapide.

5. **Apri**:
   - WebApp dal tablet o da un altro dispositivo: `https://<PEPPERSIGN_HOST>:8443/PepperSign/`
   - WebApp dal PC stesso: `http://localhost:8080/PepperSign/`
   - GUI del controller: `http://localhost:6080` → *Connect*

> **Certificato HTTPS**: il certificato è emesso dalla CA interna di Caddy, quindi al primo accesso il browser mostra un avviso che va accettato (come con il Caddyfile che usavi prima). Per eliminarlo si può installare sul dispositivo la CA radice, esportata con:
> `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./peppersign-root.crt`

## Modalità demo senza robot

Per provare tutto il sistema senza Pepper (sviluppo, prove della GUI, demo della tesi), nel file `.env` imposta:

```ini
PEPPERSIGN_FAKE_ROBOT=1
```

e riavvia il controller con `docker compose up -d controll`, oppure con `avvia-peppersign.bat`.

Il controller usa un **robot simulato** (`Controll/peppersign/fake_qi.py`) al posto dell'SDK NAOqi:

- la GUI su `http://localhost:6080` si apre subito e il titolo riporta *[DEMO - robot simulato]*;
- ogni comando che arriva dalla WebApp (SAY, ANIMATED_SAY, PLAY_GESTURE…) e ogni azione dalla GUI compare nel log come `[DEMO] ALMotion.angleInterpolation(...)`, `[DEMO] ALTextToSpeech.say(...)`;
- la posa dei giunti è tenuta in memoria con i limiti reali di Pepper: *Dump Pose*, validazione, *Test* ed export dei gesti funzionano;
- i tempi di parlato e movimento sono simulati (al massimo 8 secondi per azione).

Non può simulare il movimento fisico delle braccia: con *Free Arms* la posa resta quella corrente, ma puoi modificarla con l'editor dei frame. Per tornare al robot reale imposta `PEPPERSIGN_FAKE_ROBOT=0`.

Senza Docker: `set PEPPERSIGN_FAKE_ROBOT=1` e poi `python main.py`. In questa modalità non serve nemmeno l'SDK NAOqi.

## Riusare i dati già presenti sul tuo PC

Nel file `.env`:

```ini
PEPPERSIGN_MEDIA_DIR=C:/Users/Universita/PepperSignData
PEPPERSIGN_GESTURES_DIR=C:/Users/Universita/PepperSignGestures
```

## Autonomous Life durante i gesti

Autonomous Life può restare **attiva**: Pepper sbatte le palpebre, segue le persone con lo sguardo e "respira". Durante l'esecuzione di un gesto, sia `PLAY_GESTURE` dalla WebApp sia *Test* dalla GUI, il controller mette in pausa solo i movimenti autonomi che interferirebbero. Subito dopo il gesto ripristina **esattamente** lo stato precedente, anche in caso di errore. Il comportamento si sceglie con `PEPPERSIGN_GESTURE_AUTONOMY` nel `.env`:

| Valore | Durante il gesto |
|---|---|
| `pause` (default) | in pausa respiro e postura di riposo delle braccia, BackgroundMovement, ListeningMovement e SpeakingMovement. BasicAwareness resta attiva ma segue le persone **solo con la testa**, senza ruotare la base; se il gesto usa i giunti della testa va in pausa anche lei |
| `off` | in pausa tutti i movimenti autonomi (anche blink e awareness) e il respiro di tutto il corpo. Lo stato di Autonomous Life non viene cambiato |
| `none` | nessun intervento (comportamento precedente) |

Nel log della GUI compaiono le righe `[AUTONOMY] Pausa per il gesto (...)` e `[AUTONOMY] Movimenti autonomi ripristinati`. Viene toccato solo ciò che è attivo: con *Life OFF* non viene riacceso niente. Le API usate (`ALAutonomousLife.setAutonomousAbilityEnabled`, `ALMotion.setBreathEnabled`, `ALBasicAwareness.setTrackingMode`) sono quelle documentate per NAOqi 2.5/2.8. Ogni chiamata è protetta, quindi se una non è disponibile il gesto parte comunque.

## GUI del controller nel browser (noVNC)

Il desktop virtuale del container è di 1920×1080 e la finestra della GUI di 1900×1040, così si vedono tutte e tre le colonne, log compreso. Le dimensioni si cambiano nel `.env` con `CONTROLL_SCREEN` e `CONTROLL_WINDOW_SIZE`. Se lo schermo del PC è più piccolo, in noVNC apri il pannello laterale → ⚙ *Impostazioni* → *Modalità di ridimensionamento: Ridimensionamento locale*.

Con `VNC_PASSWORD` vuota chiunque sulla rete locale può aprire la GUI sulla porta 6080 e comandare il robot: in laboratorio conviene impostare una password.

## Comandi utili

```bash
docker compose ps                    # stato dei container
docker compose logs -f process       # log del servizio Python (ASR, DWPose)
docker compose logs -f controll      # log del controller robot
docker compose restart controll      # riavvia solo il controller
docker compose up -d web process caddy   # avvio senza robot (sviluppo della WebApp)
docker compose up -d --build web     # ricompila solo la WebApp dopo una modifica
docker compose down                  # ferma tutto (i dati in data/ restano)
```

Verifica rapida del servizio Python:
`docker compose exec process python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:5000/health').read().decode())"`
(oppure `docker compose ps`, che per `process` mostra lo stato *healthy*).

## Variabili di configurazione

Il codice ora legge la configurazione da variabili d'ambiente. Se non sono impostate usa i valori di prima, quindi **l'avvio senza Docker continua a funzionare**.

| Variabile | Modulo | Default senza Docker |
|---|---|---|
| `PEPPERSIGN_PROCESS_URL` | Web | `http://127.0.0.1:5000` |
| `PEPPERSIGN_DATA_DIR` | Web, Process | `~/PepperSignData` |
| `PEPPERSIGN_ASSETS_DIR`, `PEPPERSIGN_TMP_DIR` | Process | `assets/`, `<data>/tmp_try` |
| `ASR_MODEL` | Process | `base` |
| `PEPPERSIGN_ROBOT_IP`, `PEPPERSIGN_ROBOT_PORT` | Controll | da `config.local.json` |
| `PEPPERSIGN_WEBAPP_URL` | Controll | da `config.local.json` |
| `PEPPERSIGN_GESTURE_DIR` | Controll | `~/PepperSignGestures` |
| `PEPPERSIGN_ROBOT_WAIT` | Controll | `0` (esce subito se il robot non risponde) |
| `PEPPERSIGN_FAKE_ROBOT` | Controll | `0` (`1` = robot simulato, modalità demo) |

## Modifiche fatte al codice per Docker

- **Web**: nuova classe `AppConfig` per l'URL del servizio Python e la cartella dati; le servlet non hanno più `127.0.0.1:5000` e `~/PepperSignData` fissati nel codice. Rimossa da `context.xml` la mappatura su `C:\multimedia_data`, che non era usata e che su Linux impediva l'avvio dell'app.
- **Process**: `config.py` legge le variabili d'ambiente, `ASR_MODEL` è configurabile. `requirements.txt` corretto: aggiunti `requests`, `gunicorn`, `pillow` e `imageio-ffmpeg`; tolto `whisper`, che era il pacchetto sbagliato; `torch` e `onnxruntime` sono installati dal Dockerfile nella variante CPU o GPU. In Docker il servizio gira con gunicorn (1 worker, più thread) invece del server di sviluppo di Flask.
- **Controll**: rimossi i percorsi `C:\Python27\tcl` fissati nel codice (ora applicati solo su Windows e solo se esistono). Gli IP reali non sono più nei default: vengono da `config.local.json`, che `main.py` ora carica automaticamente, oppure dalle variabili d'ambiente. Aggiunta l'attesa del robot all'avvio (`PEPPERSIGN_ROBOT_WAIT`), la modalità demo (`fake_qi.py`, `PEPPERSIGN_FAKE_ROBOT`) e la dimensione della finestra configurabile (`PEPPERSIGN_WINDOW_SIZE`).

### Correzioni emerse durante la prima build

| Problema | Correzione |
|---|---|
| Il `pip` dell'immagine Python non riconosceva i nomi dei pacchetti sul repository PyTorch (`Jinja2`/`jinja2`) | Il Dockerfile di Process aggiorna `pip`, `setuptools` e `wheel` prima di installare torch |
| `easy-dwpose` su Linux richiede `onnxruntime-gpu==1.16.2`, non installabile | installato con `--no-deps` + le sue altre dipendenze; `onnxruntime` (CPU) o `onnxruntime-gpu` recente viene installato a parte |
| noVNC 1.4 e il `websockify` 0.8 di Ubuntu 18.04 erano incompatibili ("Impossibile connettersi al server") | `websockify` 0.10 scaricato da GitHub ed eseguito con Python 3 |
| La GUI non entrava nel desktop virtuale da 1280×800 | desktop 1920×1080 e finestra 1900×1040, configurabili |

## Problemi noti e soluzioni

- **La build di `controll` si ferma con "SDK NAOqi non trovato"**: manca il file in `Controll/docker/sdk/`.
- **La GUI su :6080 resta nera**: il controller sta aspettando il robot. Controlla `docker compose logs controll` e l'IP in `PEPPER_IP`.
- **Il robot non è raggiungibile dal container, ma dal PC sì**: su Docker Desktop i container escono sulla rete tramite il PC, quindi di solito funziona. Se la rete del robot è l'hotspot di Windows, verifica che il firewall non blocchi il traffico di Docker/WSL. Su Linux si può aggiungere `network_mode: host` al servizio `controll`.
- **Il tablet non raggiunge https://…:8443**: apri la porta 8443 nel firewall di Windows e verifica che `PEPPERSIGN_HOST` sia l'IP giusto.
- **noVNC: "Impossibile connettersi al server"**: verifica che giri il nuovo websockify con `docker compose exec controll sh -c "ps aux | grep websockify"` (deve comparire `python3 -m websockify`). Se no, ricostruisci con `docker compose up -d --build controll`.
- **Le modifiche ai file sembrano sparire**: un editor (PyCharm/IntelliJ) con il file aperto può risalvare la versione vecchia. Ricarica i file dal disco e attiva *Synchronize external changes when switching to the IDE frame*.
- **Si creano file vuoti strani nella cartella** (`[web`, `ERROR`, `0.8.5`…): succede incollando righe di log nel prompt dei comandi, perché `>` viene interpretato come redirezione. Si possono cancellare.
- **La GPU non viene usata**: `docker compose logs process` deve riportare `DWposeDetector su cuda:0`. In Docker Desktop verifica che il backend sia WSL2.
