# PepperSign — Modulo Controll

Controller del robot **Pepper**, in Python 2.7 con l'SDK NAOqi. Fa tre cose:

- riceve i comandi della WebApp con un polling su `GET /api/pepper/next` (SAY, ANIMATED_SAY, PLAY_GESTURE, …) e li esegue sul robot;
- offre una **GUI Tkinter** per registrare i gesti a keyframe (Dump Pose), modificarli, testarli ed esportarli in JSON;
- carica i gesti JSON da una cartella e li esegue con `ALMotion.angleInterpolation`.

## Struttura

```
Controll/
├── main.py                  entry point: config, connessione, GUI, thread di polling
├── config.example.json      esempio di configurazione per l'avvio senza Docker
├── Dockerfile               immagine Ubuntu 18.04 + Python 2.7 + NAOqi + noVNC
├── docker/
│   ├── supervisord.conf     processi del container (Xvfb, fluxbox, x11vnc, websockify, controller)
│   ├── run-controller.sh    avvio del controller con l'ambiente NAOqi
│   ├── start-vnc.sh         server VNC (password opzionale)
│   └── sdk/                 qui va l'SDK NAOqi Linux (.tar.gz), vedi sdk/README.md
└── peppersign/
    ├── config.py            configurazione: default, file JSON, variabili d'ambiente
    ├── controller.py        logica del robot, dispatch dei comandi, polling della WebApp
    ├── fake_qi.py           robot simulato per la modalità demo
    ├── gesture_store.py     caricamento, salvataggio ed export dei gesti
    ├── gui.py               pannello Tkinter
    ├── pose_dialog.py       finestra "Frame da coordinate" (beta, usa il servizio Process)
    ├── audio.py             registrazione WAV sul robot
    ├── http_utils.py        GET/POST JSON e upload multipart
    ├── compat.py, utils.py  compatibilità Py2/Py3 e utility
```

## Avvio

**Con Docker (consigliato):** vedi [DOCKER.md](../DOCKER.md). La GUI si apre nel browser su `http://localhost:6080`.

**Senza Docker** (Windows, Python 2.7 e SDK NAOqi per Windows installati):

```
copy config.example.json config.local.json      (imposta IP del robot e URL della WebApp)
python main.py                                   (oppure: python main.py percorso\config.json)
```

L'URL della WebApp è `http://<IP-PC>:8080/PepperSign` se gira in Docker, oppure `http://<IP-PC>:8080/PepperSign_Web_war_exploded` se la avvii da IntelliJ.

## Modalità demo (senza robot)

Imposta `PEPPERSIGN_FAKE_ROBOT=1`: nel `.env` con Docker, oppure senza Docker con `set PEPPERSIGN_FAKE_ROBOT=1` prima di `python main.py`. In questa modalità non serve né il robot né l'SDK. Ogni comando compare nel log della GUI con il prefisso `[DEMO]`. La posa dei giunti è simulata con i limiti reali di Pepper, quindi *Dump Pose*, *Test* ed export funzionano.

## Configurazione

Le variabili d'ambiente hanno la precedenza sul file JSON, che a sua volta ha la precedenza sui default.

| Variabile | Chiave JSON | Descrizione |
|---|---|---|
| `PEPPERSIGN_ROBOT_IP` / `_PORT` | `robot.ip` / `robot.port` | indirizzo di Pepper |
| `PEPPERSIGN_WEBAPP_URL` | `webapp.base_url` | URL base della WebApp |
| `PEPPERSIGN_GESTURE_DIR` | `paths.gesture_dir` | cartella delle gesture JSON |
| `PEPPERSIGN_TTS_LANGUAGE` | `robot_defaults.tts_language` | lingua del TTS |
| `PEPPERSIGN_WINDOW_SIZE` | `ui.window_size` | dimensione della finestra |
| `PEPPERSIGN_ROBOT_WAIT` | — | secondi di attesa del robot all'avvio (0 = esce subito) |
| `PEPPERSIGN_FAKE_ROBOT` | — | `1` = robot simulato |
| `PEPPERSIGN_GESTURE_AUTONOMY` | `robot_defaults.gesture_autonomy` | movimenti autonomi durante i gesti: `pause` (default), `off`, `none` |
| `PEPPERSIGN_GESTURE_PRE_DELAY` / `_POST_DELAY` | `robot_defaults.gesture_pre_delay` / `gesture_post_delay` | attese (s) prima e dopo ogni gesto con i movimenti autonomi in pausa (default 0,8 / 0,6) |
| `PEPPERSIGN_PROCESS_URL` | `process.url` | servizio Process per i frame da coordinate (in Docker `http://process:5000`) |

## Registrazione: riprendere da un frame e braccia morbide

Nella scheda **3) Registrazione segni**:

- **Vai al frame selezionato** porta il robot nella posa del frame scelto nella lista (in almeno 1 s, braccia rigide). Con *poi braccia morbide* attivo, subito dopo le braccia diventano morbide.
- **Braccia morbide** (*Morbido ON / OFF*, scelta tra entrambe, SX o DX): la stiffness si abbassa (default 0,40, regolabile 0,10–0,80) e il controller aggiorna continuamente la posizione comandata quando sposti il braccio. Il braccio si muove a mano e **resta dove lo lasci**, invece di cadere come con *Free Arms*. Le mani restano rigide. Se il braccio scende da solo, alza la stiffness; se è troppo duro da muovere, abbassala.
- *Hold*, *Free*, i test dei gesti e Rest/WakeUp disattivano automaticamente le braccia morbide.
- **Sposta su / Sposta giu** cambiano l'ordine del frame selezionato nella lista.

Flusso tipico per un movimento complesso: seleziona l'ultimo frame buono → *Vai al frame selezionato* → muovi le braccia → *Dump Pose* → ripeti.

## Scheda "Sicurezza e motori"

Valori letti in sottofondo dal controller (non bloccano la finestra):

- **Temperatura motori** di braccia, mani e testa (verde / arancione / rosso). Quando un motore scalda NAOqi ne riduce la forza: i segni diventano lenti e "duri". Consiglio: Rest e qualche minuto di pausa.
- **Ostacoli vicini alle braccia**: distanza dell'ostacolo più vicino dalla mano e lato (`ALMotion.getChainClosestObstaclePosition`), e quante volte il braccio è stato **rallentato** dalla protezione anti-collisione (evento `ALMotion/Safety/ChainVelocityClipped`). Dopo ogni gesto il log riporta eventuali rallentamenti con la posizione dell'ostacolo. La barra sopra il log mostra l'ostacolo più vicino e diventa rossa quando un braccio viene frenato.
- **Protezioni del robot**: anti-collisione esterna (SX, DX), anti-collisione con il proprio corpo, smart stiffness (attivabili/disattivabili, con conferma) e riduzione della forza per temperatura (solo lettura). Le protezioni disattivate dal pannello vengono riattivate con *Ripristina tutte* e alla chiusura del pannello.

La protezione anti-collisione esterna **rallenta** le braccia vicino agli ostacoli e nelle zone che i sensori non vedono (lo spazio torna "sconosciuto" dopo ~5 s fuori dal campo dei sensori): per segni fluidi lascia spazio libero intorno al robot. In demo, *Simula ostacolo a destra* prova l'indicatore senza robot.

## Frame da coordinate (beta)

Nella scheda **3) Registrazione segni**, riquadro *Frame da coordinate (beta)* → **Apri...**:

1. scegli il braccio (ed eventualmente *Copia speculare sull'altro braccio*);
2. scegli un punto del corpo di Pepper (mento, bocca, fronte, petto, spazio neutro...) e, se serve, uno spostamento in cm (avanti, su, verso l'esterno);
3. scegli la direzione del palmo e delle dita (*suggerito*, *libero* o una direzione dal punto di vista del robot) e l'apertura della mano;
4. **Calcola** mostra gli angoli e lo scarto dalla richiesta (Pepper ha 5 giunti per braccio e il gomito si ferma a ~90°: non tutte le pose sono raggiungibili, oltre 2 cm o 20° compare un avviso);
5. **Prova sul robot** porta il robot nella posa calcolata (in almeno 1 s); **Aggiungi frame** la inserisce dopo il frame selezionato (o in coda).

Il frame di partenza del calcolo è quello selezionato (o l'ultimo): così i frame successivi restano coerenti. I frame aggiunti si modificano, si salvano e si eseguono come quelli registrati con *Dump Pose*. Il calcolo avviene nel container `process` (endpoint `/retarget/pose`), che deve essere avviato.

## Formato dei gesti

- `frames_v1`: sequenza di keyframe `{"joints": [...], "frames": [{"angles": [...], "dt": 0.6}, ...]}`, salvata dalla GUI e ricaricabile per modificarla.
- `ready_v1`: pronta per `angleInterpolation`, `{"joints": [...], "times": [[...]], "angles": [[...]]}`. Si ottiene con *Export*.

L'ID del gesto è `gesture_id`, oppure `name`, oppure il nome del file, in minuscolo. Deve coincidere con l'ID usato dalla WebApp.
