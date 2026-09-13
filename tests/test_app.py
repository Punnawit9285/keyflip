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
