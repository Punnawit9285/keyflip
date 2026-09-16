"""Exercise the macOS tap callback - the one piece that sees every keystroke.

CGEvents can be *created* without Accessibility permission (only posting and
tapping are gated), so the matching logic is testable on any Mac.
"""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")

Quartz = pytest.importorskip("Quartz")

from keyflip import backend_mac as be   # noqa: E402
from keyflip.hotkey import parse        # noqa: E402

HOTKEY = parse("ctrl+alt+cmd+l")        # keycode 37
KEYCODE_L = 37

DOUBLE = parse("double-rshift")
KEYCODE_RSHIFT = 60
RSHIFT_DOWN = DOUBLE.mac_device_mask() | Quartz.kCGEventFlagMaskShift


def make_event(keycode, flags, down=True, synthetic=False):
    ev = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    Quartz.CGEventSetFlags(ev, flags)
    if synthetic:
        Quartz.CGEventSetIntegerValueField(
            ev, Quartz.kCGEventSourceUserData, be._SYNTHETIC_MARK)
    return ev


@pytest.fixture
def listener():
    fired = []
    lis = be.HotkeyListener([(HOTKEY, lambda: fired.append(1))])
    lis.fired = fired
    return lis


def feed(listener, event, type_=None):
    return listener._callback(None, type_ or Quartz.kCGEventKeyDown, event, None)


def test_matching_chord_is_swallowed(listener):
    out = feed(listener, make_event(KEYCODE_L, HOTKEY.mac_flags()))
    assert out is None, "the hotkey must not also reach the focused app"


def test_other_keys_pass_straight_through(listener):
    for keycode in (0, 8, 12, 49):        # a, c, q, space
        ev = make_event(keycode, HOTKEY.mac_flags())
        assert feed(listener, ev) is ev, "every other key must be returned untouched"


def test_same_key_with_different_modifiers_passes_through(listener):
    from keyflip.hotkey import MAC_FLAGS
    for flags in (0,
                  MAC_FLAGS["cmd"],                       # Cmd+L, Chrome's omnibox
                  MAC_FLAGS["ctrl"] | MAC_FLAGS["alt"],
                  HOTKEY.mac_flags() | MAC_FLAGS["shift"]):  # extra modifier
        ev = make_event(KEYCODE_L, flags)
        assert feed(listener, ev) is ev


def test_capslock_and_noncoalesced_bits_do_not_break_matching(listener):
    # Real events carry bits we do not care about; they must be masked off.
    noise = Quartz.kCGEventFlagMaskAlphaShift | Quartz.kCGEventFlagMaskNonCoalesced
    ev = make_event(KEYCODE_L, HOTKEY.mac_flags() | noise)
    assert feed(listener, ev) is None


def test_our_own_synthetic_events_are_ignored(listener):
    ev = make_event(KEYCODE_L, HOTKEY.mac_flags(), synthetic=True)
    assert feed(listener, ev) is ev, "must not react to the keys it sends itself"


def test_handler_runs_once_per_press(listener):
    import time
    feed(listener, make_event(KEYCODE_L, HOTKEY.mac_flags()))
    feed(listener, make_event(KEYCODE_L, HOTKEY.mac_flags(),
                              down=False), Quartz.kCGEventKeyUp)
    for _ in range(100):
        if listener.fired:
            break
        time.sleep(0.01)
    assert listener.fired == [1], "key-up must be swallowed but must not re-fire"


def test_key_up_of_the_chord_is_also_swallowed(listener):
    out = feed(listener, make_event(KEYCODE_L, HOTKEY.mac_flags(), down=False),
               Quartz.kCGEventKeyUp)
    assert out is None


def test_a_failing_handler_does_not_kill_the_listener():
    def boom():
        raise RuntimeError("nope")
    lis = be.HotkeyListener([(HOTKEY, boom)])
    assert feed(lis, make_event(KEYCODE_L, HOTKEY.mac_flags())) is None
    import time
    time.sleep(0.2)
    # still alive and still matching
    assert feed(lis, make_event(KEYCODE_L, HOTKEY.mac_flags())) is None


# --- the double tap -------------------------------------------------------
@pytest.fixture
def taps():
    fired = []
    lis = be.HotkeyListener([(DOUBLE, lambda: fired.append(1))])
    lis.fired = fired
    return lis


def flags_changed(listener, flags, keycode=KEYCODE_RSHIFT):
    """One modifier transition, as the window server delivers it."""
    ev = make_event(keycode, flags)
    out = listener._callback(None, Quartz.kCGEventFlagsChanged, ev, None)
    assert out is ev, "a modifier must always reach the app - it has to type"


def settle(listener, expected):
    import time
    for _ in range(100):
        if len(listener.fired) >= expected:
            break
        time.sleep(0.01)
    return listener.fired


def test_two_taps_of_right_shift_fire(taps):
    for _ in range(2):
        flags_changed(taps, RSHIFT_DOWN)
        flags_changed(taps, 0)
    assert settle(taps, 1) == [1]


def test_the_left_shift_is_left_alone(taps):
    lshift_down = 0x0002 | Quartz.kCGEventFlagMaskShift
    for _ in range(2):
        flags_changed(taps, lshift_down, keycode=56)
        flags_changed(taps, 0, keycode=56)
    import time
    time.sleep(0.15)
    assert taps.fired == [], "the other shift must stay usable for capitals"


def test_typing_a_capital_between_the_taps_does_not_fire(taps):
    flags_changed(taps, RSHIFT_DOWN)
    feed(taps, make_event(0, Quartz.kCGEventFlagMaskShift))   # shift+A
    flags_changed(taps, 0)
    flags_changed(taps, RSHIFT_DOWN)
    import time
    time.sleep(0.15)
    assert taps.fired == []


def test_the_right_shift_going_up_is_seen_while_the_left_is_held(taps):
    # The plain shift flag stays set, so only the per-side bit can tell us.
    both = 0x0002 | RSHIFT_DOWN
    left_only = 0x0002 | Quartz.kCGEventFlagMaskShift
    for _ in range(2):
        flags_changed(taps, both)        # right down, left still held
        flags_changed(taps, left_only)   # right up, left still held
    assert settle(taps, 1) == [1]


def test_it_fires_only_after_right_shift_is_let_go(taps, monkeypatch):
    # The shortcut goes on to send Cmd+C; sent with shift held it would
    # arrive as Cmd+Shift+C.  Fire on the key-up, never on the key-down.
    dispatched = []
    monkeypatch.setattr(taps, "_fire", dispatched.append)
    flags_changed(taps, RSHIFT_DOWN)
    flags_changed(taps, 0)
    flags_changed(taps, RSHIFT_DOWN)
    assert dispatched == [], "must not fire while the second tap is still held"
    flags_changed(taps, 0)
    assert len(dispatched) == 1


def test_a_chord_listener_does_not_ask_for_modifier_events(listener):
    assert not listener._by_tap, "flagsChanged is only worth watching for a tap"
