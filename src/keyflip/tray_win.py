"""A notification-area icon for Windows, built on pystray.

pystray pumps its own message loop on the calling thread, which is why the
hotkey listener gets a thread of its own: RegisterHotKey delivers WM_HOTKEY to
the queue of whichever thread registered it, and two loops cannot share one.

The icon is drawn rather than loaded so there is no asset to ship or lose, and
no font dependency - a Thai glyph would not render with PIL's bundled font.
"""

from __future__ import annotations

import os

import pystray
from PIL import Image, ImageDraw

from . import hotkey as hk
from .config import Config, config_path

_BG = (32, 33, 36, 255)
_THAI = (122, 200, 255, 255)
_LATIN = (255, 214, 122, 255)


def _icon_image(size: int = 64) -> Image.Image:
    """Two arrows swapping places: the whole program in one glyph."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=_BG)

    unit = size / 16
    def arrow(y, color, pointing_right):
        x0, x1 = 3 * unit, 13 * unit
        d.line([(x0, y), (x1, y)], fill=color, width=max(2, int(unit * 0.9)))
        tip, back = (x1, x0) if pointing_right else (x0, x1)
        head = unit * 2.6 * (1 if pointing_right else -1)
        d.polygon([(tip, y), (tip - head, y - unit * 1.9),
                   (tip - head, y + unit * 1.9)], fill=color)

    arrow(size * 0.34, _THAI, True)
    arrow(size * 0.66, _LATIN, False)
    return img


def run_tray(daemon) -> None:
    def status_text(_item=None) -> str:
        if not daemon.flips:
            return "No flips yet"
        last = daemon.last
        if len(last) > 46:
            last = last[:45] + "…"
        return f"{daemon.flips} flip{'' if daemon.flips == 1 else 's'}  ·  {last}"

    def on_flip(icon, item):
        daemon.flip_clipboard_in_place()

    def on_config(icon, item):
        path = config_path()
        if not path.exists():
            Config().save(path)
        os.startfile(path)  # noqa: S606 - opening the user's own config

    def on_quit(icon, item):
        daemon.stop()
        icon.stop()

    cfg = daemon.config
    rows = [pystray.MenuItem(status_text, None, enabled=False),
            pystray.Menu.SEPARATOR]
    for spec, label in ((cfg.hotkey, "flip selection"),
                        (cfg.hotkey_to_thai, "force -> Thai"),
                        (cfg.hotkey_to_english, "force -> English")):
        if spec:
            rows.append(pystray.MenuItem(
                f"{hk.parse(spec).pretty('win32')}   {label}", None, enabled=False))
    rows += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Flip clipboard now", on_flip, default=True),
        pystray.MenuItem("Open config file", on_config),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit keyflip", on_quit),
    ]

    icon = pystray.Icon("keyflip", _icon_image(), "keyflip", pystray.Menu(*rows))
    icon.run()
