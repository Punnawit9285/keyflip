"""The Win32 structs are declared by hand, so check their layout everywhere.

These sizes are the x64 Windows ABI.  They can be verified from any host
because every field now has an explicit width - which is the point: a bare
ctypes.c_long silently becomes 64-bit on an LP64 machine, SendInput rejects
the mis-sized INPUT, and nothing pastes.
"""
import ctypes
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from keyflip import backend_win as w  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.parametrize("struct, size", [
    (w.INPUT, 40),
    (w._KEYBDINPUT, 24),
    (w._MOUSEINPUT, 32),
    (w._HARDWAREINPUT, 8),
    (w.MSG, 48),
    (w.KBDLLHOOKSTRUCT, 24),
    (w.POINT, 8),
])
def test_struct_sizes_match_win64_abi(struct, size):
    assert ctypes.sizeof(struct) == size


def test_input_union_is_offset_past_the_type_tag():
    assert w.INPUT.u.offset == 8, "x64 pads the DWORD tag out to the union's alignment"


def test_backend_refuses_to_bind_off_windows():
    if sys.platform == "win32":
        pytest.skip("running on Windows")
    with pytest.raises(OSError):
        w._dlls()
