"""The flip itself: borrow the selection, re-type it, hand the clipboard back.

There is no API on either OS for "give me the text the user has selected", so
every tool in this category does the same dance with the clipboard.  The parts
worth being careful about are all failure modes: noticing that the focused app
never answered the copy, never pasting when the text would not change, and
always putting the user's own clipboard back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import Config
from .layout import convert, detect_direction, normalize_thai

# Outcomes, in the order they can occur.
BUSY_MODIFIERS = "modifiers-held"
NO_SELECTION = "no-selection"
NOT_TEXT = "not-text"
NO_EVIDENCE = "no-evidence"
UNCHANGED = "unchanged"
FLIPPED = "flipped"


@dataclass
class FlipResult:
    status: str
    before: str = ""
    after: str = ""
    direction: str = ""

    @property
    def ok(self) -> bool:
        return self.status == FLIPPED

    def describe(self) -> str:
        return {
            BUSY_MODIFIERS: "still holding the shortcut - let go and try again",
            NO_SELECTION: "nothing selected (or the app ignored the copy)",
            NOT_TEXT: "the selection is not text",
            NO_EVIDENCE: "no letters in the selection - nothing to infer from",
            UNCHANGED: "nothing on either layout would change",
            FLIPPED: f"{self.before!r} -> {self.after!r}",
        }[self.status]


class Flipper:
    def __init__(self, config: Config, backend):
        self.config = config
        self.backend = backend

    def flip(self, direction: str | None = None) -> FlipResult:
        cfg, be = self.config, self.backend

        # The shortcut's own modifiers are still physically down at this point.
        # Anything we synthesise would inherit them and reach the app as a
        # different chord entirely, so wait for the user's hand to come off.
        if not be.wait_modifiers_released(cfg.modifier_release_timeout_ms):
            return FlipResult(BUSY_MODIFIERS)

        saved = be.clipboard_get()
        serial = be.clipboard_serial()

        be.send_copy()
        if not self._await_clipboard(serial, cfg.copy_timeout_ms):
            return FlipResult(NO_SELECTION)

        selection = be.clipboard_get()
        if not selection:
            self._restore(saved)
            return FlipResult(NOT_TEXT)

        chosen = direction or detect_direction(selection)
        if chosen is None:
            # Digits and punctuation sit on both layouts, so a selection with
            # no letters gives auto-detection nothing to go on.  Decline rather
            # than turn "2026" into Thai.  An explicit one-way shortcut still
            # converts it, because then the user has said which way.
            self._restore(saved)
            return FlipResult(NO_EVIDENCE, selection, selection)

        flipped = convert(selection, chosen)
        if cfg.normalize_thai:
            flipped = normalize_thai(flipped)

        if flipped == selection:
            self._restore(saved)
            return FlipResult(UNCHANGED, selection, flipped, chosen)

        be.clipboard_set(flipped)
        be.send_paste()

        # Give the target app time to actually read the clipboard before we
        # yank it back; a restore that lands too early pastes the old text.
        time.sleep(cfg.paste_settle_ms / 1000)
        self._restore(saved)
        return FlipResult(FLIPPED, selection, flipped, chosen)

    # -- helpers -----------------------------------------------------------
    def _await_clipboard(self, serial: int, timeout_ms: int) -> bool:
        """Did the focused app actually answer our copy?

        Polling the change counter is how we tell "nothing was selected" apart
        from "the app is just slow", without ever guessing at a fixed delay.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if self.backend.clipboard_serial() != serial:
                return True
            time.sleep(0.015)
        return False

    def _restore(self, saved: str | None) -> None:
        if not self.config.restore_clipboard or saved is None:
            return
        try:
            self.backend.clipboard_set(saved)
        except OSError:
            pass  # losing the old clipboard is not worth an error path
