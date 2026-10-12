"""
Punti del corpo di Pepper usati come riferimento per i frame da coordinate (BETA).

Coordinate nel sistema del torso (metri): x avanti, z in alto; per y si usa
`y_out`, la distanza laterale verso l'ESTERNO del braccio che fa il segno
(positiva = dal lato di quel braccio, negativa = verso il lato opposto).
Il punto indica dove mettere il CENTRO della mano: per i punti del viso e' gia'
~5 cm davanti alla superficie, cosi' la mano non tocca la testa.

Ricavati dall'URDF ufficiale (pepper_description) con la testa dritta
(HeadYaw = HeadPitch = 0): giunto della testa a (-0.038, 0, 0.170), camera
"bocca" a (0.055, 0, 0.232), camera della fronte a (0.048, 0, 0.333), sommita'
della testa a z ~0.386, tasto sul petto a (0.050, 0, 0.055), tablet centrato
a ~(0.084, 0, 0.063) inclinato di 30 gradi; spalle a (-0.057, +-0.150, 0.087).
Le posizioni di mento, guance, orecchie e collo sono stimate dalla forma della
testa: approssimate, da regolare con gli spostamenti in cm.
Molti punti del viso sono oltre la portata di Pepper (gomito max ~90 gradi):
il solutore avvisa con lo scarto ottenuto.
"""

# id: (etichetta, x, y_out, z, palmo suggerito, dita suggerite)
LANDMARKS = [
    ("spazio_neutro", "Spazio neutro (davanti al busto)", 0.25, 0.08, 0.02, None, None),
    ("davanti_petto", "Davanti al petto (centro)", 0.20, 0.00, 0.10, None, None),
    ("petto_lato", "Petto, dal lato del braccio", 0.18, 0.10, 0.08, None, None),
    ("spalla_opposta", "Spalla opposta (spesso fuori portata)", 0.05, -0.15, 0.12, "indietro", None),
    ("collo", "Collo", 0.08, 0.00, 0.16, "indietro", None),
    ("mento", "Mento", 0.10, 0.00, 0.20, None, None),
    ("bocca", "Bocca", 0.11, 0.00, 0.232, None, None),
    ("naso", "Naso", 0.12, 0.00, 0.26, None, None),
    ("occhi", "Occhi", 0.11, 0.00, 0.29, None, None),
    ("fronte", "Fronte", 0.10, 0.00, 0.33, None, None),
    ("guancia", "Guancia (lato del braccio)", 0.08, 0.06, 0.24, None, None),
    ("orecchio", "Orecchio (lato del braccio, spesso fuori portata)", -0.02, 0.13, 0.26, None, None),
    ("sopra_testa", "Sopra la testa", 0.00, 0.08, 0.45, None, "su"),
    ("pancia", "Davanti alla pancia (sotto il tablet)", 0.20, 0.00, -0.12, None, None),
    ("fianco", "Fianco, braccio lungo il corpo e scostato", 0.08, 0.24, -0.25, "dentro", None),
    ("avanti_lontano", "Avanti, braccio disteso", 0.35, 0.12, 0.10, None, "avanti"),
]

# Direzioni proposte nella GUI (nomi accettati da pose.parse_direction)
DIRECTION_CHOICES = [
    "avanti", "indietro", "su", "giu", "dentro", "fuori",
    "avanti+su", "avanti+giu", "avanti+dentro", "avanti+fuori", "su+dentro", "su+fuori",
    "giu+dentro", "indietro+su",
]


def landmark_ids():
    return [item[0] for item in LANDMARKS]


def get_landmark(landmark_id):
    for item in LANDMARKS:
        if item[0] == landmark_id:
            return item
    raise KeyError("Punto del corpo sconosciuto: %s" % landmark_id)


def landmark_point(landmark_id, side, forward=0.0, up=0.0, outward=0.0):
    """
    Punto (torso, metri) per il braccio `side` ("L"/"R"), con spostamenti in metri:
    forward = avanti, up = in alto, outward = verso l'esterno del braccio.
    """
    _, _, x, y_out, z, _, _ = get_landmark(landmark_id)
    sign = 1.0 if side == "L" else -1.0           # esterno del braccio sinistro = +y
    return [x + forward, sign * (y_out + outward), z + up]


def as_dicts():
    return [{"id": i, "label": label, "x": x, "y_out": y, "z": z, "palm": palm, "fingers": fingers}
            for i, label, x, y, z, palm, fingers in LANDMARKS]
