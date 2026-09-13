# -*- coding: utf-8 -*-
from __future__ import absolute_import

import sys

PY2 = sys.version_info[0] == 2

if PY2:
    text_type = unicode
    binary_type = str
    string_types = (basestring,)
else:
    text_type = str
    binary_type = bytes
    string_types = (str,)

try:
    import Tkinter as tk
    import tkFileDialog
except ImportError:
    import tkinter as tk
    from tkinter import filedialog as tkFileDialog

try:
    import ttk
except Exception:
    ttk = None

try:
    import Queue as queue
except Exception:
    import queue
