"""Windows backend: the shortcut, and SendInput for copy/paste.

Chords go through RegisterHotKey, which asks the window manager to reserve one
combination: nothing else is touched, and if another program already owns the
chord we are told at startup rather than silently fighting over it.

A double tap cannot be registered - RegisterHotKey has no way to express "this
modifier, twice, on its own" - so it needs a WH_KEYBOARD_LL hook, which puts
this process in the delivery path of every keystroke on the machine.  That is
the cost of the gesture, and it is why the hook is installed only when a tap
is actually configured, and why its callback does nothing but compare a
virtual-key code against a small dict before handing the key straight on.
Anything slower shows up as input lag everywhere, and a callback that overruns
LowLevelHooksTimeout gets silently unhooked by Windows.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from typing import Callable

from .hotkey import DoubleTap, Hotkey, TapDetector

PLATFORM = "win32"

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

VK_CONTROL, VK_MENU, VK_SHIFT = 0x11, 0x12, 0x10
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_C, VK_V = 0x43, 0x56
_MODIFIER_VKS = (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
_KEY_DOWN_MESSAGES = (WM_KEYDOWN, WM_SYSKEYDOWN)
LLKHF_INJECTED = 0x10

#: Stamped into dwExtraInfo so we can recognise our own synthetic input.
_SYNTHETIC_MARK = 0x4B46  # "KF"

# Win32 LONG and DWORD stay 32-bit even on x64 (LLP64), so every field below
# uses an explicit width.  The natural-looking ctypes.c_long is 64-bit on an
# LP64 host, which mis-sizes INPUT and makes SendInput reject the call.
ULONG_PTR = ctypes.c_size_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16),
                ("wParamH", ctypes.c_uint16)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", ctypes.c_uint32), ("scanCode", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ULONG_PTR)]


#: The callback Windows itself calls, so it has to use the stdcall convention
#: where that is a distinct thing.  CFUNCTYPE off Windows only exists so this
#: module still imports (and its struct layout still tests) on any host.
_HOOKPROC = (ctypes.WINFUNCTYPE if sys.platform == "win32" else ctypes.CFUNCTYPE)(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_void_p
)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint32),
                ("wParam", ULONG_PTR), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint32), ("pt", POINT)]


_user32 = None
_kernel32 = None


def _dlls():
    """Bind lazily so this module can be imported (and unit-tested) anywhere."""
    global _user32, _kernel32
    if _user32 is None:
        if sys.platform != "win32":
            raise OSError("backend_win only runs on Windows")
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _user32.SendInput.argtypes = (ctypes.c_uint32,
                                      ctypes.POINTER(INPUT), ctypes.c_int)
        _user32.SendInput.restype = ctypes.c_uint32
        _user32.GetMessageW.argtypes = (ctypes.POINTER(MSG), ctypes.c_void_p,
                                        ctypes.c_uint32, ctypes.c_uint32)
        _user32.RegisterHotKey.argtypes = (ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_uint32, ctypes.c_uint32)
        _user32.GetClipboardData.restype = ctypes.c_void_p
        _user32.SetClipboardData.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
        _user32.SetClipboardData.restype = ctypes.c_void_p
        _kernel32.GlobalAlloc.restype = ctypes.c_void_p
        _kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
        _kernel32.GlobalLock.restype = ctypes.c_void_p
        _kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
        _kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
        _user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC,
                                              ctypes.c_void_p, ctypes.c_uint32)
        _user32.SetWindowsHookExW.restype = ctypes.c_void_p
        _user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
        _user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_size_t, ctypes.c_void_p)
        _user32.CallNextHookEx.restype = ctypes.c_ssize_t
        _kernel32.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
        _kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    return _user32, _kernel32


# --------------------------------------------------------------------------
# permissions (Windows needs none, but keep the interface identical)
# --------------------------------------------------------------------------
PERMISSION_HELP = (
    "Windows does not gate global hotkeys, but a shortcut pressed while an\n"
    "elevated window has focus only reaches an elevated program.  If keyflip\n"
    "seems dead in one specific app, run keyflip as administrator too."
)


def has_accessibility(prompt: bool = False) -> bool:
    return True


def wait_for_accessibility(timeout_s: float = 300.0, poll_s: float = 0.5) -> bool:
    return True


def can_tap() -> bool:
    return True


# --------------------------------------------------------------------------
# clipboard
# --------------------------------------------------------------------------
def clipboard_serial() -> int:
    user32, _ = _dlls()
    return int(user32.GetClipboardSequenceNumber())


def _open_clipboard(attempts: int = 12) -> None:
    """The clipboard is a single global lock; other apps hold it briefly."""
    user32, _ = _dlls()
    for i in range(attempts):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.01 * (i + 1))   # 10ms, 20ms, ... ~0.8s total
    raise OSError("could not open the clipboard - another app is holding it")


def clipboard_get() -> str | None:
    user32, kernel32 = _dlls()
    _open_clipboard()
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def clipboard_set(text: str) -> None:
    user32, kernel32 = _dlls()
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not handle:
        raise OSError("GlobalAlloc failed")
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        raise OSError("GlobalLock failed")
    ctypes.memmove(ptr, ctypes.byref(data), size)
    kernel32.GlobalUnlock(handle)

    _open_clipboard()
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        # On success the system owns the handle; do not free it.
    finally:
        user32.CloseClipboard()


# --------------------------------------------------------------------------
# synthetic input
# --------------------------------------------------------------------------
def _key_event(vk: int, up: bool) -> INPUT:
    ev = INPUT()
    ev.type = INPUT_KEYBOARD
    ev.ki = _KEYBDINPUT(wVk=vk, wScan=0,
                        dwFlags=KEYEVENTF_KEYUP if up else 0,
                        time=0, dwExtraInfo=_SYNTHETIC_MARK)
    return ev


def _send_ctrl_chord(vk: int) -> None:
    user32, _ = _dlls()
    events = (INPUT * 4)(
        _key_event(VK_CONTROL, False),
        _key_event(vk, False),
        _key_event(vk, True),
        _key_event(VK_CONTROL, True),
    )
    sent = user32.SendInput(4, events, ctypes.sizeof(INPUT))
    if sent != 4:
        raise ctypes.WinError(ctypes.get_last_error())


def send_copy() -> None:
    _send_ctrl_chord(VK_C)


def send_paste() -> None:
    _send_ctrl_chord(VK_V)


def modifiers_down() -> bool:
    user32, _ = _dlls()
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIER_VKS)


def wait_modifiers_released(timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if not modifiers_down():
            time.sleep(0.02)
            return True
        time.sleep(0.01)
    return False


def notify(title: str, message: str) -> None:
    # Toasts need a registered AppUserModelID; the tray balloon covers it when
    # a tray icon is running, and there is nothing worth doing otherwise.
    pass


# --------------------------------------------------------------------------
# hotkey listener
# --------------------------------------------------------------------------
class HotkeyListener:
    def __init__(self, bindings: list[tuple[Hotkey | DoubleTap, Callable[[], None]]]):
        self._chords = [(b, fn) for b, fn in bindings if not isinstance(b, DoubleTap)]
        #: virtual-key code -> (detector, handler)
        self._by_tap: dict[int, tuple[TapDetector, Callable[[], None]]] = {
            b.win_vk(): (TapDetector(b.window_ms), fn)
            for b, fn in bindings if isinstance(b, DoubleTap)
        }
        self._handlers: dict[int, Callable[[], None]] = {}
        self._thread_id: int | None = None
        self._busy = threading.Event()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._hook = None
        # Windows keeps only the raw pointer, so the wrapper has to outlive
        # the call that installs it or the callback lands in freed memory.
        self._hook_proc = _HOOKPROC(self._on_hook) if self._by_tap else None

    def install(self) -> None:
        """No-op: registration happens inside run_forever().

        With a NULL window handle WM_HOTKEY is posted to the queue of the
        thread that called RegisterHotKey, and a WH_KEYBOARD_LL callback is
        run by the thread that installed it while it pumps messages - so
        registering, hooking and pumping all have to happen on one thread.
        """

    def run_forever(self) -> None:
        user32, kernel32 = _dlls()
        self._thread_id = kernel32.GetCurrentThreadId()
        registered: list[int] = []
        try:
            for index, (hk, fn) in enumerate(self._chords, start=1):
                if not user32.RegisterHotKey(None, index, hk.win_mods(), hk.win_vk()):
                    err = ctypes.get_last_error()
                    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
                        raise OSError(
                            f"another program already owns {hk.pretty('win32')}. "
                            f"Pick a different shortcut with:  keyflip hotkey <combo>"
                        )
                    raise ctypes.WinError(err)
                self._handlers[index] = fn
                registered.append(index)
            if self._hook_proc is not None:
                self._hook = user32.SetWindowsHookExW(
                    WH_KEYBOARD_LL, self._hook_proc,
                    kernel32.GetModuleHandleW(None), 0,
                )
                if not self._hook:
                    raise ctypes.WinError(ctypes.get_last_error())
            self._ready.set()

            msg = MSG()
            while True:
                got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if got in (0, -1):
                    break
                if msg.message == WM_HOTKEY:
                    handler = self._handlers.get(int(msg.wParam))
                    if handler:
                        self._fire(handler)
        finally:
            self._ready.set()
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
            for index in registered:
                user32.UnregisterHotKey(None, index)

    # -- the hot path ------------------------------------------------------
    def _on_hook(self, ncode, wparam, lparam):
        """Every keystroke on the machine passes through here.  Keep it cheap."""
        try:
            if ncode == HC_ACTION:
                info = ctypes.cast(lparam,
                                   ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                # Skip the copy/paste keys we send ourselves, and anything
                # else injected - only real fingers count as a tap.
                if not (info.flags & LLKHF_INJECTED) and \
                        info.dwExtraInfo != _SYNTHETIC_MARK:
                    self._key_event(int(info.vkCode), int(wparam))
        except Exception:  # never let an exception escape into Windows
            pass
        return _user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _key_event(self, vk: int, message: int) -> None:
        down = message in _KEY_DOWN_MESSAGES
        entry = self._by_tap.get(vk)
        if entry is None:
            if down:
                # Any other key means the user is typing, not tapping.
                for detector, _ in self._by_tap.values():
                    detector.interrupted()
            return
        detector, handler = entry
        now = time.monotonic()
        if down:
            detector.press(now)
        elif detector.release(now):
            # On the key-up, not the second key-down: see TapDetector.  Fired
            # while shift is held, the copy lands as Ctrl+Shift+C.
            self._fire(handler)

    def _fire(self, handler: Callable[[], None]) -> None:
        if self._busy.is_set():
            return
        self._busy.set()
        threading.Thread(target=self._run, args=(handler,), daemon=True).start()

    def _run(self, handler: Callable[[], None]) -> None:
        try:
            handler()
        except Exception as exc:
            print(f"keyflip: {exc!r}")
        finally:
            self._busy.clear()

    def stop(self) -> None:
        if self._thread_id is not None:
            user32, _ = _dlls()
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
