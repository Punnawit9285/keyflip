"""Picking the keyboard layout to move to after a flip."""
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip import backend_win as w    # noqa: E402

# Real HKLs: the low word is the language, the high word the layout.  A
# 64-bit HKL with a device handle comes back sign-extended.
US, UK, THAI = 0x04090409, 0x08090809, 0x041E041E
THAI_PATTACHOTE = 0xFFFFFFFFF002041E


def test_windows_picks_the_layout_for_the_language():
    assert w._pick_layout([US, THAI], "th") == THAI
    assert w._pick_layout([THAI, US], "en") == US


def test_windows_matches_any_english_and_any_thai_layout():
    assert w._pick_layout([THAI, UK], "en") == UK
    assert w._pick_layout([US, THAI_PATTACHOTE], "th") == THAI_PATTACHOTE


def test_windows_finds_nothing_when_the_language_is_not_installed():
    assert w._pick_layout([US, UK], "th") is None
    assert w._pick_layout([None, 0], "en") is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_binds_input_sources_and_leaves_the_current_one_alone():
    from keyflip import backend_mac as m

    tis = m._tis()
    current = m._language(tis["TISCopyCurrentKeyboardInputSource"]())
    assert current, "every keyboard input source names its language"
    # Asking for the language the keyboard is already in must not touch it.
    assert m.select_language(current) is True
    assert m._language(tis["TISCopyCurrentKeyboardInputSource"]()) == current
