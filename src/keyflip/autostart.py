"""Start keyflip at login, toggled from the menu rather than System Settings.

Neither platform needs an installer or admin rights for this, and both put the
entry somewhere the user can find and undo it without keyflip's help: Login
Items on macOS, the Startup tab of Task Manager on Windows.

macOS gets a LaunchAgent plist.  Simply *writing* the file is what enables it -
launchd reads ~/Library/LaunchAgents at login - so there is no launchctl call
to fail, and deleting the file is a complete uninstall.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

LABEL = "com.keyflip.agent"
#: The name of the value under HKCU\...\Run, and of the plist file.
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class AutostartError(RuntimeError):
    """Raised when the entry could not be written or removed."""


def supported() -> bool:
    return sys.platform in ("darwin", "win32")


def launch_command() -> list[str]:
    """How to start keyflip again from scratch.

    A frozen build is its own executable; from source it takes the interpreter
    that is running us, so a login item made from a venv keeps using that venv.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    return [sys.executable, "-m", "keyflip", "run"]


# --------------------------------------------------------------------------
# macOS
# --------------------------------------------------------------------------
def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _mac_is_enabled() -> bool:
    return _plist_path().exists()


def _mac_enable() -> None:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": launch_command(),
        "RunAtLoad": True,
        # A shortcut daemon that respawns in a loop after a crash would be
        # worse than one that stays down until the user opens it again.
        "KeepAlive": False,
    }
    with path.open("wb") as fh:
        plistlib.dump(payload, fh)


def _mac_disable() -> None:
    _plist_path().unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def _win_command_line() -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in launch_command())


def _win_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, "keyflip")
        return True
    except OSError:
        return False


def _win_enable() -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
        winreg.SetValueEx(key, "keyflip", 0, winreg.REG_SZ, _win_command_line())


def _win_disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "keyflip")
    except FileNotFoundError:
        pass  # already gone, which is what was asked for


# --------------------------------------------------------------------------
# public interface
# --------------------------------------------------------------------------
def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_is_enabled()
    if sys.platform == "win32":
        return _win_is_enabled()
    return False


def set_enabled(on: bool) -> None:
    """Turn the login item on or off.  Raises AutostartError if it did not."""
    if not supported():
        raise AutostartError(f"no login item support on {sys.platform}")
    try:
        if sys.platform == "darwin":
            _mac_enable() if on else _mac_disable()
        else:
            _win_enable() if on else _win_disable()
    except OSError as exc:
        raise AutostartError(str(exc)) from exc
