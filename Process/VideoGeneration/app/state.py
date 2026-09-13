from threading import Lock, Semaphore

JOBS = {}
JOBS_LOCK = Lock()

DETECTOR_LOCK = Lock()   # prudenziale
GPU_SEM = None           # inizializzato in create_app()
ASR_SEM = None           # inizializzato in create_app()
