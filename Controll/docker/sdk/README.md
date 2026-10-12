# SDK NAOqi per il container Controll

Il container del modulo Controll ha bisogno dell'SDK Python di NAOqi **per Linux a 64 bit**.
Quello che usi oggi su Windows non va bene: serve la versione Linux.

1. Scarica dal sito di Aldebaran/SoftBank (area download / supporto di Pepper)
   il file:

   `pynaoqi-python2.7-<versione>-linux64-<data>.tar.gz`   (in uso: `pynaoqi-python2.7-2.8.7.4-linux64-20210819_141148.tar.gz`)

   La versione in uso nel progetto è la 2.8.7.4.

2. Copia il file **così com'è** (senza estrarlo) in questa cartella:

   `Controll/docker/sdk/pynaoqi-python2.7-2.8.7.4-linux64-20210819_141148.tar.gz`

3. Ricostruisci il container:

   `docker compose build controll`

Durante la build viene eseguito `import qi`: se l'SDK manca o è sbagliato, la build si ferma con un messaggio esplicito.

> L'archivio dell'SDK non va messo nel repository Git (è escluso dal `.gitignore`), perché la licenza non ne consente la ridistribuzione.
