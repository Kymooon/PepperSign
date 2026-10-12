"""
Riconoscimento della posa di riposo (braccio lungo il fianco).

Nei video a mezzo busto, quando il braccio e' a riposo il polso e' sul bordo
inferiore dell'immagine o fuori quadro. In questi casi la profondita' stimata
non e' affidabile (l'avambraccio "tagliato" sembra puntare in avanti), quindi
quei frame vengono marcati come riposo e il braccio di Pepper va nella sua
posa di riposo.

Per un braccio, un frame e' "a riposo" se:
  - il polso manca (non rilevato o poco affidabile), oppure
  - il polso o il gomito sono entro `border` dal bordo inferiore dell'immagine, oppure
  - il polso e' sotto il gomito e il gomito e' sotto la spalla, con l'avambraccio
    quasi verticale (braccio che pende), e il polso piu' in basso di `low` larghezze
    di spalla rispetto alle spalle.
Gli intervalli molto brevi (sotto `min_run` frame) vengono assorbiti per evitare sfarfallio.
"""
import numpy as np

DEFAULT_BORDER = 0.04      # frazione dell'altezza dell'immagine
DEFAULT_LOW = 1.0          # larghezze di spalla sotto la linea delle spalle
DEFAULT_MIN_RUN = 4        # frame


def _clean_runs(flags, min_run):
    """Elimina gli intervalli (True o False) piu' corti di min_run, tranne ai bordi."""
    f = flags.copy()
    n = len(f)
    i = 0
    while i < n:
        j = i
        while j < n and f[j] == f[i]:
            j += 1
        if (j - i) < min_run and i > 0 and j < n:
            f[i:j] = f[i - 1]
        i = j
    return f


def detect_rest(seq, border=DEFAULT_BORDER, low=DEFAULT_LOW, min_run=DEFAULT_MIN_RUN):
    """Ritorna {'l': bool(T,), 'r': bool(T,)} (lato della persona)."""
    b = seq.body
    T = seq.n_frames
    sw = np.linalg.norm(b["l_shoulder"][:, :2] - b["r_shoulder"][:, :2], axis=1)
    sw_med = float(np.nanmedian(sw)) if np.isfinite(sw).any() else np.nan
    out = {}
    for side in ("l", "r"):
        s, e, w = b[side + "_shoulder"], b[side + "_elbow"], b[side + "_wrist"]
        rest = np.zeros(T, dtype=bool)
        missing = ~np.isfinite(w[:, 1]) | ~np.isfinite(e[:, 1])
        rest |= missing
        if not seq.is_3d:
            # coordinate 2D normalizzate sull'altezza: bordo inferiore a y = -1
            bottom = -1.0 + border
            rest |= np.nan_to_num(w[:, 1], nan=-2) <= bottom
            rest |= np.nan_to_num(e[:, 1], nan=-2) <= bottom
        if np.isfinite(sw_med):
            fore = w[:, :2] - e[:, :2]
            vertical = np.abs(fore[:, 0]) < 0.35 * np.abs(fore[:, 1])
            hanging = (w[:, 1] < e[:, 1]) & (e[:, 1] < s[:, 1]) & vertical
            very_low = (s[:, 1] - w[:, 1]) > low * sw_med
            rest |= np.nan_to_num(hanging & very_low, nan=0).astype(bool)
        out[side] = _clean_runs(rest, min_run)
    return out
