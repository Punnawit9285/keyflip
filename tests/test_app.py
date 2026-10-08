"""The command line surface the installers depend on."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip import app, hotkey as hk   # noqa: E402
from keyflip.config import Config       # noqa: E402


def test_the_installer_flag_is_accepted():
    # keyflip.iss launches "keyflip.exe run --welcome"; if argparse ever
    # rejected it, a fresh install would end in an exe that exits at once.
    args = app.build_parser().parse_args(["run", "--welcome"])
    assert args.welcome is True
    assert app.build_parser().parse_args(["run"]).welcome is False


def test_the_welcome_names_the_shortcut_actually_configured():
    msg = app._welcome_message(Config(hotkey="double-rshift"))
    assert hk.parse("double-rshift").pretty(sys.platform) in msg

    chord = app._welcome_message(Config(hotkey="ctrl+alt+shift+k"))
    assert hk.parse("ctrl+alt+shift+k").pretty(sys.platform) in chord


def test_the_welcome_survives_having_no_main_shortcut():
    assert app._welcome_message(Config(hotkey="")) == "keyflip is running."


# --- the Accessibility permission ----------------------------------------
class PermissionBackend:
    """Records the order of what startup asks of macOS."""

    def __init__(self, trusted=False, prompt_grants=False):
        self.trusted, self.prompt_grants, self.calls = trusted, prompt_grants, []

    def has_accessibility(self, prompt=False):
        self.calls.append("prompt" if prompt else "check")
        return self.trusted or (prompt and self.prompt_grants)

    def forget_stale_permission(self):
        self.calls.append("forget")


def test_a_trusted_start_touches_nothing():
    be = PermissionBackend(trusted=True)
    assert app._ensure_permission(be) is True
    assert be.calls == ["check"]


def test_a_stale_grant_is_cleared_before_macos_is_asked_again():
    # An update is a new binary: the old switch is still listed as on, for a
    # build that no longer exists.  Prompting over it changes nothing.
    be = PermissionBackend(prompt_grants=True)
    assert app._ensure_permission(be) is True
    assert be.calls == ["check", "forget", "prompt"]


def test_without_a_grant_it_waits_for_one(monkeypatch):
    waited = []
    monkeypatch.setattr(app, "_await_permission", lambda be: waited.append(be) or False)
    be = PermissionBackend()
    assert app._ensure_permission(be) is False
    assert waited == [be]
