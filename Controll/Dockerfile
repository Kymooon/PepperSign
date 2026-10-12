# ==========================================================
# PepperSign - Controll (Python 2.7 + NAOqi + GUI Tkinter)
#
# La GUI Tkinter gira su un display virtuale (Xvfb) ed e'
# visibile da browser tramite noVNC:  http://<host>:6080
#
# PREREQUISITO: l'SDK Python di NAOqi per Linux 64 bit
# (pynaoqi-python2.7-2.5.x-linux64.tar.gz) va copiato in
# Controll/docker/sdk/  (vedi docker/sdk/README.md).
# ==========================================================
FROM ubuntu:18.04

ARG NOVNC_VERSION=1.4.0
ARG WEBSOCKIFY_VERSION=0.10.0

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Rome \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Python 2.7 + Tkinter, display virtuale, server VNC, window manager.
# python3 serve solo a websockify (il ponte WebSocket <-> VNC per noVNC).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python2.7 python-tk libpython2.7 \
        xvfb x11vnc fluxbox supervisor python3 \
        fonts-dejavu-core ca-certificates curl procps \
 && rm -rf /var/lib/apt/lists/*

# Client web noVNC (versione recente dal rilascio ufficiale su GitHub).
RUN mkdir -p /opt/novnc \
 && curl -fsSL "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" \
    | tar -xz -C /opt/novnc --strip-components=1 \
 && ln -s /opt/novnc/vnc.html /opt/novnc/index.html

# websockify recente: il pacchetto di Ubuntu 18.04 (0.8) e' incompatibile con
# noVNC >= 1.0 e rifiuta la connessione ("Impossibile connettersi al server").
RUN mkdir -p /opt/websockify \
 && curl -fsSL "https://github.com/novnc/websockify/archive/refs/tags/v${WEBSOCKIFY_VERSION}.tar.gz" \
    | tar -xz -C /opt/websockify --strip-components=1 \
 && cd /opt/websockify && python3 -c "import websockify; print('websockify OK')"

# ---- SDK NAOqi ----
# Estraggo l'archivio, individuo automaticamente la cartella che contiene il
# modulo "qi" e quelle con le librerie .so, e verifico subito che "import qi"
# funzioni: se l'SDK manca o e' sbagliato la build si ferma con un messaggio chiaro.
COPY docker/sdk/ /tmp/sdk/
RUN set -e; \
    sdk="$(ls /tmp/sdk/pynaoqi-python2.7-*linux64*.tar.gz 2>/dev/null | head -n1 || true)"; \
    if [ -z "$sdk" ]; then \
        echo ""; \
        echo "ERRORE: SDK NAOqi non trovato in Controll/docker/sdk/"; \
        echo "Copia li' il file pynaoqi-python2.7-2.5.x-linux64.tar.gz (vedi docker/sdk/README.md)"; \
        echo ""; \
        exit 1; \
    fi; \
    echo "Uso SDK: $sdk"; \
    mkdir -p /opt/naoqi; \
    tar -xzf "$sdk" -C /opt/naoqi --strip-components=1; \
    qi_init="$(find /opt/naoqi -path '*/qi/__init__.py' | head -n1)"; \
    [ -n "$qi_init" ] || { echo "ERRORE: modulo qi non trovato nell'SDK"; exit 1; }; \
    site_dir="$(dirname "$(dirname "$qi_init")")"; \
    lib_dirs="$(find /opt/naoqi -name '*.so*' -printf '%h\n' | sort -u | tr '\n' ':')"; \
    printf 'export PYTHONPATH="%s${PYTHONPATH:+:$PYTHONPATH}"\nexport LD_LIBRARY_PATH="%s${LD_LIBRARY_PATH}"\n' \
        "$site_dir" "$lib_dirs" > /etc/naoqi.env; \
    cat /etc/naoqi.env; \
    . /etc/naoqi.env && python2.7 -c "import qi; print('NAOqi SDK OK: ' + qi.__file__)"; \
    rm -rf /tmp/sdk

# ---- Applicazione ----
WORKDIR /opt/peppersign
COPY main.py config.example.json ./
COPY peppersign/ ./peppersign/
COPY docker/supervisord.conf /etc/supervisor/conf.d/peppersign.conf
COPY docker/run-controller.sh docker/start-vnc.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/run-controller.sh /usr/local/bin/start-vnc.sh \
 && chmod +x /usr/local/bin/run-controller.sh /usr/local/bin/start-vnc.sh \
 && find /opt/peppersign -name '*.pyc' -delete \
 && mkdir -p /data/gestures

# Valori di default (sovrascrivibili da .env / docker-compose).
ENV PEPPERSIGN_ROBOT_PORT=9559 \
    PEPPERSIGN_WEBAPP_URL=http://web:8080/PepperSign \
    PEPPERSIGN_GESTURE_DIR=/data/gestures \
    PEPPERSIGN_ROBOT_WAIT=86400 \
    SCREEN_GEOMETRY=1280x800x24 \
    VNC_PASSWORD=

VOLUME ["/data/gestures"]
EXPOSE 6080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
