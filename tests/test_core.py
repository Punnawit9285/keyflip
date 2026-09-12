"""Drive the flip against a fake desktop: a clipboard, a selection, an app."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip.config import Config           # noqa: E402
from keyflip.core import (                  # noqa: E402
    Flipper, BUSY_MODIFIERS, NO_SELECTION, NOT_TEXT, NO_EVIDENCE, UNCHANGED,
    FLIPPED,
)


class FakeBackend:
    """Stands in for macOS/Windows: a clipboard with a change counter."""

    def __init__(self, selection=None, clipboard=None, *,
                 answers_copy=True, modifiers_stuck=False):
        self.clipboard = clipboard
        self.selection = selection
        self.serial = 100
        self.answers_copy = answers_copy
        self.modifiers_stuck = modifiers_stuck
        self.pasted = []          # what the "app" received
        self.copies = 0

    def wait_modifiers_released(self, timeout_ms):
        return not self.modifiers_stuck

    def clipboard_serial(self):
        return self.serial

    def clipboard_get(self):
        return self.clipboard

    def clipboard_set(self, text):
        self.clipboard = text
        self.serial += 1

    def send_copy(self):
        self.copies += 1
        if self.answers_copy and self.selection is not None:
            self.clipboard = self.selection
            self.serial += 1

    def send_paste(self):
        self.pasted.append(self.clipboard)


def flip(backend, config=None, direction=None):
    return Flipper(config or Config(paste_settle_ms=0), backend).flip(direction)


def test_thai_gibberish_becomes_english():
    be = FakeBackend(selection="รสนอำันีแสฟีกำ", clipboard="keep me")
    res = flip(be)
    assert res.status == FLIPPED
    assert res.after == "iloveyouclaude"
    assert be.pasted == ["iloveyouclaude"]


def test_english_gibberish_becomes_thai():
    be = FakeBackend(selection="ggvxgxbh]", clipboard="keep me")
    res = flip(be)
    assert res.after == "เเอปเปิ้ล"
    assert be.pasted == ["เเอปเปิ้ล"]


def test_original_clipboard_is_put_back():
    be = FakeBackend(selection="l;ylfu8iy[", clipboard="my earlier copy")
    assert flip(be).ok
    assert be.clipboard == "my earlier copy"


def test_clipboard_is_left_alone_when_restore_is_off():
    be = FakeBackend(selection="l;ylfu8iy[", clipboard="my earlier copy")
    flip(be, Config(paste_settle_ms=0, restore_clipboard=False))
    assert be.clipboard == "สวัสดีครับ"


def test_nothing_selected_never_pastes():
    be = FakeBackend(selection=None, clipboard="untouched")
    res = flip(be, Config(paste_settle_ms=0, copy_timeout_ms=40))
    assert res.status == NO_SELECTION
    assert be.pasted == []
    assert be.clipboard == "untouched"


def test_app_that_ignores_the_copy_never_pastes():
    be = FakeBackend(selection="text", answers_copy=False, clipboard="untouched")
    res = flip(be, Config(paste_settle_ms=0, copy_timeout_ms=40))
    assert res.status == NO_SELECTION
    assert be.pasted == []


def test_image_selection_is_declined():
    be = FakeBackend(selection="", clipboard="untouched")
    be.send_copy = lambda: (setattr(be, "clipboard", None),
                            setattr(be, "serial", be.serial + 1))
    res = flip(be)
    assert res.status == NOT_TEXT
    assert be.pasted == []


def test_text_with_nothing_to_change_is_not_pasted():
    be = FakeBackend(selection="\U0001f600 \n\t", clipboard="untouched")
    res = flip(be)
    assert res.status in (UNCHANGED, NO_EVIDENCE)
    assert be.pasted == []
    assert be.clipboard == "untouched"


def test_a_selected_number_is_left_alone():
    # Digits are real keys on both layouts: "2026" would become Thai here.
    for text in ("2026", "$14.99", "+66 81-234-5678"):
        be = FakeBackend(selection=text, clipboard="untouched")
        res = flip(be)
        assert res.status == NO_EVIDENCE, text
        assert be.pasted == []
        assert be.clipboard == "untouched"


def test_an_explicit_direction_still_converts_a_number():
    be = FakeBackend(selection="2026")
    res = flip(be, direction="en2th")
    # the unshifted number row on a Thai board, not the Thai digits (those are
    # the shifted row) - which is exactly why guessing here would be wrong
    assert res.status == FLIPPED and res.after == "/\u0e08/\u0e38"


def test_held_modifiers_abort_before_touching_the_clipboard():
    be = FakeBackend(selection="x", clipboard="untouched", modifiers_stuck=True)
    res = flip(be)
    assert res.status == BUSY_MODIFIERS
    assert be.copies == 0 and be.pasted == []
    assert be.clipboard == "untouched"


def test_forced_direction_overrides_detection():
    # Pure ASCII that also happens to be valid on a Thai board
    be = FakeBackend(selection="iloveyouclaude")
    assert flip(be, direction="en2th").after == "รสนอำันีแสฟีกำ"


def test_normalize_is_opt_in():
    be = FakeBackend(selection="ggvxgxbh]")
    assert flip(be).after == "เเอปเปิ้ล"
    be2 = FakeBackend(selection="ggvxgxbh]")
    assert flip(be2, Config(paste_settle_ms=0, normalize_thai=True)).after == "แอปเปิ้ล"


def test_describe_covers_every_status():
    for status in (BUSY_MODIFIERS, NO_SELECTION, NOT_TEXT, UNCHANGED, FLIPPED):
        from keyflip.core import FlipResult
        assert FlipResult(status, "a", "b").describe()
