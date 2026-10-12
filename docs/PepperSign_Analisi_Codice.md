# PepperSign — Report di analisi del codice

*Analisi del 30/09/2026 sulla cartella `PepperSign` (Controll, Process, Web). Sono stati letti tutti i sorgenti attivi; esclusi `old-version/`, `target/`, `.idea/`, modelli `.onnx` e file binari.*

---

## 1. Panoramica

PepperSign è un sistema per l'insegnamento della lingua dei segni italiana (LIS) con il robot umanoide Pepper, composto da tre moduli che comunicano via HTTP:

| Modulo | Cartella | Tecnologia | Ruolo | Dimensione |
|---|---|---|---|---|
| **Web** | `Web/PepperWebApp` | Java 17, Jakarta Servlet 6 (Tomcat), JSP, JS ES5 | Interfaccia sul tablet di Pepper/PC, orchestratore, coda comandi per il robot | 15 classi Java (~1.100 righe), ~4.500 righe JS |
| **Process** | `Process/VideoGeneration` | Python 3, Flask, DWPose (ONNX), Whisper, FFmpeg | Generazione degli scheletri dai video, ASR, valutazione del gesto dell'utente | ~1.100 righe |
| **Controll** | `Controll` | Python 2.7, NAOqi `qi`, Tkinter | Pilotaggio del robot, registrazione ed esecuzione dei gesti, GUI locale | ~2.450 righe |

### Architettura e flussi

```
            ┌──────────── Tablet Pepper / Browser ────────────┐
            │ index.jsp + ps-*.js  |  gestureTry.js  |  admin  │
            └──────────────┬───────────────────────────────────┘
                           │ HTTP (XHR)
                 ┌─────────▼──────────┐        HTTP (sincrono)     ┌───────────────────────┐
                 │  Tomcat  :8080     │ ─────────────────────────► │ Flask :5000 (Process) │
                 │  Servlet /api/*    │  /process /transcribe /try │ DWPose · Whisper      │
                 │  PepperCommandBus  │ ◄───────────────────────── │ ~/PepperSignData      │
                 └─────────▲──────────┘                            └───────────────────────┘
                           │ polling GET /api/pepper/next (ogni 0,2–0,3 s)
                 ┌─────────┴──────────┐        NAOqi (tcp 9559)    ┌───────────────┐
                 │ Controll (Py 2.7)  │ ─────────────────────────► │ Robot Pepper  │
                 │ GUI Tkinter        │                            └───────────────┘
                 └────────────────────┘
```

1. **Richiesta vocale (modalità PC):** microfono del browser → `/api/asr` → Flask `/transcribe` (Whisper) → estrazione della parola target → `/api/lesson` → se il video non esiste, Flask `/process` lo genera.
2. **Generazione dello scheletro:** Flask `/process` cerca il video in `assets/`, altrimenti lo scarica da SpreadTheSign → DWPose frame per frame → `~/PepperSignData/<slug>.mp4` + `.jpg`.
3. **Catalogo:** `/api/media` elenca le coppie immagine+video di `~/PepperSignData`; `/media/*` le serve con supporto ai Range.
4. **"Prova gesto":** webcam → `/api/try` (proxy Tomcat) → Flask `/try` (job asincrono) → scheletro dell'utente → similarità con il template → polling su `/try/status`.
5. **"Esegui gesto" su Pepper:** `/api/pepper/say` + `/api/pepper/gesture` → `PepperCommandBus` (coda FIFO) → Controll lo legge con `/api/pepper/next` → `angleInterpolation` sul robot.
6. **Registrazione dei gesti (offline):** GUI Tkinter → braccia libere → *Dump Pose* per ogni keyframe → validazione dei limiti → salvataggio JSON `frames_v1` o `ready_v1` in `~/PepperSignGestures`.

---

## 2. Punti di forza

- **Separazione dei moduli chiara** e motivata dal vincolo tecnico (NAOqi funziona solo su Python 2.7).
- **Controll ben rifattorizzato:** config esterna con deep-merge, dispatch dei comandi basato su una tabella (`command_handlers`), `GestureStore` caricato da cartella, livello di compatibilità Py2/Py3, `_try_service` per i servizi NAOqi opzionali.
- **Registrazione dei gesti ricca:** frame compositi (braccio SX/DX/testa acquisiti separatamente), mirroring con inversione dei segni, validazione con tolleranza e avviso vicino ai limiti, clamp ai limiti dei giunti prima dell'esecuzione.
- **Attenzione alla sicurezza lato Java:** whitelist regex sui nomi (`^[A-Za-z0-9_-]{1,100}$`), protezione dal path traversal in `MediaServlet`, streaming con i Range HTTP, `X-Content-Type-Options`.
- **Backend Flask:** modelli caricati una sola volta, semafori per GPU/ASR, fallback ASR a cascata (faster-whisper → openai-whisper → dummy), pulizia dei file temporanei in `finally`, job `/try` asincroni con TTL.
- **Frontend pensato per il tablet di Pepper** (Android 5.1 / vecchio Chrome): ES5, XHR, fallback per `getUserMedia`.
- `.gitignore` completo (modelli, config locale, target, snapshot).

---

## 3. Problemi rilevati (in ordine di priorità)

### 🔴 Critici — funzionalità rotte o incomplete

**C1. La modalità "microfono di Pepper" non funziona end-to-end.**
- Il frontend (`ps-pepper.js → runPepperFlow`) chiama `/api/pepper/start` e `/api/pepper/status`: **nessuna servlet espone questi endpoint** (404).
- Controll carica l'audio su `/api/pepper/audio` (`config.py → audio_upload_path`): **nessuna servlet esistente**.
- Il comando `SAY_AND_LISTEN` è gestito in Python ma **non esiste in `PepperCommand.java`**, e `PepperNextServlet.toJson()` serializza solo `action/text/gestureId/ts`: `sessionId` e `prompt` non arriverebbero mai.
- Lo stesso vale per `WAKEUP`, `REST`, `LIFE_ON`, `LIFE_OFF`: gestiti dal robot ma non producibili dalla webapp.
→ Decidere se completare il flusso (3 servlet + nuovi campi nel comando) o rimuoverlo.

**C2. Il feedback di stato nella home non appare mai.**
`ps-app.js` cerca `#asrText`, `#audioSourceToggle` e `#audioModeLabel`, che **non sono presenti in `index.jsp`**. Tutti i messaggi `setAsrStatus(...)` ("Sto ascoltando…", "Ho capito…") vengono scartati; l'utente vede solo `alert/confirm`. Non è possibile nemmeno cambiare la modalità PC/Pepper dall'interfaccia.

**C3. Le parole composte vengono rifiutate.**
`extract_target_it` restituisce fino a 3 token separati da spazi (es. "buon giorno"), ma `LessonServlet`/`GenerateServlet` accettano solo `[A-Za-z0-9_-]` → HTTP 400. Anche le lettere accentate ("città", "perché") vengono rifiutate. Inoltre `/process` salva con `_safe_slug` (`buon_giorno.mp4`) mentre `/try` cerca il template con il `gestureId` grezzo. → Serve **un'unica funzione di normalizzazione dell'ID** condivisa per convenzione da tutti e tre i moduli.

**C4. La metrica di similarità di "Prova gesto" è debole.**
`compute_similarity_percent` calcola l'IoU di maschere binarie (soglia 30 sul grigio) tra frame allineati per indice:
- non c'è allineamento temporale (un utente più lento o più veloce viene penalizzato) → usare **DTW**;
- lo scheletro è fatto di linee sottili, quindi l'IoU pixel-wise è intrinsecamente bassa e la soglia 0,65 è difficile da raggiungere;
- dipende da posizione e scala della persona nell'inquadratura;
- scarta i keypoint numerici già calcolati da DWPose.
→ Per la tesi conviene confrontare i **keypoint normalizzati** (centrati sulle spalle e scalati) con DTW, pesando di più mani e braccia. Il feedback attuale è binario e generico.

### 🟠 Importanti — robustezza e architettura

**I1. GUI Tkinter bloccata durante l'esecuzione dei gesti.**
`_tick()` gira sul thread principale ogni 500 ms e chiama `ctrl.get_volume()`, che acquisisce `self.lock`. Il lock resta occupato durante `tts.say`, `angleInterpolation` e la registrazione audio (fino a diversi secondi), quindi **la finestra si congela**. Anche `get_autonomous_life_state()` è una chiamata RPC sul thread della UI. → Leggere lo stato in un thread separato e metterlo in cache.

**I2. Chiamate HTTP sincrone e lunghe in Tomcat.**
`LessonServlet` (timeout 180 s) e `GenerateServlet` (10 min) attendono la fine della generazione DWPose. Conseguenze:
- il thread di Tomcat resta occupato;
- `LessonServlet` risponde `"GENERATING"` quando il video è già **stato generato**, mentre se si supera il timeout risponde `ERROR` anche se Python continua a lavorare;
- il frontend mostra "Generazione avviata! Attendi qualche secondo" solo **dopo** che la generazione è finita.
→ Rendere `/process` asincrono come `/try` (job id + polling).

**I3. Configurazione hard-coded e duplicata.**
- `http://127.0.0.1:5000` compare in 4 servlet, `~/PepperSignData` in 4 servlet e in `config.py`. I `getInitParameter(...)` restituiscono sempre `null` perché `web.xml` è vuoto.
- `context.xml` mappa `/media` su `C:\multimedia_data`, ma `MediaServlet` (`/media/*`) ha la precedenza e legge da `~/PepperSignData` → **configurazione morta e fuorviante**.
- In `config.py` e `gui.py` i percorsi `C:\Python27\tcl\...` sono fissati nel codice; `gui.py` reimporta `Tkinter` scavalcando il layer `compat`.
- `DEFAULT_CONFIG` contiene gli IP reali (`192.168.137.x`), il che vanifica `config.local.json`.
- Il `Caddyfile` contiene il segnaposto non valido `https://<192.168.0.108>:8443`.
- Il messaggio d'errore di `AsrServlet` cita la porta `:5001`, ma l'URL usato è `:5000`.

**I4. Lista dei gesti animabili duplicata.**
`PepperAnimatableGestures.java` elenca 7 gesti fissi (`ciao, acqua, casa, …`), mentre i gesti reali sono i JSON in `~/PepperSignGestures` sulla macchina di Controll. Le due liste possono divergere. Inoltre **i file dei gesti registrati (dato centrale della tesi) non sono versionati**. → Far pubblicare a Controll la lista dei gesti alla webapp, oppure spostare i JSON nel repository.

**I5. Polling molto frequente.**
Controll fa una GET ogni 0,2–0,3 s anche a vuoto. `PepperCommandBus` offre già `poll(timeout, unit)`: con il **long-polling** (es. attesa di 20 s) si riducono latenza e traffico.

**I6. Gestione dei job `/try`.**
- La TTL guard è un thread one-shot: se allo scadere il job è ancora `running` o è stato "toccato", la cartella non viene mai eliminata se il client non torna.
- I job sono tenuti in memoria: un riavvio perde le sessioni.
- `requests` è usato ma **manca in `requirements.txt`**; `whisper` dovrebbe essere `openai-whisper`; `Pillow` manca (serve a `single_dwpose.py`).
- La cache di `/process` controlla solo l'esistenza dei file: un file scritto a metà (dopo un crash) viene considerato valido; due richieste contemporanee sulla stessa parola scrivono sullo stesso file.

### 🟡 Sicurezza (contesto: LAN di laboratorio)

- Nessuna autenticazione: chiunque in rete può far parlare o muovere il robot, generare video o accedere ad `admin.jsp`.
- Endpoint che cambiano stato accettati via **GET** (`/api/pepper/say`, `/gesture`, `/animated-say`) → vulnerabili a CSRF.
- Flask con `CORS "*"`, server di sviluppo (`app.run`) esposto su `0.0.0.0`, risposte `/process` con percorsi assoluti del filesystem.
- Lo scraping di SpreadTheSign è fragile (regex sull'HTML) e ha implicazioni di **licenza/termini d'uso** da citare nella tesi.

### ⚪ Pulizia

- `js/script_modular_bundle.js` (1.069 righe) è **codice morto**: non è incluso in nessuna pagina ed è un duplicato dei moduli `ps-*`.
- `ps-pepper.js`: commento "✅ ANIMATED SAY (FIXATO)", uso misto di `fetch` e XHR; `PS.pepper.animatedSay` non restituisce la Promise.
- `ElementoMultimediale` usa nomi in italiano, il resto del codice in inglese; `persistence.xml` e `beans.xml` sono vuoti e inutilizzati.
- `.pyc` accanto ai sorgenti, `snapshots/*.ppm`, patch di `.idea/shelf`, `old-version/prova*.py` (~75 KB), `README.md` di Controll = "Progetto-Tirocinio".
- In `main.py`, `rest()` viene chiamato due volte alla chiusura (in `gui.on_close` e dopo `gui.run()`).
- Mancano del tutto i **test automatici**.

---

## 4. Contratto delle API (stato attuale)

| Endpoint (Tomcat) | Metodo | Implementato | Chiamato da | Note |
|---|---|---|---|---|
| `/api/media` | GET | ✅ | home, admin | lista img+video |
| `/media/*` | GET | ✅ | home | Range, anti-traversal |
| `/api/lesson` | POST JSON | ✅ | ASR flow | sincrono su `/process` |
| `/api/generate` | POST | ✅ | pulsante "+" | sincrono, 10 min |
| `/api/asr` | POST multipart | ✅ | modalità PC | proxy `/transcribe` |
| `/api/try/*` | POST/GET/DELETE | ✅ | gestureTry.js | proxy asincrono |
| `/api/pepper/say` · `animated-say` · `gesture` | POST/GET | ✅ | card, admin | accodano |
| `/api/pepper/animatable` | GET | ✅ | card, admin | lista fissa |
| `/api/pepper/next` | GET/POST | ✅ | Controll | JSON costruito a mano |
| `/api/pepper/start` · `status` | — | ❌ **mancante** | ps-pepper.js | vedi C1 |
| `/api/pepper/audio` | — | ❌ **mancante** | Controll | vedi C1 |

---

## 5. Piano di lavoro proposto

**Fase 1 — Far funzionare ciò che c'è (breve)**
1. Aggiungere `#asrText` e il toggle PC/Pepper in `index.jsp` (C2).
2. Definire la normalizzazione unica del `gestureId` (minuscolo, spazi→`_`, accenti rimossi) e applicarla in JS, Java e Python (C3).
3. Completare il flusso microfono di Pepper (`start`/`status`/`audio` + campi `sessionId`/`prompt` in `PepperCommand`), oppure rimuoverlo (C1).
4. Correggere `requirements.txt`, il `Caddyfile`, il messaggio `:5001` ed eliminare `script_modular_bundle.js`.

**Fase 2 — Robustezza**
5. Sbloccare la GUI Tkinter (stato letto in background) (I1).
6. Rendere `/process` asincrono e il frontend basato su polling (I2).
7. Centralizzare la configurazione (`web.xml`/variabili d'ambiente per Tomcat, un unico `PEPPERSIGN_DATA_DIR`) (I3).
8. Long-polling su `/api/pepper/next` (I5).
9. Lista dei gesti animabili pubblicata da Controll o versionata (I4).

**Fase 3 — Contributo scientifico della tesi**
10. Nuova metrica di valutazione: keypoint DWPose normalizzati + DTW, punteggio per segmento corporeo, feedback specifico ("mano destra troppo bassa").
11. Test: unit test per `extract_target_it`, normalizzazione ID e metrica; test di integrazione per le servlet.
12. Documentazione: README unico con avvio dei 3 moduli, diagramma dell'architettura, formato JSON dei gesti (`frames_v1` / `ready_v1`).

---

*Report generato da Claude; da aggiornare man mano che le correzioni vengono applicate.*
