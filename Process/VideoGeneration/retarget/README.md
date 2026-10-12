# Retargeting video → gesto Pepper (BETA)

Genera la **bozza** di un gesto per Pepper a partire da un video. Il modulo estrae i keypoint della persona con DWPose, li converte negli angoli dei giunti delle braccia di Pepper e salva un JSON `frames_v1` che si apre nella GUI di Controll per le correzioni e si esegue sul robot.

```
video → DWPose (keypoint 2D) → profondità stimata → riconoscimento posa di riposo
      → retargeting geometrico (punto di partenza)
      → cinematica inversa sulla posizione del polso (limiti dei giunti, tablet)
      → rotazione del polso (WristYaw) dai punti della mano
      → apertura mani → smoothing → keyframe (picchi del polso inclusi) → riposo a inizio/fine
      → <nome>_auto.json  (frames_v1)
```

È un modulo separato, eseguito a mano: non modifica le funzionalità esistenti.

## Generare un gesto (F1)

Dalla cartella `PepperSign`, su Windows:

1. **Aggiorna l'immagine `process`**, solo la prima volta o dopo modifiche al modulo:
   ```
   docker compose build process
   ```
2. **Genera il gesto:**
   ```
   docker compose run --rm process python3 -m retarget.generate --video assets/acqua.mp4 --name acqua --reuse
   ```
   Con `--reuse` vengono riutilizzati i keypoint già estratti (anche quelli della fase F0), così si evitano i ~2 minuti di DWPose su CPU.
3. **Controlla i risultati** in `data\media\_retarget\acqua\`:

   | File | Contenuto |
   |---|---|
   | `check.png` | **da guardare prima di provare sul robot:** video + Pepper di fronte e di lato nei keyframe |
   | `report.md` | keyframe, durata, errore del polso, eventuali contatti con il tablet |
   | `angles.png` | traiettorie dei giunti |
   | `acqua_auto.json` | il gesto |

4. **Provalo:**
   - copia `acqua_auto.json` in `data\gestures\`;
   - nella GUI (`http://localhost:6080`) premi **Ricarica**, scegli `acqua_auto` e premi **Avvia**. Per vedere e correggere i frame usa invece **Carica sequenza**;
   - prima prova in **modalità demo** (`PEPPERSIGN_FAKE_ROBOT=1`), poi sul robot reale.

Altri video: copiali in `Process\VideoGeneration\assets\` e usa `--video assets/<file>`.

### Opzioni

| Opzione | Default | Significato |
|---|---|---|
| `--speed` | `0.8` | velocità rispetto al video (`0.5` = metà velocità, consigliato per le prime prove) |
| `--reuse` | no | riusa i keypoint già estratti |
| `--mirror` | no | specchia sinistra/destra (default: lato anatomico) |
| `--epsilon` | `0.08` | tolleranza (rad) della riduzione a keyframe: più alta = meno frame |
| `--max-keyframes` | `20` | numero massimo di keyframe |
| `--no-ik` | no | solo retargeting geometrico (come F0), per confronto |
| `--no-rest-ends` | no | non aggiungere il riposo a inizio/fine |
| `--no-wrist` | no | polso fermo nella posa di riposo (comportamento precedente), per confronto |
| `--wrist-flip` | no | sceglie l'altro verso di rotazione del polso (se sul robot ruota al contrario) |
| `--wrist-gain` | `1.0` | amplifica le oscillazioni rapide del polso (es. `1.5`), senza cambiare la rotazione media |
| `--hand-conf` | `0.5` | confidenza minima della mano per stimare il polso |
| `--smooth-hand` | `5` | finestra di smoothing (frame) per polso e apertura della mano |

### Sicurezza sul robot
- Il gesto **parte e finisce nella posa di riposo**: viene aggiunto un frame di riposo se il video non comincia o non finisce a riposo.
- Velocità dei giunti limitata a 2 rad/s tra keyframe (1,5 rad/s verso e dal riposo); velocità globale 0,8 di default.
- I giunti restano a 0,02 rad dal fine corsa.
- La cinematica inversa tiene il braccio fuori da una scatola che approssima il tablet; i keyframe sospetti sono segnalati nel report e nel JSON (`warning`).
- Il controller mette in pausa i movimenti autonomi durante il gesto (`PEPPERSIGN_GESTURE_AUTONOMY`).

## Frame da coordinate (beta)

Crea un frame indicando dove deve stare la mano e come deve essere orientata, come il generatore MATLAB del paper di Botta et al. Il risultato è un frame `frames_v1` che si apre nella GUI e si mescola con quelli registrati o generati dal video.

```
docker compose run --rm process python3 -m retarget.pose --side R --point 0.22 -0.13 0.0 --palm dentro --fingers avanti
docker compose run --rm process python3 -m retarget.pose --side R --point 0.25 -0.15 0.05 --palm dentro --hand 1 --mirror \
    --out /data/media/_retarget/prova_coordinate.json --dt 1.2
```
Con `--out` il frame viene aggiunto in coda al gesto (creato se non esiste); il frame precedente fa da punto di partenza, così i frame successivi restano coerenti.

| Opzione | Significato |
|---|---|
| `--side` | braccio del robot (`R` o `L`) |
| `--point X Y Z` | centro della mano nel sistema del torso, in metri: x avanti, y verso la **sinistra del robot**, z in alto. Spalle a (−0,057, ±0,150, 0,087) |
| `--wrist-point` | `--point` indica il polso invece del centro della mano |
| `--palm`, `--fingers` | direzione del palmo e delle dita: `avanti`, `indietro`, `su`, `giu`, `sinistra`, `destra`, `dentro`, `fuori`, combinabili (`avanti+su`) o `x,y,z` |
| `--hand` | apertura della mano 0–1 |
| `--mirror` | copia la posa specchiata sull'altro braccio |
| `--w-palm`, `--w-fingers` | pesi dell'orientamento (default 0,0025: 1 rad di errore pesa come 5 cm) |
| `--dt` | durata del movimento verso il frame (s) |

Pepper ha 5 giunti per braccio: posizione e orientamento completi insieme in genere non sono raggiungibili, e il gomito si ferma a ~90°. Il solutore trova il miglior compromesso secondo i pesi e stampa gli scarti; oltre 2 cm o 20° il frame riceve un avviso (`warning`), visibile anche nel JSON.

**Come funziona (`ik.solve_arm_pose`).** Minimizza l'errore pesato di posizione e di direzione di palmo e dita, entro i limiti dei giunti, con la penalità del tablet; Levenberg–Marquardt da più punti di partenza (frame precedente + alcune pose tipiche) per evitare i minimi locali. Assi della mano di Pepper: dita = asse x della mano, palmo = −z (lato del centro mano), pollice = +y a destra / −y a sinistra: da confermare sul robot.

### Dalla GUI di Controll

Lo stesso calcolo è disponibile nella GUI (scheda *Registrazione segni* → *Frame da coordinate (beta)*), con un elenco di punti del corpo di Pepper (`landmarks.py`: mento, bocca, naso, occhi, fronte, guancia, collo, petto, spazio neutro, sopra la testa...), ricavati dall'URDF e approssimati. La GUI chiama questo servizio:

| Endpoint | Uso |
|---|---|
| `GET /retarget/landmarks` | punti del corpo e direzioni disponibili |
| `POST /retarget/pose` | `{"side": "R", "landmark": "mento", "offset_cm": {"avanti": 2, "su": 0, "esterno": 0}, "palm": "indietro", "fingers": null, "hand": 0.8, "mirror": false, "dt": 1.0, "base": {giunto: angolo}}` → angoli, frame, scarti e avvisi |

Da riga di comando: `python3 -m retarget.pose --side R --landmark mento --offset 2 0 0 --palm indietro`.

## Fase F0: confronto tra estrattori

```
docker compose run --rm process python3 -m retarget.f0 --video assets/acqua.mp4 --name acqua --extractors dwpose
docker compose run --rm process sh -c "python3 -m pip install mediapipe==0.10.14 && python3 -m retarget.f0 --video assets/acqua.mp4 --name acqua --extractors mediapipe"
```
I risultati vanno in `data\media\_retarget_f0\<nome>\`, con `report.md` e i grafici. Esito su `acqua`: DWPose è affidabile sui video a mezzo busto, MediaPipe no. Le versioni di MediaPipe ≥ 1.0 non hanno più l'interfaccia `solutions` usata qui.

## Come funziona

| Modulo | Ruolo |
|---|---|
| `pepper_kinematics.py` | modello cinematico delle braccia di Pepper dall'URDF ufficiale (FK, limiti, posa di riposo) |
| `model_check.py` | confronto del modello con le posizioni misurate da NAOqi sul robot |
| `keypoints.py` | formato comune dei keypoint, conversione DWPose/MediaPipe |
| `depth.py` | profondità dai keypoint 2D (lunghezze dei segmenti, mani davanti al corpo) |
| `rest.py` | riconoscimento della posa di riposo (polsi al bordo, braccio che pende) |
| `retarget.py` | angoli dalle direzioni di braccio e avambraccio (soluzione analitica) |
| `ik.py` | cinematica inversa sulla posizione del polso + penalità del tablet |
| `wrist.py` | rotazione del polso (WristYaw) dalla linea delle nocche + punti di svolta |
| `pose.py` | frame da coordinate: posizione + orientamento della mano (IK a 5 giunti) |
| `landmarks.py` | punti del corpo di Pepper per i frame da coordinate |
| `postprocess.py` | smoothing, limiti, keyframe, dt, formato frames_v1 |
| `visualize.py` | immagine di controllo video/Pepper |
| `generate.py` | script F1 |
| `f0.py`, `extractors.py` | script F0 ed estrazione dei keypoint |

**Rotazione del polso.** Pepper ha un solo movimento del polso: la rotazione attorno all'avambraccio (WristYaw, ±104°); non può piegarlo su/giù. Nel video si misura la linea delle nocche (mignolo → indice) rispetto all'avambraccio: se appare lunga il palmo (o il dorso) è rivolto verso la telecamera, se è corta la mano è di taglio. Si sceglie il WristYaw che fa apparire la mano di Pepper allo stesso modo a chi lo guarda di fronte. Solo dove la mano è rilevata bene (`--hand-conf`); altrove il valore è interpolato o resta a riposo. I massimi e minimi della rotazione diventano keyframe obbligatori, così le oscillazioni rapide non vengono eliminate. In `check.png` il segmento verde mostra il lato del pollice: nel video la linea delle nocche, su Pepper l'orientamento della mano.

**Bersaglio del polso.** In orizzontale la posizione è misurata rispetto alla linea mediana del corpo e scalata sulle larghezze delle spalle; in verticale e in profondità è misurata rispetto alla spalla e scalata sulla lunghezza del braccio. La cinematica inversa pesa di più la posizione vista di fronte (laterale e altezza) che la profondità. Così, quando Pepper non può raggiungere il punto (gomito limitato a ~90°), porta la mano allo stesso punto visto di fronte, solo più avanti.

## Test automatici

```
docker compose run --rm process python3 -m retarget.tests.test_f1
docker compose run --rm process python3 -m retarget.tests.test_f0_pipeline
docker compose run --rm process python3 -m retarget.tests.test_wrist
docker compose run --rm process python3 -m retarget.tests.test_model
docker compose run --rm process python3 -m retarget.tests.test_pose
```

## Limiti noti
- **Polso (`WristYaw`):** stima beta da 2D. Il verso della rotazione non è sempre distinguibile (si sceglie quello più vicino alla posa di riposo; `--wrist-flip` per l'altro) e l'asse della mano di Pepper è ricavato dalla posa di riposo: entrambi da confermare sul robot. I piegamenti del polso e i movimenti delle dita non sono riproducibili.
- **Testa:** resta nella posa di riposo.
- **Mano:** solo apertura 0–1 (Pepper non muove le dita singolarmente).
- **Modello di Pepper:** dal 07/10/2026 si usa l'URDF ufficiale (`pepper_description`): spalle 57 mm dietro l'origine del torso, gomito spostato di 15 mm verso l'esterno e inclinato di ~9°, centro della mano dalla documentazione NAOqi. Rispetto al modello semplificato precedente il polso cambia di ~2,7 cm rispetto alla spalla. Restano da verificare sul robot: lo scarto di 23,6 mm sul polso tra URDF e documentazione e la forma del tablet (non presente nell'URDF, ancora approssimata con una scatola). Per la verifica: `python3 -m retarget.model_check --input <file>` con pose registrate dal robot (formato nel file).
- **Profondità dal 2D:** affidabile solo in parte. Per i segni con le mani lontane dal corpo verso la telecamera, controlla `check.png`.
- **Altezza dei punti del viso:** le proporzioni testa/spalle di Pepper sono diverse da quelle umane, quindi i segni al mento possono risultare un po' bassi.
