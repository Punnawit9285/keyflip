"""The login item, written to a temporary directory rather than your real one."""
import plistlib
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip import autostart   # noqa: E402


@pytest.fixture
def plist(tmp_path, monkeypatch):
    """Point the macOS implementation at a throwaway plist."""
    path = tmp_path / "LaunchAgents" / f"{autostart.LABEL}.plist"
    monkeypatch.setattr(autostart, "_plist_path", lambda: path)
    return path


def test_the_command_relaunches_the_frozen_app_directly(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/keyflip.app/x/keyflip")
    assert autostart.launch_command() == [
        "/Applications/keyflip.app/x/keyflip", "run"]


def test_from_source_it_keeps_the_interpreter_it_is_running_on(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/repo/.venv/bin/python")
    assert autostart.launch_command() == [
        "/repo/.venv/bin/python", "-m", "keyflip", "run"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS login item")
def test_enabling_writes_a_launch_agent_that_launchd_can_read(plist):
    assert autostart.is_enabled() is False
    autostart.set_enabled(True)

    assert autostart.is_enabled() is True
    payload = plistlib.loads(plist.read_bytes())
    assert payload["Label"] == autostart.LABEL
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is False, "a crashed shortcut daemon must stay down"
    assert payload["ProgramArguments"] == autostart.launch_command()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS login item")
def test_disabling_removes_the_file_entirely(plist):
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert not plist.exists(), "an uninstall should leave nothing behind"
    assert autostart.is_enabled() is False


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS login item")
def test_disabling_when_it_was_never_on_is_not_an_error(plist):
    autostart.set_enabled(False)
    assert autostart.is_enabled() is False


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS login item")
def test_enabling_twice_leaves_one_entry(plist):
    autostart.set_enabled(True)
    autostart.set_enabled(True)
    assert autostart.is_enabled() is True
    assert plistlib.loads(plist.read_bytes())["Label"] == autostart.LABEL


def test_the_windows_command_line_quotes_a_path_with_spaces(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\keyflip\keyflip.exe")
    assert autostart._win_command_line() == r'"C:\Program Files\keyflip\keyflip.exe" run'
