"""macOS backend: a CGEventTap for the hotkey, CGEvents for copy/paste.

The tap is the only part of this program that sees every keystroke on the
system, so it does as little as possible: compare two integers, and either
hand the event straight back or swallow it and wake a worker thread.  Anything
slower would make every key in every application feel sticky, and a tap that
overruns its deadline gets torn down by the window server anyway.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Callable

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString
from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)

from .hotkey import MAC_FLAG_MASK, DoubleTap, Hotkey, TapDetector

PLATFORM = "darwin"

#: Stamped onto every event we synthesise so our own tap can skip it.
_SYNTHETIC_MARK = 0x4B46  # "KF"

_KEYCODE_C = 8
_KEYCODE_V = 9
_MASK_CMD = 1 << 20

_TAP_DISABLED = (
    Quartz.kCGEventTapDisabledByTimeout,
    Quartz.kCGEventTapDisabledByUserInput,
)


# --------------------------------------------------------------------------
# permissions
# --------------------------------------------------------------------------
def has_accessibility(prompt: bool = False) -> bool:
    """True when this process may tap the keyboard and synthesise events."""
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))


PERMISSION_HELP = (
    "keyflip needs Accessibility permission to read your shortcut and to send\n"
    "the copy/paste keystrokes.\n\n"
    "  System Settings -> Privacy & Security -> Accessibility\n"
    "  and switch on the app you launched keyflip from\n"
    "  (keyflip.app, or your terminal if you are running it from source).\n\n"
    "If it is already listed, toggle it off and on again - macOS caches the\n"
    "old answer whenever the binary changes."
)


_ACCESSIBILITY_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)


def wait_for_accessibility(timeout_s: float = 300.0, poll_s: float = 0.5) -> bool:
    """Block until the user grants the permission, or give up.

    The grant lands while we are sitting here, so there is no reason to make
    anyone open the app a second time - which is the step people miss, because
    nothing on screen says the first launch is now a dead process.

    The run loop has to keep turning while we wait: the user is in System
    Settings for a minute or two, and a GUI process that never pumps gets the
    spinning wheel and an "application not responding" report.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if has_accessibility():
            return True
        started = time.monotonic()
        Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, poll_s, False)
        # With no sources attached the run loop returns at once; do not spin.
        idle = poll_s - (time.monotonic() - started)
        if idle > 0:
            time.sleep(idle)
    return has_accessibility()


def can_tap() -> bool:
    """Is an event tap actually installable right now?

    Being trusted and being able to tap are not quite the same thing - the
    window server can still refuse - and a tap that fails inside the listener
    thread would only reach a stderr nobody is reading.  Ask up front instead.
    """
    probe = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
        lambda proxy, type_, event, refcon: event,
        None,
    )
    if not probe:
        return False
    Quartz.CGEventTapEnable(probe, False)
    return True


def _alert(title: str, body: str, buttons: tuple[str, ...]) -> int:
    """A modal alert from a process with no windows.  Returns the button index."""
    from AppKit import (
        NSAlert,
        NSAlertFirstButtonReturn,
        NSApplication,
        NSApplicationActivationPolicyRegular,
    )

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    app.activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(body)
    for label in buttons:
        alert.addButtonWithTitle_(label)
    return int(alert.runModal()) - int(NSAlertFirstButtonReturn)


def show_permission_alert() -> bool:
    """Explain the missing permission on screen, for a Finder launch.

    Double-clicking the app and having it vanish is the worst possible
    outcome: stderr goes nowhere, so without this the user sees nothing at all.
    Returns True if they asked to be taken to the settings pane.
    """
    from AppKit import NSWorkspace
    from Foundation import NSURL

    chosen = _alert(
        "keyflip needs Accessibility permission",
        "keyflip reads its keyboard shortcut and sends the copy and paste "
        "keystrokes, so macOS requires Accessibility access.\n\n"
        "Turn on keyflip under Privacy & Security \u203a Accessibility. "
        "keyflip will start by itself as soon as you do - there is no need to "
        "open it again.",
        ("Open Accessibility Settings", "Quit"),
    )
    if chosen != 0:
        return False
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(_ACCESSIBILITY_PANE))
    return True


def show_reopen_alert() -> None:
    """The grant landed but the tap was still refused - only a restart fixes it."""
    _alert(
        "Please open keyflip again",
        "The permission is granted, but macOS is still holding the old answer "
        "for this copy of keyflip.\n\nQuit keyflip and open it once more and "
        "it will start normally.",
        ("OK",),
    )


# --------------------------------------------------------------------------
# clipboard
# --------------------------------------------------------------------------
def clipboard_serial() -> int:
    return int(NSPasteboard.generalPasteboard().changeCount())


def clipboard_get() -> str | None:
    return NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)


def clipboard_set(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


# --------------------------------------------------------------------------
# synthetic input
# --------------------------------------------------------------------------
def _post(keycode: int, flags: int, down: bool) -> None:
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    ev = Quartz.CGEventCreateKeyboardEvent(src, keycode, down)
    Quartz.CGEventSetFlags(ev, flags)
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, _SYNTHETIC_MARK)
    Quartz.CGEventPost(Quartz.kCGSessionEventTap, ev)


def _tap_key(keycode: int) -> None:
    _post(keycode, _MASK_CMD, True)
    time.sleep(0.012)
    _post(keycode, _MASK_CMD, False)


def send_copy() -> None:
    _tap_key(_KEYCODE_C)


def send_paste() -> None:
    _tap_key(_KEYCODE_V)


def modifiers_down() -> bool:
    state = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
    return bool(state & MAC_FLAG_MASK)


def wait_modifiers_released(timeout_ms: int) -> bool:
    """Hold off until the user lets go of the shortcut.

    Synthetic events inherit the hardware modifier state, so firing Cmd+C while
    ctrl-alt-cmd is still physically held would reach the app as a completely
    different chord.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if not modifiers_down():
            time.sleep(0.02)  # let the app process the key-up first
            return True
        time.sleep(0.01)
    return False


def notify(title: str, message: str) -> None:
    script = f'display notification {message!r} with title {title!r}'
    try:
        subprocess.run(["osascript", "-e", script], check=False,
                       capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass


# --------------------------------------------------------------------------
# hotkey listener
# --------------------------------------------------------------------------
class HotkeyListener:
    def __init__(self, bindings: list[tuple[Hotkey | DoubleTap, Callable[[], None]]]):
        self._by_chord: dict[tuple[int, int], Callable[[], None]] = {}
        #: keycode -> (detector, handler, the flag bit that means "held").
        self._by_tap: dict[int, tuple[TapDetector, Callable[[], None], int]] = {}
        for binding, fn in bindings:
            if isinstance(binding, DoubleTap):
                self._by_tap[binding.mac_keycode()] = (
                    TapDetector(binding.window_ms), fn, binding.mac_device_mask()
                )
            else:
                self._by_chord[(binding.mac_keycode(), binding.mac_flags())] = fn
        self._tap = None
        self._source = None
        self._busy = threading.Event()
        self._running = False

    # -- the hot path ------------------------------------------------------
    def _callback(self, proxy, type_, event, refcon):
        if type_ in _TAP_DISABLED:
            # The window server cut us off (usually a momentary stall).
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        if Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGEventSourceUserData
        ) == _SYNTHETIC_MARK:
            return event

        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )

        if type_ == Quartz.kCGEventFlagsChanged:
            self._modifier_changed(keycode, Quartz.CGEventGetFlags(event))
            return event  # a modifier is never swallowed: it has to keep typing

        if self._by_tap and type_ == Quartz.kCGEventKeyDown:
            # A real key in the middle of the gesture means the user is typing
            # capitals, not reaching for the shortcut.
            for detector, _, _ in self._by_tap.values():
                detector.interrupted()

        flags = Quartz.CGEventGetFlags(event) & MAC_FLAG_MASK
        handler = self._by_chord.get((keycode, flags))
        if handler is None:
            return event  # not ours: untouched, unlogged, unmeasured

        if type_ == Quartz.kCGEventKeyDown:
            self._fire(handler)
        return None  # swallow both the down and the matching up

    def _modifier_changed(self, keycode: int, flags: int) -> None:
        entry = self._by_tap.get(keycode)
        if entry is None:
            # Some other modifier moved - that rules out a clean double tap.
            for detector, _, _ in self._by_tap.values():
                detector.interrupted()
            return
        detector, handler, device_mask = entry
        now = time.monotonic()
        if flags & device_mask:
            detector.press(now)
        elif detector.release(now):
            self._fire(handler)

    def _fire(self, handler: Callable[[], None]) -> None:
        if self._busy.is_set():
            return
        self._busy.set()
        threading.Thread(target=self._run, args=(handler,), daemon=True).start()

    def _run(self, handler: Callable[[], None]) -> None:
        try:
            handler()
        except Exception as exc:  # a bad flip must never kill the listener
            print(f"keyflip: {exc!r}")
        finally:
            self._busy.clear()

    # -- lifecycle ---------------------------------------------------------
    def install(self) -> None:
        """Bind the tap to the calling thread's run loop.

        Must run on the same thread as run_forever(): a tap is serviced by
        the run loop it was added to.
        """
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(
            Quartz.kCGEventKeyUp
        )
        if self._by_tap:
            # Modifiers arrive as flagsChanged, not as key events.  Only ask
            # for them when something is actually watching for a tap.
            mask |= Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if not self._tap:
            raise PermissionError(PERMISSION_HELP)
        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), self._source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)

    def run_forever(self) -> None:
        # Short slices rather than CFRunLoopRun() so that stop() can actually
        # end this loop: CFRunLoopRun() never returns, which would leave the
        # listener thread running after a quit and make stop() mean nothing
        # beyond disabling the tap.  Four no-op wakeups a second is the price.
        # (Ctrl+C happens to reach Python either way - a signal interrupts the
        # mach call underneath - so this is about shutdown, not about signals.)
        self._running = True
        while self._running:
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.25, False)

    def stop(self) -> None:
        self._running = False
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
