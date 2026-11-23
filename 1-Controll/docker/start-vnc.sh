#!/bin/sh
# Avvia il server VNC sul display virtuale.
# Se VNC_PASSWORD e' impostata, noVNC la chiedera' all'apertura.
set -e

i=0
while [ ! -e /tmp/.X11-unix/X99 ] && [ "$i" -lt 30 ]; do
    sleep 1
    i=$((i + 1))
done

if [ -n "$VNC_PASSWORD" ]; then
    mkdir -p /root/.vnc
    x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd >/dev/null 2>&1
    exec x11vnc -display :99 -forever -shared -rfbport 5900 -localhost -rfbauth /root/.vnc/passwd -quiet
fi

exec x11vnc -display :99 -forever -shared -rfbport 5900 -localhost -nopw -quiet
