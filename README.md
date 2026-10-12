# PepperSign

Sistema per l'insegnamento della **Lingua dei Segni Italiana (LIS)** con il robot umanoide **Pepper**, sviluppato come lavoro di tesi.

L'utente chiede un segno a voce, dal tablet di Pepper o da un PC. Il sistema mostra il video del segno con lo scheletro della posa (DWPose), Pepper lo esegue con le braccia, e l'utente può riprodurlo davanti alla webcam e ricevere un punteggio.

## Moduli

| Modulo | Cartella | Tecnologia | Ruolo |
|---|---|---|---|
| **Web** | [`Web/PepperWebApp`](Web/PepperWebApp) | Java 17, Jakarta Servlet (Tomcat 10.1), JSP, JavaScript ES5 | Interfaccia per tablet e PC, API REST, coda dei comandi per il robot |
| **Process** | [`Process/VideoGeneration`](Process/VideoGeneration) | Python 3, Flask, DWPose (ONNX), Whisper, FFmpeg | Generazione degli scheletri, riconoscimento vocale, valutazione del gesto |
| **Controll** | [`Controll`](Controll) | Python 2.7, SDK NAOqi, Tkinter | Pilotaggio di Pepper, registrazione ed esecuzione dei gesti |

```
Tablet / PC ──HTTPS──► Caddy ──► Web (Tomcat) ──HTTP──► Process (Flask: DWPose, Whisper)
                                    ▲
                                    │ polling comandi
                              Controll (Python 2.7) ──NAOqi──► Pepper
```

## Avvio rapido (Docker)

Requisiti: [Docker Desktop](https://docs.docker.com/desktop/) e l'SDK NAOqi Python 2.7 per **Linux 64 bit** in `Controll/docker/sdk/` (vedi [README dell'SDK](Controll/docker/sdk/README.md)).

```
copy .env.example .env          (poi imposta PEPPER_IP, oppure PEPPERSIGN_FAKE_ROBOT=1 per la demo)
avvia-peppersign.bat -Build
```

| Cosa | Indirizzo |
|---|---|
| WebApp da tablet o altri dispositivi | `https://<IP-del-PC>:8443/` |
| WebApp dal PC | `http://localhost:8080/PepperSign/` |
| GUI del controller (robot) | `http://localhost:6080` |

Senza robot: `PEPPERSIGN_FAKE_ROBOT=1` nel `.env` attiva un Pepper simulato.

La guida completa è in **[DOCKER.md](DOCKER.md)**: GPU, dati, variabili, problemi noti.

## Struttura della repository

```
PepperSign/
├── README.md, DOCKER.md          documentazione
├── docker-compose.yml            avvio di tutti i servizi (CPU)
├── docker-compose.gpu.yml        variante GPU NVIDIA per Process
├── .env.example                  modello di configurazione (copiare in .env)
├── avvia-peppersign.bat / .ps1   avvio su Windows con rilevamento dell'IP
├── docker/caddy/Caddyfile        proxy HTTPS
├── docs/                         report di analisi e di sistema
├── Controll/                     modulo robot (Python 2.7)
├── Process/                      modulo di elaborazione (Python 3)
├── Web/                          modulo web (Java)
└── data/                         dati runtime: video generati, gesture (non versionati)
```

## Documentazione

- [DOCKER.md](DOCKER.md): installazione, avvio, configurazione, problemi noti
- [docs/PepperSign_Report_Sistema.md](docs/PepperSign_Report_Sistema.md): architettura attuale, stato dei problemi, prossimi passi
- [docs/PepperSign_Analisi_Codice.md](docs/PepperSign_Analisi_Codice.md): prima analisi del codice
- README dei moduli: [Controll](Controll/README.md), [Process](Process/README.md)

## File non presenti nella repository

| File | Dove metterlo |
|---|---|
| `.env` | copia di `.env.example` |
| SDK NAOqi Linux (`pynaoqi-python2.7-*-linux64*.tar.gz`) | `Controll/docker/sdk/` (licenza: non ridistribuibile) |
| Modelli DWPose (`yolox_l.onnx`, `dw-ll_ucoco_384.onnx`) | `Process/VideoGeneration/checkpoints/` (scaricati da soli se mancano) |
| Video generati e gesture registrate | `data/media`, `data/gestures` |
