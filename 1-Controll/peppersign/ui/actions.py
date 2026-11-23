# -*- coding: utf-8 -*-
"""
Comandi semplici della finestra: un pulsante chiama un metodo del controller in
un thread separato e scrive il messaggio di ritorno nel log.

Ogni riga della tabella diventa un metodo on_<nome> di PepperGUI (install_actions):
aggiungere un comando di questo tipo vuol dire aggiungere una riga, non un metodo.
"""
from __future__ import absolute_import

from peppersign.utils import safe_unicode


class Action(object):
    def __init__(self, handler, method, args=(), log="%s"):
        self.handler = handler      # nome del metodo della GUI (es. "on_free_arms")
        self.method = method        # metodo del controller
        self.args = tuple(args)     # argomenti fissi
        self.log = log              # riga di log; %s = messaggio restituito dal controller


SIMPLE_ACTIONS = [
    # Rigidita' dei motori durante la registrazione
    Action("on_free_arms", "free_arms", log="[STIFF] %s"),
    Action("on_hold_arms", "hold_arms", log="[STIFF] %s"),
    Action("on_free_left_arm", "free_left_arm", log="[STIFF] %s"),
    Action("on_hold_left_arm", "hold_left_arm", log="[STIFF] %s"),
    Action("on_free_right_arm", "free_right_arm", log="[STIFF] %s"),
    Action("on_hold_right_arm", "hold_right_arm", log="[STIFF] %s"),
    Action("on_move_only_left_arm", "move_only_left_arm", log="[STIFF] %s"),
    Action("on_move_only_right_arm", "move_only_right_arm", log="[STIFF] %s"),
    Action("on_free_head", "free_head", log="[STIFF] %s"),
    Action("on_hold_head", "hold_head", log="[STIFF] %s"),
    # Mani
    Action("on_open_left_hand", "open_hand", ("LHand",), log="[HAND] %s"),
    Action("on_close_left_hand", "close_hand", ("LHand",), log="[HAND] %s"),
    Action("on_open_right_hand", "open_hand", ("RHand",), log="[HAND] %s"),
    Action("on_close_right_hand", "close_hand", ("RHand",), log="[HAND] %s"),
    Action("on_open_both_hands", "open_both_hands", log="[HAND] %s"),
    Action("on_close_both_hands", "close_both_hands", log="[HAND] %s"),
    # Autonomous Life e volume
    Action("on_life_on", "set_autonomous_life", (True,), log="[CMD] LIFE ON -> %s"),
    Action("on_life_off", "set_autonomous_life", (False,), log="[CMD] LIFE OFF -> %s"),
    Action("on_volume_up", "volume_up", log="[VOLUME] %s"),
    Action("on_volume_down", "volume_down", log="[VOLUME] %s"),
]


def _make_handler(action):
    def handler(self):
        def run():
            ok, message = getattr(self.ctrl, action.method)(*action.args)
            self.enqueue_log(action.log % safe_unicode(message))
        self.run_async(run)
    handler.__name__ = action.handler
    handler.__doc__ = "Pulsante: controller.%s%r, esito nel log." % (action.method, action.args)
    return handler


def install_actions(cls, actions=SIMPLE_ACTIONS):
    """Aggiunge alla classe della GUI un metodo on_<nome> per ogni comando della tabella."""
    for action in actions:
        if hasattr(cls, action.handler):
            raise ValueError("Comando gia' definito: %s" % action.handler)
        setattr(cls, action.handler, _make_handler(action))
