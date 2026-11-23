# Test di non regressione di Controll

Eseguono il controller (e la GUI) con il **robot simulato** (`fake_qi`) e registrano
il risultato di ogni metodo pubblico e il log. Il confronto con i file in `baseline/`
mostra se una modifica ha cambiato il comportamento.

Storia dei file in `baseline/`:
- 07/11/2026: generati con il codice prima del refactor; il codice rifattorizzato li riproduceva identici.
- 09/11/2026: rigenerati dopo la correzione della riconnessione (problema 10) e con il robot
  simulato piu' realistico (un solo robot che mantiene lo stato tra le sessioni; servizi che
  danno errore dopo la chiusura della sessione o con il robot offline). Unica differenza
  rispetto a prima: il motivo di un messaggio vocale fallito durante la disconnessione simulata.
- 09/11/2026 (sera): rigenerati dopo la revisione degli errori (problema 9) e l'esito dei comandi
  (problema 7). Differenze attese: `say`, `wakeup`, `rest` restituiscono (ok, messaggio),
  `get_pose` (ok, angoli, messaggio), `handle_command` (ok, messaggio). Il test si ferma dopo il
  primo errore di polling, cosi' il log non dipende piu' dalla tempistica.
- 09/11/2026 (notte): rigenerato `controller.json` dopo il rifiuto dei frame non coerenti
  (problema 2). Differenze attese: il caso "build_interpolation short" (un frame con 1 angolo
  su 14) ora e' rifiutato con InvalidGesture invece di essere completato con zeri; il file di
  prova `rotto.json` viene segnalato al caricamento. `gui.json` invariato.
- 09/11/2026 (sera tardi): rigenerato `gui.json` dopo il refactor della GUI (problema 6) e le
  etichette in italiano. Il refactor da solo riproduceva `gui.json` identico e le schermate di
  tutte le schede identiche pixel per pixel; unica differenza attesa dopo le etichette: la riga
  "[FRAME] Clear completato" diventa "[FRAME] Lista dei frame svuotata".
- 10/11/2026: rigenerati `controller.json` e `gui.json` dopo la rimozione del formato ready_v1
  (pulsante "Esporta gesto pronto"). Differenze attese: il gesto di prova `acqua` (ready_v1) ora e'
  rifiutato senza muovere il robot, quindi "Vai alla posa" parte da un'altra posizione (durata
  diversa); `check_tracks` non esiste piu'; la GUI non salva piu' `ready.json`.

Servono Python 2.7 (con Tkinter e un display per il test della GUI). Dalla cartella `Controll`:

```
python2.7 tests/regression_controller.py . out_controller.json
python3   tests/compare.py tests/baseline/controller.json out_controller.json

python2.7 tests/regression_gui.py . out_gui.json        # serve un display (anche Xvfb)
python3   tests/compare.py tests/baseline/gui.json out_gui.json
```

Test della riconnessione sicura (gesti interrotti da riconnessione, cambio robot,
robot offline, carico con piu' thread):

```
python2.7 tests/test_reconnect.py .
```

Test del rifiuto dei frame e dei gesti non coerenti (angoli mancanti o in piu', NaN,
dt non validi, gesti nel vecchio formato ready_v1): nessun movimento del robot simulato, motivo nel
log e nell'esito per il tablet; con un display prova anche Carica sequenza, Salva ed Export
nella GUI vera.

```
python2.7 tests/test_frames.py .
```

Test della sequenza dei frame senza finestra (`peppersign/ui/sequence.py`: cattura, modifica,
specchio, frame composito, ordine, copia, anti-collisione, file). Non serve un display:

```
python2.7 tests/test_sequence.py .
```

Test della sequenza modificata solo dal thread della finestra (problema 5): la lettura della
posa e' resa lenta e nel frattempo un frame viene rimosso o spostato, oppure si carica un file.
Il risultato deve finire sul frame giusto o essere scartato. Serve un display:

```
python2.7 tests/test_gui_threads.py .
```

Test della gestione degli errori (errori ripetuti scritti una volta, API mancanti
segnalate una volta, ritorni uniformi):

```
python2.7 tests/test_errors.py .
```

Prova completa del protocollo dei comandi con la WebApp vera (avviata, anche in Docker):
comando accodato con id, eseguito dal robot simulato, esito "done"/"failed" visto dalla
WebApp, "robot non collegato" quando Controll non risponde.

```
python2.7 tests/test_webapp_protocol.py . http://127.0.0.1:8080/PepperSign
```

Per tutti l'ultima riga deve essere `ESITO: OK`.

L'ultima riga di `compare.py` deve essere `ESITO: IDENTICO`. Se una modifica cambia
il comportamento di proposito, si rigenera la baseline e si controlla a mano la differenza.
