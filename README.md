# PepperSign

Sistema di supporto all'insegnamento della **Lingua dei Segni Italiana (LIS)** basato sul robot umanoide **Pepper**, sviluppato come lavoro di tesi triennale in Informatica presso l'Università degli Studi di Salerno.

PepperSign affianca i docenti nell'insegnamento della LIS e offre agli studenti uno strumento di esercitazione individuale: Pepper usa le braccia e le mani per mostrare fisicamente i segni che lo studente vuole imparare.

Rispetto a lavori simili, PepperSign si distingue per due aspetti:

- **usa attivamente il tablet sul petto del robot** come interfaccia per lo studente, invece di considerarlo solo un ostacolo ai movimenti delle braccia;
- **rende la creazione dei segni accessibile**: il docente può insegnare un segno a Pepper muovendogli direttamente le braccia, senza bisogno di competenze informatiche e senza dipendere dalle risorse di calcolo o dai dati di addestramento di un modello.

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

## Installazione su un nuovo PC

### 1. Requisiti
- [Git](https://git-scm.com/download/win)
- [Docker Desktop](https://docs.docker.com/desktop/) con backend **WSL2**, avviato fino alla scritta *Engine running*
- Circa 15 GB liberi su disco (immagini Docker e modelli)
- *Opzionale:* scheda NVIDIA con driver aggiornati, per usare la GPU
- *Opzionale:* il robot Pepper sulla stessa rete del PC

### 2. Clonare il repository
```bat
git clone https://github.com/Kymooon/PepperSign.git
cd PepperSign
```

### 3. Copiare l'SDK NAOqi (solo per il modulo Controll)
L'SDK non è nel repository perché la licenza non ne consente la ridistribuzione. Copia il file `pynaoqi-python2.7-2.8.7.4-linux64-*.tar.gz` (versione **Linux 64 bit**, non quella Windows) in `Controll/docker/sdk/`, **senza estrarlo**. Dettagli in [Controll/docker/sdk/README.md](Controll/docker/sdk/README.md).

> Se non hai l'SDK puoi comunque usare la WebApp e il servizio Python: vedi la variante "senza Controll" al passo 5.

### 4. Creare il file di configurazione
```bat
copy .env.example .env
```
Apri `.env` con un editor di testo e imposta:

| Variabile | Valore |
|---|---|
| `PEPPER_IP` | IP del robot (lo dice Pepper premendo il pulsante sul petto) |
| `PEPPERSIGN_FAKE_ROBOT` | `1` per provare senza robot, `0` con il robot reale |
| `VNC_PASSWORD` | consigliata in laboratorio: senza password chiunque sulla rete può comandare il robot |

`PEPPERSIGN_HOST` non serve toccarlo: lo script di avvio rileva da solo l'IP del PC.

### 5. Primo avvio
Dalla cartella del progetto:
```bat
avvia-peppersign.bat -Build
```
La prima volta richiede parecchi minuti: scarica le immagini base, PyTorch e i modelli DWPose (circa 350 MB).

| Variante | Comando |
|---|---|
| Senza SDK NAOqi (niente Controll) | `avvia-peppersign.bat -Build -Services web,process,caddy` |
| Con GPU NVIDIA | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build` |
| IP rilevato sbagliato | `avvia-peppersign.bat -Build -Ip 192.168.x.x` |

### 6. Verificare che sia tutto acceso
```bat
docker compose ps
```
Tutti i container devono risultare *running*, e `process` deve risultare *healthy* (al primo avvio può impiegare un paio di minuti).

### 7. Aprire il sistema
| Cosa | Indirizzo |
|---|---|
| WebApp dal tablet di Pepper o da altri dispositivi | `https://<IP-del-PC>:8443/` |
| WebApp dal PC stesso | `http://localhost:8080/PepperSign/` |
| GUI del controller del robot | `http://localhost:6080` → *Connect* |

- Al primo accesso in HTTPS il browser mostra un avviso sul certificato: va accettato. L'HTTPS serve perché il tablet possa usare microfono e webcam.
- Se il tablet non si collega, apri la porta **8443** nel firewall di Windows.

### 8. Uso quotidiano
| Azione | Comando |
|---|---|
| Avviare | doppio clic su `avvia-peppersign.bat` |
| Fermare | `docker compose down` (i dati in `data/` restano) |
| Aggiornare dopo un `git pull` | `avvia-peppersign.bat -Build` |
| Vedere i log | `docker compose logs -f process` oppure `docker compose logs -f controll` |

Problemi frequenti, GPU e tutte le variabili di configurazione: **[DOCKER.md](DOCKER.md)**.

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
