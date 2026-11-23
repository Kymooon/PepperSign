# -*- coding: utf-8 -*-
"""
Componenti interni del controller di Pepper.

PepperController (peppersign/controller.py) resta l'unico punto d'accesso per
GUI, main.py e WebApp: crea questi componenti e delega a loro. Ogni componente
riceve la RobotSession condivisa (connessione, servizi NAOqi, lock, log).

    session.py        RobotSession, ConnectionMonitor, load_qi, validate_robot_address
    joints.py         liste dei giunti, limiti, clamp, validazione dei frame
    interpolation.py  frame -> times/angles, durata dei frame, finestre senza anti-collisione
    collision.py      anti-collisione tra le braccia spenta durante parti del gesto
    autonomy.py       Autonomous Life e movimenti autonomi (anche durante i gesti)
    safety.py         temperature, ostacoli, protezioni, rallentamenti
    recording.py      stiffness, mani, pose, braccia morbide, preparazione della registrazione
    player.py         esecuzione dei gesti
    speech.py         voce, volume, registrazione audio
    webapp.py         polling dei comandi della WebApp
"""
