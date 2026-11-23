#!/bin/sh
# Avvia il controller PepperSign con l'ambiente dell'SDK NAOqi.
set -e

# Percorsi dell'SDK (generati durante la build del container).
. /etc/naoqi.env

export DISPLAY="${DISPLAY:-:99}"

# Attendo che il display virtuale sia pronto prima di aprire la GUI Tkinter.
i=0
while [ ! -e /tmp/.X11-unix/X99 ] && [ "$i" -lt 30 ]; do
    sleep 1
    i=$((i + 1))
done

cd /opt/peppersign
exec python2.7 main.py
