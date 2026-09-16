"""Parsing, and the double-tap state machine.

The detector's job is mostly *not* firing: right shift is a key people hit
dozens of times a minute while typing, so every test below that ends in "does
not fire" is guarding against the shortcut going off mid-sentence.
"""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip import hotkey as hk   # noqa: E402


# --- parsing --------------------------------------------------------------
@pytest.mark.parametrize("spec", [
    "double-rshift", "double rshift", "double right shift", "DOUBLE_RSHIFT",
    "rshift rshift", "rshift+rshift", "rshift x2", "rightshift x2",
    "shiftright twice", "double shift_r",
])
def test_every_spelling_of_the_default_lands_on_one_binding(spec):
    parsed = hk.parse(spec)
    assert isinstance(parsed, hk.DoubleTap)
    assert parsed.key == "rshift"
    assert parsed.spec == "double-rshift", "specs are canonicalised before saving"


def test_the_two_shifts_are_different_keys():
    assert hk.parse("double-lshift").key == "lshift"
    assert hk.parse("double-rshift").identity() != hk.parse("double-lshift").identity()


def test_a_double_tap_encodes_for_both_platforms():
    tap = hk.parse("double-rshift")
    assert tap.mac_keycode() == 60          # kVK_RightShift
    assert tap.win_vk() == 0xA1             # VK_RSHIFT
    assert tap.mac_device_mask() == 0x0004  # NX_DEVICERSHIFTKEYMASK


def test_the_windows_name_for_cmd_is_win():
    assert hk.parse("double-rcmd").pretty("win32").startswith("Right Win")
    assert "⌘" in hk.parse("double-rcmd").pretty("darwin")


def test_a_lone_modifier_is_explained_rather_than_rejected():
    with pytest.raises(hk.HotkeyError, match="double-rshift"):
        hk.parse("rshift")


def test_chords_still_parse_the_way_they_did():
    chord = hk.parse("ctrl+alt+cmd+l")
    assert isinstance(chord, hk.Hotkey)
    assert chord.key == "l" and chord.mods == frozenset({"ctrl", "alt", "cmd"})


def test_a_chord_on_the_minus_key_survives_the_double_tap_check():
    assert hk.parse("ctrl+alt+shift+-").key == "-"


def test_the_window_comes_from_the_caller():
    assert hk.parse("double-rshift", double_tap_ms=250).window_ms == 250


# --- the detector ---------------------------------------------------------
def tap(det, at, hold=0.05):
    """One press-and-release, returning whether the shortcut fired."""
    det.press(at)
    return det.release(at + hold)


def test_two_quick_taps_fire_when_the_second_is_released():
    det = hk.TapDetector(400)
    assert tap(det, 1.0) is False
    det.press(1.2)
    assert det.release(1.25) is True


def test_a_slow_second_tap_does_not_fire():
    det = hk.TapDetector(400)
    tap(det, 1.0)
    assert tap(det, 1.9) is False


def test_typing_capitals_does_not_fire():
    # Shift down, a letter, shift up - twice, as in "Hello World".
    det = hk.TapDetector(400)
    det.press(1.0)
    det.interrupted()          # the "H"
    assert det.release(1.15) is False
    det.press(1.3)
    det.interrupted()          # the "W"
    assert det.release(1.45) is False


def test_a_tap_then_a_capital_does_not_fire():
    # Firing on the second key-down would have flipped here, mid-word.
    det = hk.TapDetector(400)
    tap(det, 1.0)
    det.press(1.2)
    det.interrupted()          # shift is being used to type a capital
    assert det.release(1.3) is False


def test_holding_the_key_is_not_a_tap():
    det = hk.TapDetector(400)
    det.press(1.0)
    assert det.release(2.0) is False       # held for a second
    assert tap(det, 2.1) is False


def test_holding_the_second_tap_is_not_a_tap():
    det = hk.TapDetector(400)
    tap(det, 1.0)
    det.press(1.2)
    assert det.release(2.0) is False


def test_auto_repeat_while_held_is_not_a_second_tap():
    det = hk.TapDetector(400)
    det.press(1.0)
    det.press(1.05)            # Windows repeats a held modifier
    assert det.release(1.1) is False, "repeats of one press are still one tap"
    det.press(1.2)
    for repeat in (1.25, 1.3, 1.35):
        det.press(repeat)
    assert det.release(1.4) is True, "repeats must not restart the hold timer"


def test_three_taps_are_one_shortcut_not_two():
    det = hk.TapDetector(400)
    assert tap(det, 1.0) is False
    assert tap(det, 1.2) is True
    assert tap(det, 1.4) is False, "the third tap must re-arm, not re-fire"
    assert tap(det, 1.6) is True


def test_the_gesture_still_works_after_being_interrupted():
    det = hk.TapDetector(400)
    det.press(1.0)
    det.interrupted()
    det.release(1.1)
    assert tap(det, 1.2) is False
    assert tap(det, 1.4) is True


def test_a_release_with_no_press_is_ignored():
    # Shift was already down when keyflip started: only its key-up arrives.
    det = hk.TapDetector(400)
    assert det.release(1.0) is False
    assert tap(det, 1.2) is False
    assert tap(det, 1.4) is True
