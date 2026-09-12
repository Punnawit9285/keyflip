"""Platform dispatch for the tray icon.

Importing this raises ImportError when no tray is available, which the caller
treats as "run in the console instead".
"""

from __future__ import annotations

import sys

if sys.platform == "darwin":
    from .tray_mac import run_tray  # noqa: F401
elif sys.platform == "win32":
    from .tray_win import run_tray  # noqa: F401
else:
    raise ImportError(f"no tray implementation for {sys.platform}")
