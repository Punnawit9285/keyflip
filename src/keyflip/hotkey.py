"""Parsing and per-platform encoding of hotkey specs.

Two shapes of shortcut live here:

* a chord - ``ctrl+alt+cmd+l``, a key held down with modifiers;
* a double tap - ``double-rshift``, one modifier key hit twice on its own.

Keys are identified by *physical position*, never by the character they
produce.  That is the whole point: the user is mid-sentence on a Thai layout
when they reach for the shortcut, so "the L key" has to mean the key where L
lives on a US board, whatever it happens to type right now.
"""

from __future__ import annotations

import re

MODIFIERS = ("ctrl", "alt", "shift", "cmd")

#: Accepted aliases -> canonical modifier name.
_MOD_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl", "^": "ctrl",
    "alt": "alt", "opt": "alt", "option": "alt",
    "shift": "shift",
    "cmd": "cmd", "command": "cmd", "super": "cmd", "win": "cmd", "meta": "cmd",
}

_KEY_ALIASES = {
    "space": "space", "spacebar": "space",
    "return": "return", "enter": "return",
    "esc": "escape", "escape": "escape",
    "tab": "tab",
    "backquote": "`", "grave": "`", "tilde": "`",
    "minus": "-", "equal": "=", "equals": "=",
    "semicolon": ";", "quote": "'", "apostrophe": "'",
    "comma": ",", "period": ".", "dot": ".", "slash": "/", "backslash": "\\",
    "lbracket": "[", "rbracket": "]",
}

# --- macOS ANSI virtual keycodes (Carbon kVK_*) ---------------------------
MAC_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33,
    "i": 34, "p": 35, "return": 36, "l": 37, "j": 38, "'": 39, "k": 40,
    ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "tab": 48, "space": 49, "`": 50, "escape": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111, "f13": 105,
    "f14": 107, "f15": 113, "f16": 106, "f17": 64, "f18": 79, "f19": 80,
}

# --- Windows virtual-key codes -------------------------------------------
WIN_VKS = {
    "space": 0x20, "return": 0x0D, "escape": 0x1B, "tab": 0x09,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
for _i in range(26):
    WIN_VKS[chr(ord("a") + _i)] = 0x41 + _i
for _i in range(10):
    WIN_VKS[str(_i)] = 0x30 + _i
for _i in range(1, 25):
    WIN_VKS[f"f{_i}"] = 0x70 + _i - 1

# CGEventFlags
MAC_FLAGS = {"shift": 1 << 17, "ctrl": 1 << 18, "alt": 1 << 19, "cmd": 1 << 20}
MAC_FLAG_MASK = sum(MAC_FLAGS.values())

# RegisterHotKey fsModifiers
WIN_MODS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "cmd": 0x0008}
WIN_MOD_NOREPEAT = 0x4000

# --- double-tap keys ------------------------------------------------------
#: How long the second tap has to arrive - and how long the first may be held
#: before it counts as holding the key rather than tapping it.
DEFAULT_DOUBLE_TAP_MS = 400

# Tappable keys are named by side.  "Shift twice" has to mean the shift the
# user actually hit, or the other one could not be used for capitals any more.
#
# ``mac_device`` is the NX_DEVICE*KEYMASK bit that says this particular key is
# down.  It is per-side, unlike the plain shift/ctrl/alt/cmd flags: with those
# alone, a left shift held down would hide the right one being released.
TAP_KEYS = {
    "lshift": {"mac": 56, "mac_device": 0x0002, "win": 0xA0, "label": "Left Shift",  "glyph": "⇧"},
    "rshift": {"mac": 60, "mac_device": 0x0004, "win": 0xA1, "label": "Right Shift", "glyph": "⇧"},
    "lctrl":  {"mac": 59, "mac_device": 0x0001, "win": 0xA2, "label": "Left Ctrl",   "glyph": "⌃"},
    "rctrl":  {"mac": 62, "mac_device": 0x2000, "win": 0xA3, "label": "Right Ctrl",  "glyph": "⌃"},
    "lalt":   {"mac": 58, "mac_device": 0x0020, "win": 0xA4, "label": "Left Alt",    "glyph": "⌥"},
    "ralt":   {"mac": 61, "mac_device": 0x0040, "win": 0xA5, "label": "Right Alt",   "glyph": "⌥"},
    "lcmd":   {"mac": 55, "mac_device": 0x0008, "win": 0x5B, "label": "Left Cmd",    "glyph": "⌘"},
    "rcmd":   {"mac": 54, "mac_device": 0x0010, "win": 0x5C, "label": "Right Cmd",   "glyph": "⌘"},
}

#: Every spelling of a tappable key, with separators already stripped out.
_TAP_ALIASES: dict[str, str] = {}
for _canon in TAP_KEYS:
    _base = _canon[1:]
    _sides = ("l", "left") if _canon[0] == "l" else ("r", "right")
    for _alias, _norm in _MOD_ALIASES.items():
        if _norm != _base or not _alias.isalpha():
            continue
        for _side in _sides:
            _TAP_ALIASES[f"{_side}{_alias}"] = _canon   # rshift, rightshift
            _TAP_ALIASES[f"{_alias}{_side}"] = _canon   # shiftr, shiftright

#: "double rshift", "rshift x2", "rshift rshift" all mean the same thing.
_DOUBLE_WORDS = ("double", "dbl", "twice", "2x", "x2")


class HotkeyError(ValueError):
    pass


class Hotkey:
    __slots__ = ("mods", "key", "spec")

    def __init__(self, mods: frozenset[str], key: str, spec: str):
        self.mods, self.key, self.spec = mods, key, spec

    def __repr__(self) -> str:
        return f"<Hotkey {self.spec}>"

    def identity(self) -> tuple:
        """What makes two bindings the same physical gesture."""
        return ("chord", self.mods, self.key)

    # -- encodings ---------------------------------------------------------
    def mac_keycode(self) -> int:
        try:
            return MAC_KEYCODES[self.key]
        except KeyError:
            raise HotkeyError(f"{self.key!r} has no macOS keycode") from None

    def mac_flags(self) -> int:
        return sum(MAC_FLAGS[m] for m in self.mods)

    def win_vk(self) -> int:
        try:
            return WIN_VKS[self.key]
        except KeyError:
            raise HotkeyError(f"{self.key!r} has no Windows virtual-key code") from None

    def win_mods(self) -> int:
        return sum(WIN_MODS[m] for m in self.mods) | WIN_MOD_NOREPEAT

    def pretty(self, platform: str) -> str:
        if platform == "darwin":
            glyphs = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
            order = ("ctrl", "alt", "shift", "cmd")
            label = self.key.upper() if len(self.key) == 1 else self.key.title()
            return "".join(glyphs[m] for m in order if m in self.mods) + label
        order = ("ctrl", "alt", "shift", "cmd")
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Win"}
        parts = [names[m] for m in order if m in self.mods]
        parts.append(self.key.upper() if len(self.key) == 1 else self.key.title())
        return "+".join(parts)


class DoubleTap:
    """One modifier key hit twice on its own, e.g. right shift, right shift.

    A modifier alone can never be a chord - it has nothing to modify - so this
    gesture is invisible to every application on the machine, which is exactly
    what makes it safe to claim: there is no shortcut anywhere to collide with.
    The cost is that it has to be recognised rather than registered, so both
    backends watch the key going down and up and time the gap themselves.
    """

    __slots__ = ("key", "spec", "window_ms")

    def __init__(self, key: str, spec: str, window_ms: int = DEFAULT_DOUBLE_TAP_MS):
        self.key, self.spec, self.window_ms = key, spec, window_ms

    def __repr__(self) -> str:
        return f"<DoubleTap {self.spec}>"

    def identity(self) -> tuple:
        return ("tap", self.key)

    @property
    def mods(self) -> frozenset[str]:
        return frozenset()

    # -- encodings ---------------------------------------------------------
    def mac_keycode(self) -> int:
        return TAP_KEYS[self.key]["mac"]

    def mac_device_mask(self) -> int:
        """The flag bit that is set while this exact key is held down."""
        return TAP_KEYS[self.key]["mac_device"]

    def win_vk(self) -> int:
        return TAP_KEYS[self.key]["win"]

    def pretty(self, platform: str) -> str:
        info = TAP_KEYS[self.key]
        if platform == "darwin":
            side = "Right" if self.key[0] == "r" else "Left"
            return f"{side} {info['glyph']} \u00d72"
        return f"{info['label'].replace('Cmd', 'Win')} \u00d72"


class TapDetector:
    """The state machine behind a double tap, fed by a backend's key events.

    Everything it rejects matters more than what it accepts.  Typing "Hello
    World" presses the same shift twice within a few hundred milliseconds, so
    a tap only counts when the key went down and up with nothing in between
    and without being held - i.e. when it was pressed for its own sake.
    """

    __slots__ = ("window", "_down_at", "_last_tap", "_used", "_fired")

    def __init__(self, window_ms: int = DEFAULT_DOUBLE_TAP_MS):
        self.window = window_ms / 1000
        self._down_at = 0.0    # when the key went down; 0 while it is up
        self._last_tap = 0.0   # when the previous clean tap completed
        self._used = False     # another key was pressed while this one was held
        self._fired = False    # this press already triggered the shortcut

    def press(self, now: float) -> bool:
        """Key down.  True when this is the second tap and the shortcut fires."""
        if self._down_at:
            return False       # auto-repeat while held is not a new tap
        self._down_at = now
        self._used = False
        if self._last_tap and now - self._last_tap <= self.window:
            self._last_tap = 0.0
            self._fired = True
            return True
        return False

    def release(self, now: float) -> None:
        down_at, self._down_at = self._down_at, 0.0
        clean = down_at and not self._used and now - down_at <= self.window
        # After firing, start over: three taps are one shortcut, not two.
        self._last_tap = now if clean and not self._fired else 0.0
        self._fired = False

    def interrupted(self) -> None:
        """Another key was pressed: this is typing, not a deliberate tap."""
        self._used = True
        self._last_tap = 0.0


def _parse_double_tap(spec: str) -> str | None:
    """The tap key named by ``spec``, or None if it does not name one."""
    flat = re.sub(r"[\s+_.-]+", "", spec.strip().lower())
    if not flat:
        return None
    for word in _DOUBLE_WORDS:
        if flat.startswith(word) and flat[len(word):] in _TAP_ALIASES:
            return _TAP_ALIASES[flat[len(word):]]
        if flat.endswith(word) and flat[:-len(word)] in _TAP_ALIASES:
            return _TAP_ALIASES[flat[:-len(word)]]
    half, odd = divmod(len(flat), 2)
    if not odd and flat[:half] == flat[half:] and flat[:half] in _TAP_ALIASES:
        return _TAP_ALIASES[flat[:half]]
    # A bare "rshift" is almost certainly a mistyped double tap, and it can
    # never be anything else - a lone modifier cannot be a chord.
    if flat in _TAP_ALIASES:
        raise HotkeyError(
            f"{spec!r} is a single modifier; write it as "
            f"'double-{_TAP_ALIASES[flat]}' to tap it twice"
        )
    return None


def parse(spec: str, *, double_tap_ms: int = DEFAULT_DOUBLE_TAP_MS) -> Hotkey | DoubleTap:
    """``"ctrl+alt+cmd+l"`` or ``"double-rshift"`` -> a binding.

    Raises HotkeyError on anything odd.
    """
    tap = _parse_double_tap(spec)
    if tap is not None:
        return DoubleTap(tap, f"double-{tap}", double_tap_ms)
    tokens = [t.strip().lower() for t in spec.replace("-", "+-").split("+") if t.strip()]
    if not tokens:
        raise HotkeyError("empty hotkey")
    # "+-" above lets a literal "-" survive the split; undo the artefact
    tokens = [t for t in tokens if t]
    mods: set[str] = set()
    key: str | None = None
    for tok in tokens:
        if tok in _MOD_ALIASES:
            mods.add(_MOD_ALIASES[tok])
            continue
        tok = _KEY_ALIASES.get(tok, tok)
        if key is not None:
            raise HotkeyError(f"{spec!r} names two keys ({key!r} and {tok!r})")
        key = tok
    if key is None:
        raise HotkeyError(f"{spec!r} is only modifiers - it needs a key too")
    if key not in MAC_KEYCODES and key not in WIN_VKS:
        raise HotkeyError(f"unknown key {key!r}")
    if len(mods) < 2:
        raise HotkeyError(
            f"{spec!r} uses fewer than two modifiers; that is very likely to "
            "collide with an application shortcut"
        )
    return Hotkey(frozenset(mods), key, spec)
