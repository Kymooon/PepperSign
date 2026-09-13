PepperSign refactor - struttura suggerita

File principali:
- main.py                -> entry point del programma
- peppersign/config.py   -> configurazione centralizzata
- peppersign/controller.py -> logica robot + polling WebApp
- peppersign/gui.py      -> pannello locale Tkinter
- peppersign/gesture_store.py -> gesture, salvataggio, export, reload da cartella
- peppersign/http_utils.py -> HTTP / upload multipart
- peppersign/audio.py    -> registrazione e recupero WAV dal robot
- peppersign/utils.py    -> utility comuni
- config.example.json    -> esempio di config esterna

Uso:
1) Copia config.example.json in config.json e modifica IP/URL/cartelle
2) Metti le gesture JSON dentro la cartella gesture_dir
3) Avvia: python main.py
   oppure: python main.py percorso_config.json

Migliorie incluse:
- clamp corretto anche per gesture in formato times/angles
- gestureId normalizzato in lowercase anche lato Pepper
- configurazione spostata fuori dal codice
- polling con dispatch centralizzato delle action
- caricamento gesture da directory, senza hardcode nel sorgente
- ultimo errore visibile in GUI
