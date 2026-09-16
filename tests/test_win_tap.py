"""The Windows double tap, driven without Windows.

The hook callback itself needs a real keyboard, but everything after it -
which keystrokes count, and when the shortcut fires - is plain Python.
"""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip import backend_win as w    # noqa: E402
from keyflip.hotkey import parse        # noqa: E402

VK_LSHIFT, VK_RSHIFT, VK_A = 0xA0, 0xA1, 0x41


@pytest.fixture
def lis(monkeypatch):
    listener = w.HotkeyListener([(parse("double-rshift"), lambda: None)])
    listener.fired = []
    monkeypatch.setattr(listener, "_fire", listener.fired.append)
    return listener


def key(lis, vk, down):
    lis._key_event(vk, w.WM_KEYDOWN if down else w.WM_KEYUP)


def test_it_fires_only_after_right_shift_is_let_go(lis):
    # The bug this guards: fired on the second key-down, the copy went out
    # while shift was still held and arrived as Ctrl+Shift+C - a cloze in
    # Anki, the element inspector in Chrome.
    key(lis, VK_RSHIFT, True)
    key(lis, VK_RSHIFT, False)
    key(lis, VK_RSHIFT, True)
    assert lis.fired == [], "must not fire while the second tap is still held"
    key(lis, VK_RSHIFT, False)
    assert len(lis.fired) == 1


def test_the_left_shift_is_left_alone(lis):
    for _ in range(2):
        key(lis, VK_LSHIFT, True)
        key(lis, VK_LSHIFT, False)
    assert lis.fired == []


def test_a_capital_typed_with_the_second_tap_does_not_fire(lis):
    key(lis, VK_RSHIFT, True)
    key(lis, VK_RSHIFT, False)
    key(lis, VK_RSHIFT, True)
    key(lis, VK_A, True)       # shift+A
    key(lis, VK_A, False)
    key(lis, VK_RSHIFT, False)
    assert lis.fired == []


def test_held_shift_auto_repeat_does_not_fire(lis):
    for _ in range(5):
        key(lis, VK_RSHIFT, True)
    key(lis, VK_RSHIFT, False)
    assert lis.fired == []


def test_shift_reported_as_a_system_key_still_counts(lis):
    for _ in range(2):
        lis._key_event(VK_RSHIFT, w.WM_SYSKEYDOWN)
        lis._key_event(VK_RSHIFT, w.WM_SYSKEYUP)
    assert len(lis.fired) == 1
