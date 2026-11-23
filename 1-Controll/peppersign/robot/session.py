# -*- coding: utf-8 -*-
"""
Connessione con Pepper: sessione NAOqi, servizi, lock condiviso, log e
monitor della connessione (riconnessione automatica).

RobotSession e' lo stato condiviso da tutti i componenti del controller:
chi deve parlare con il robot usa i servizi e il lock di questo oggetto.
"""
from __future__ import absolute_import

import socket
import threading
import time

from peppersign.config import fake_robot_enabled
from peppersign.utils import safe_unicode, tcp_check


def load_qi(fake):
    """
    Modulo qi da usare: robot simulato (fake_qi.py, modalita' demo) oppure
    SDK NAOqi reale. L'import e' fatto qui e non all'avvio del file, cosi'
    dalla GUI si puo' passare da demo a robot reale senza riavviare.
    """
    if fake:
        from peppersign import fake_qi
        return fake_qi
    import qi
    return qi


def validate_robot_address(ip, port):
    """Ritorna (ok, ip, port, messaggio). Accetta un IP o un nome host."""
    ip = safe_unicode(ip).strip()
    if not ip:
        return False, ip, port, "Indirizzo del robot vuoto"
    if " " in ip or "/" in ip or ":" in ip:
        return False, ip, port, "Indirizzo non valido: %s (scrivi solo l'IP, es. 192.168.0.110)" % ip
    try:
        port = int(safe_unicode(port).strip())
    except Exception:
        return False, ip, port, "Porta non valida: %s" % safe_unicode(port)
    if port < 1 or port > 65535:
        return False, ip, port, "Porta fuori intervallo: %d" % port
    try:
        socket.getaddrinfo(str(ip), port)
    except Exception:
        return False, ip, port, "Indirizzo non risolvibile: %s" % ip
    return True, ip, port, ""


# Servizi NAOqi usati dal controller, nell'ordine in cui vengono aperti.
# (attributo, nome del servizio, obbligatorio)
SERVICES = [
    ("tts", "ALTextToSpeech", True),
    ("audio_device", "ALAudioDevice", False),
    ("animated_speech", "ALAnimatedSpeech", False),
    ("speaking_movement", "ALSpeakingMovement", False),
    ("recorder", "ALAudioRecorder", True),
    ("fileman", "ALFileManager", True),
    ("motion", "ALMotion", True),
    ("basic_awareness", "ALBasicAwareness", True),
    ("autonomous_life", "ALAutonomousLife", False),
    ("behavior", "ALBehaviorManager", False),
    ("anim_player", "ALAnimationPlayer", False),
    ("background_movement", "ALBackgroundMovement", False),
    ("listening_movement", "ALListeningMovement", False),
    ("autonomous_blinking", "ALAutonomousBlinking", False),
    ("memory", "ALMemory", False),
]
SERVICE_ATTRS = [attr for attr, _, _ in SERVICES]


# Attesa massima (s) della fine del comando in corso prima di chiudere o
# sostituire la sessione (riconnessione manuale, cambio robot, disconnessione).
SESSION_SWAP_WAIT = 15.0


class _NotConnected(object):
    """Servizio segnaposto quando non c'e' una sessione: e' 'falso' e ogni chiamata da' errore."""

    def __init__(self, name):
        self._name = name

    def __nonzero__(self):
        return False
    __bool__ = __nonzero__

    def __getattr__(self, method):
        if method.startswith("_"):
            raise AttributeError(method)
        raise RuntimeError("Robot non connesso (%s.%s)" % (self._name, method))


class _Services(object):
    """Sessione NAOqi e servizi di UNA connessione: vengono sostituiti tutti insieme."""

    def __init__(self, session=None, services=None, generation=0):
        self.session = session
        self.generation = generation
        services = services or {}
        for attr, name, _ in SERVICES:
            value = services.get(attr)
            setattr(self, attr, value if value is not None else _NotConnected(name))


class RobotSession(object):
    """
    Sessione NAOqi, servizi, lock e stato della connessione, condivisi dai componenti.

    Due lock, sempre presi in quest'ordine:
      connection_lock  un solo cambio di sessione alla volta (connessione,
                       disconnessione, cambio robot), da qualunque thread arrivi
      lock             i comandi che usano il robot; la sessione viene chiusa o
                       sostituita solo tenendo anche questo, quindi mai a meta' di un comando
    I servizi (motion, tts, ...) stanno in un unico oggetto _Services che viene
    sostituito con una sola assegnazione: nessun thread vede un misto di vecchia
    e nuova sessione. Un servizio opzionale assente vale None, come prima.
    """

    def __init__(self, config, log_cb=None):
        self.config = config
        self.log_cb = log_cb

        self.robot_ip = config["robot"]["ip"]
        self.robot_port = config["robot"]["port"]

        # Robot simulato (demo) o reale: modificabile dalla GUI (set_target)
        self.fake_robot = fake_robot_enabled()
        self.qi = load_qi(self.fake_robot)

        self.lock = threading.Lock()
        self.connection_lock = threading.RLock()
        self._current = _Services()
        self._generation = 0

        self.last_error = ""
        self.running = True
        self._warned = set()          # chiavi gia' segnalate da warn_once
        self._reports = {}            # chiave -> [ultima scrittura, ripetizioni non scritte]
        self._log_lock = threading.Lock()

        # Stato della connessione con il robot (aggiornato dal ConnectionMonitor).
        # La GUI legge solo questi valori in cache: non chiama mai il robot
        # dal thread grafico, cosi' la finestra non si blocca.
        self.robot_connected = False
        self.connection_state = "NON CONNESSO"

    # ------------------------------------------------------------ log
    def log(self, message):
        if self.log_cb:
            try:
                self.log_cb(message)
                return
            except Exception:
                pass
        print message

    def set_error(self, message):
        self.last_error = safe_unicode(message)
        if self.last_error:
            self.log("[ERR] %s" % self.last_error)

    def warn_once(self, key, message):
        """
        Scrive `message` nel log solo la prima volta per `key`. Per le API di NAOqi
        che possono mancare su alcune versioni di Pepper: si usa un'alternativa e
        lo si dice una volta, senza riempire il log.
        """
        if not self.alive(check_tcp=False):
            # sessione appena caduta: l'errore e' della connessione, non dell'API.
            # Lo scrivo con la limitazione e non segno l'avviso come gia' dato.
            self.report("disconnected:" + key, message + " (sessione con il robot non attiva)")
            return
        with self._log_lock:
            if key in self._warned:
                return
            self._warned.add(key)
        self.log(message)

    def report(self, key, message, every=30.0):
        """
        Errore che puo' ripetersi (es. a ogni lettura del monitor): nel log al massimo
        una volta ogni `every` secondi per `key`, con il numero di ripetizioni intanto.
        """
        now = time.time()
        with self._log_lock:
            entry = self._reports.get(key)
            if entry is not None and now - entry[0] < every:
                entry[1] += 1
                return
            skipped = entry[1] if entry is not None else 0
            self._reports[key] = [now, 0]
        if skipped:
            message = "%s (ripetuto altre %d volte)" % (message, skipped)
        self.log(message)

    @property
    def is_fake(self):
        return getattr(self.qi, "IS_FAKE", False)

    # ------------------------------------------------------------ sessione
    @property
    def session(self):
        return self._current.session

    @property
    def generation(self):
        """Numero della connessione attuale: cambia a ogni apertura o chiusura della sessione."""
        return self._current.generation

    def _build(self):
        """Apre una nuova sessione NAOqi e recupera i servizi, senza ancora installarli."""
        session = self.qi.Session()
        if self.is_fake:
            # I comandi ricevuti dal robot simulato compaiono nel log della GUI.
            session.set_logger(self.log)
        session.connect("tcp://%s:%s" % (self.robot_ip, self.robot_port))
        services = {}
        for attr, name, required in SERVICES:
            if required:
                services[attr] = session.service(name)
            else:
                services[attr] = self._try_service(session, name)
        return session, services

    def _try_service(self, session, service_name):
        try:
            return session.service(service_name)
        except Exception as exc:
            self.log("[WARN] Servizio non disponibile %s: %s" % (service_name, str(exc)))
            return None

    def _acquire_commands(self, wait):
        """Prende il lock dei comandi aspettando al massimo `wait` secondi; True se preso."""
        deadline = time.time() + float(wait)
        while True:
            if self.lock.acquire(False):
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.05)

    def _swap(self, session, services, reason):
        """Installa i nuovi servizi (o nessuno) e chiude la sessione precedente, mai a meta' di un comando."""
        with self.connection_lock:
            acquired = self._acquire_commands(SESSION_SWAP_WAIT)
            if not acquired:
                self.log("[ROBOT] Comando in corso da oltre %d s: %s comunque" % (int(SESSION_SWAP_WAIT), reason))
            try:
                old = self._current
                self._generation += 1
                self._current = _Services(session, services, self._generation)
                if old.session is not None:
                    try:
                        old.session.close()
                    except Exception:
                        pass        # sessione gia' caduta: non c'e' altro da chiudere
            finally:
                if acquired:
                    self.lock.release()

    def open(self):
        """Nuova sessione: i servizi vengono preparati a parte e poi sostituiti tutti insieme."""
        with self.connection_lock:
            session, services = self._build()
            self._swap(session, services, "sostituisco la sessione")

    def close(self):
        """Chiude la sessione attuale (dopo la fine del comando in corso)."""
        with self.connection_lock:
            if self._current.session is None:
                return
            self._swap(None, None, "chiudo la sessione")

    def safe_call(self, service, method_name, label, *args):
        """
        Esegue una chiamata opzionale a un servizio NAOqi senza bloccare il
        programma se il servizio/metodo non esiste su quella versione di Pepper.
        """
        if not service:
            self.log("[AUTO] %s non disponibile" % label)
            return False

        try:
            method = getattr(service, method_name)
            method(*args)
            self.log("[AUTO] %s OK" % label)
            return True
        except Exception as exc:
            self.log("[AUTO] %s FAIL: %s" % (label, str(exc)))
            return False

    def alive(self, check_tcp):
        session = self.session
        try:
            if session is None or not session.isConnected():
                return False
        except Exception:
            return False
        if check_tcp and not self.is_fake:
            return tcp_check(self.robot_ip, self.robot_port, timeout=2)
        return True

    def set_target(self, fake, qi_module, ip, port):
        """Nuovo robot di destinazione (da usare a sessione chiusa)."""
        with self.connection_lock:
            self.fake_robot = fake
            self.qi = qi_module
            self.robot_ip = ip
            self.robot_port = port
            self.config["robot"]["ip"] = ip
            self.config["robot"]["port"] = port


def _service_property(attr):
    def getter(self):
        value = getattr(self._current, attr)
        # i servizi opzionali assenti si leggono come None (come prima del refactor)
        return None if isinstance(value, _NotConnected) and self._current.session is not None else value
    return property(getter)


for _attr in SERVICE_ATTRS:
    setattr(RobotSession, _attr, _service_property(_attr))
del _attr


class ConnectionMonitor(object):
    """
    Monitor della connessione: rileva la disconnessione del robot, aggiorna i
    valori di stato in cache e riconnette automaticamente.
    Gira in un thread separato (avviato da main.py tramite PepperController.monitor_loop).

    hooks: dict con le funzioni dei componenti
        connect()            nuova connessione completa (PepperController.connect)
        refresh_status()     stato di Autonomous Life e volume
        refresh_temperatures(), refresh_obstacles(), refresh_protections()
        on_disconnect()      azzera le cache dei componenti e ferma le braccia morbide
    """

    TEMPERATURE_PERIOD_TICKS = 3        # lettura ogni ~3 s

    def __init__(self, robot, hooks):
        self.robot = robot
        self.hooks = hooks
        self.reconnect_interval = float(robot.config["robot"].get("reconnect_interval", 5))
        self.wake_event = threading.Event()
        self.reconnect_requested = False
        self.reconnect_failures = 0

    def mark_disconnected(self, reason, as_error=True):
        robot = self.robot
        with robot.connection_lock:
            was_connected = robot.robot_connected
            self.hooks["on_disconnect"]()
            robot.robot_connected = False
            robot.connection_state = "DISCONNESSO"
            robot.close()
        if was_connected and as_error:
            robot.set_error("Connessione con il robot persa (%s). Riconnessione automatica attiva." % reason)

    def try_reconnect(self):
        robot = self.robot
        if not robot.is_fake and not tcp_check(robot.robot_ip, robot.robot_port, timeout=2):
            self.reconnect_failures += 1
            robot.connection_state = "DISCONNESSO - nuovo tentativo ogni %d s" % int(self.reconnect_interval)
            if self.reconnect_failures == 1 or self.reconnect_failures % 12 == 0:
                robot.log("[ROBOT] Pepper non raggiungibile su %s:%d, riprovo..." % (robot.robot_ip, robot.robot_port))
            return False
        try:
            with robot.connection_lock:
                self.hooks["connect"]()
            robot.log("[ROBOT] Riconnessione riuscita.")
            robot.last_error = ""
            return True
        except Exception as exc:
            self.reconnect_failures += 1
            robot.robot_connected = False
            robot.connection_state = "DISCONNESSO - nuovo tentativo ogni %d s" % int(self.reconnect_interval)
            if self.reconnect_failures == 1 or self.reconnect_failures % 12 == 0:
                robot.log("[ROBOT] Riconnessione fallita: %s" % str(exc))
            return False

    def request_reconnect(self, manual=True):
        """Forza una nuova connessione (pulsante 'Riconnetti ora' della GUI)."""
        if manual:
            self.reconnect_requested = True
        self.reconnect_failures = 0
        self.wake_event.set()

    def wake(self):
        self.wake_event.set()

    def _refresh(self, hook, label):
        """Una lettura del monitor: un errore non ferma il monitor ma finisce nel log (con limitazione)."""
        try:
            self.hooks[hook]()
        except Exception as exc:
            self.robot.report("monitor:" + hook, "[MONITOR] Lettura di %s non riuscita: %s" % (label, exc))

    def loop(self):
        robot = self.robot
        tick = 0
        while robot.running:
            tick += 1
            if self.reconnect_requested:
                self.reconnect_requested = False
                robot.log("[ROBOT] Riconnessione richiesta dall'utente...")
                self.mark_disconnected("riconnessione manuale", as_error=False)
                self.reconnect_failures = 0
            if robot.robot_connected:
                if robot.alive(check_tcp=(tick % 3 == 0)):
                    self._refresh("refresh_status", "stato e volume")
                    if tick % self.TEMPERATURE_PERIOD_TICKS == 1:
                        self._refresh("refresh_temperatures", "temperature")
                    self._refresh("refresh_obstacles", "ostacoli")
                    if tick % 5 == 2:
                        self._refresh("refresh_protections", "protezioni")
                    wait = 1.0
                else:
                    robot.log("[ROBOT] Connessione con Pepper persa.")
                    self.mark_disconnected("sessione NAOqi chiusa")
                    wait = 1.0
            else:
                self.try_reconnect()
                wait = 1.0 if robot.robot_connected else self.reconnect_interval
            self.wake_event.wait(wait)
            self.wake_event.clear()
