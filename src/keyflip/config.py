"""User configuration, stored as JSON next to the platform's other app data."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# Right shift, tapped twice.  A modifier on its own cannot be a chord, so no
# application anywhere binds this - unlike the one- and two-modifier space,
# which Chrome, Office, Anki, Photoshop and the GPU overlays all live in.  It
# is also the same gesture on both platforms and needs no free letter.
DEFAULT_HOTKEY = "double-rshift"


def default_hotkey() -> str:
    return DEFAULT_HOTKEY


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / "keyflip"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "keyflip"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "keyflip"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Config:
    #: Flip the selection, guessing the direction from its contents.
    hotkey: str = field(default_factory=default_hotkey)
    #: Optional one-way shortcuts.  Empty string disables.
    hotkey_to_thai: str = ""
    hotkey_to_english: str = ""
    #: For double-tap shortcuts: how long the second tap has to arrive.
    double_tap_ms: int = 400

    #: Fold a typed "SARA E SARA E" into a single SARA AE after converting.
    normalize_thai: bool = False
    #: Put the user's own clipboard back once the paste has landed.
    restore_clipboard: bool = True
    #: How long to wait for the focused app to answer our copy request.
    copy_timeout_ms: int = 600
    #: How long to leave the converted text on the clipboard before restoring.
    paste_settle_ms: int = 350
    #: Give up waiting for the user to let go of the shortcut's modifiers.
    modifier_release_timeout_ms: int = 1000
    #: Show a desktop notification when a flip happens.
    notify: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"keyflip: ignoring unreadable config {path}: {exc}", file=sys.stderr)
            return cls()
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            print(f"keyflip: unknown config keys ignored: {', '.join(sorted(unknown))}",
                  file=sys.stderr)
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return path
