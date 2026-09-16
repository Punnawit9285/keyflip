"""Command line entry point and the daemon that owns the hotkeys."""

from __future__ import annotations

import argparse
import sys
import threading

from . import hotkey as hk
from .config import Config, config_dir, config_path
from .core import FLIPPED, Flipper
from .layout import EN2TH, TH2EN, convert, detect_direction, normalize_thai

__version__ = "1.0.1"


def load_backend():
    if sys.platform == "darwin":
        from . import backend_mac as backend
    elif sys.platform == "win32":
        from . import backend_win as backend
    else:
        raise SystemExit(
            f"keyflip supports macOS and Windows; this is {sys.platform}."
        )
    return backend


# --------------------------------------------------------------------------
# daemon
# --------------------------------------------------------------------------
class Daemon:
    def __init__(self, config: Config, backend, verbose: bool = False):
        self.config = config
        self.backend = backend
        self.verbose = verbose
        self.flipper = Flipper(config, backend)
        self.flips = 0
        self.last = ""
        self.listener = backend.HotkeyListener(self._bindings())

    def _bindings(self):
        pairs = [(self.config.hotkey, None),
                 (self.config.hotkey_to_thai, EN2TH),
                 (self.config.hotkey_to_english, TH2EN)]
        out = []
        seen: set[tuple] = set()
        for spec, direction in pairs:
            if not spec:
                continue
            parsed = hk.parse(spec, double_tap_ms=self.config.double_tap_ms)
            gesture = parsed.identity()
            if gesture in seen:
                raise SystemExit(f"keyflip: {spec!r} is bound twice")
            seen.add(gesture)
            out.append((parsed, self._make_handler(direction)))
        if not out:
            raise SystemExit("keyflip: no hotkeys configured")
        return out

    def _make_handler(self, direction):
        def handler():
            result = self.flipper.flip(direction)
            if result.status == FLIPPED:
                self.flips += 1
                self.last = f"{result.before} -> {result.after}"
                if self.config.notify:
                    self.backend.notify("keyflip", result.after[:120])
            if self.verbose:
                print(f"keyflip: {result.describe()}", flush=True)
        return handler

    def flip_clipboard_in_place(self, direction: str | None = None) -> str:
        """Convert whatever is on the clipboard, no selection needed."""
        text = self.backend.clipboard_get()
        if not text:
            return "clipboard is empty"
        chosen = direction or detect_direction(text)
        if chosen is None:
            # Same guard as the hotkey path: with no letters either way there
            # is nothing to infer a direction from, and digits would be eaten.
            return "no letters in the clipboard - nothing to infer from"
        out = convert(text, chosen)
        if self.config.normalize_thai:
            out = normalize_thai(out)
        if out == text:
            return "nothing to change"
        self.backend.clipboard_set(out)
        self.flips += 1
        self.last = f"{text} -> {out}"
        return out

    # -- lifecycle ---------------------------------------------------------
    def run_in_thread(self) -> threading.Thread:
        """Pump the hotkeys off the main thread, leaving it for the UI.

        Both the macOS event tap and the Windows message queue belong to the
        thread that installed them, so install and pump together in here.
        """
        def target():
            try:
                self.listener.install()
                self.listener.run_forever()
            except Exception as exc:
                print(f"keyflip: listener stopped: {exc}", file=sys.stderr)

        thread = threading.Thread(target=target, name="keyflip-hotkeys", daemon=True)
        thread.start()
        return thread

    def run_blocking(self) -> None:
        self.listener.install()
        self.listener.run_forever()

    def stop(self) -> None:
        self.listener.stop()


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def _launched_without_a_console() -> bool:
    """True when nobody will ever see what we print."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        return not sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return True


def _record_startup_problem(message: str) -> None:
    """Leave a breadcrumb for a packaged app that refused to start."""
    if not getattr(sys, "frozen", False):
        return
    try:
        from datetime import datetime

        path = config_dir() / "startup.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


def _await_permission(backend) -> bool:
    """Offer the permission, then wait for it, rather than exiting.

    Quitting the moment the check fails is what makes this confusing: the
    grant is per-binary, so the user goes to System Settings, switches keyflip
    on, and comes back to a process that died before they got there.  Nothing
    says so.  Wait instead, and start the moment the switch is flipped.
    """
    print(backend.PERMISSION_HELP, file=sys.stderr)
    _record_startup_problem(backend.PERMISSION_HELP)
    if sys.platform != "darwin":
        return False

    # Launched from Finder there is no stderr to read, so say it on screen.
    # The alert offers to open the settings pane; "Quit" means quit.
    if _launched_without_a_console() and not backend.show_permission_alert():
        return False

    print("keyflip: waiting for Accessibility permission "
          "(this window can stay open)...", file=sys.stderr)
    if not backend.wait_for_accessibility():
        return False

    # Trusted, but the window server can still refuse the tap - and that
    # failure would happen on the listener thread where nobody would see it.
    if not backend.can_tap():
        _record_startup_problem("permission granted but the event tap was refused")
        print("keyflip: permission granted, but macOS still refused the event "
              "tap.\nQuit keyflip and open it again.", file=sys.stderr)
        if _launched_without_a_console():
            backend.show_reopen_alert()
        return False

    print("keyflip: permission granted.", file=sys.stderr)
    return True


def _describe_hotkeys(config: Config) -> list[str]:
    rows = []
    for spec, label in ((config.hotkey, "flip (auto-detect)"),
                        (config.hotkey_to_thai, "force English -> Thai"),
                        (config.hotkey_to_english, "force Thai -> English")):
        if spec:
            rows.append(f"  {hk.parse(spec).pretty(sys.platform):<22} {label}")
    return rows


def _welcome_message(config: Config) -> str:
    """What a fresh install says, so a setup window that just closes is not a mystery."""
    if not config.hotkey:
        return "keyflip is running."
    key = hk.parse(config.hotkey).pretty(sys.platform)
    return (f"keyflip is running. Select text typed in the wrong layout, "
            f"then press {key} to flip it.")


def cmd_run(args) -> int:
    # The daemon's output is usually redirected to a log (launchd, a Startup
    # shortcut, a background shell), where block buffering would hide every
    # line until the buffer filled or the process died.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    config = Config.load()
    if args.hotkey:
        config.hotkey = args.hotkey
    backend = load_backend()

    if not backend.has_accessibility(prompt=True) and not _await_permission(backend):
        return 2

    daemon = Daemon(config, backend, verbose=args.verbose)
    print(f"keyflip {__version__} - watching for:")
    print("\n".join(_describe_hotkeys(config)))

    use_tray = not args.no_tray
    if use_tray:
        try:
            from .tray import run_tray
        except ImportError as exc:
            print(f"keyflip: no tray available ({exc}); running in the console.")
            use_tray = False

    try:
        if use_tray:
            daemon.run_in_thread()
            run_tray(daemon, announce=_welcome_message(config) if args.welcome else None)
        else:
            print("Press Ctrl+C to quit.")
            daemon.run_blocking()
    except KeyboardInterrupt:
        print("\nkeyflip: stopped.")
    finally:
        daemon.stop()
    return 0


def cmd_convert(args) -> int:
    text = " ".join(args.text) if args.text else sys.stdin.read().rstrip("\n")
    direction = {"thai": EN2TH, "english": TH2EN, "auto": None}[args.to]
    out = convert(text, direction)
    if args.normalize:
        out = normalize_thai(out)
    print(out)
    return 0


def cmd_doctor(args) -> int:
    config = Config.load()
    print(f"keyflip {__version__}")
    print(f"  python      {sys.version.split()[0]}  ({sys.platform})")
    print(f"  config      {config_path()}"
          f"{'' if config_path().exists() else '  (defaults, not yet written)'}")

    ok = True
    print("  hotkeys")
    for spec, label in ((config.hotkey, "flip"),
                        (config.hotkey_to_thai, "-> Thai"),
                        (config.hotkey_to_english, "-> English")):
        if not spec:
            continue
        try:
            parsed = hk.parse(spec)
            print(f"    {parsed.pretty(sys.platform):<22} {label}  ok")
        except hk.HotkeyError as exc:
            ok = False
            print(f"    {spec:<22} {label}  INVALID: {exc}")

    try:
        backend = load_backend()
    except SystemExit as exc:
        print(f"  backend     {exc}")
        return 1

    if sys.platform == "darwin":
        trusted = backend.has_accessibility()
        print(f"  accessibility {'granted' if trusted else 'NOT GRANTED'}")
        if not trusted:
            ok = False
            print()
            print(backend.PERMISSION_HELP)
    else:
        print("  accessibility n/a on Windows")

    try:
        serial = backend.clipboard_serial()
        print(f"  clipboard   reachable (change counter {serial})")
    except OSError as exc:
        ok = False
        print(f"  clipboard   FAILED: {exc}")

    print("\nall good" if ok else "\nsomething above needs attention")
    return 0 if ok else 1


def cmd_hotkey(args) -> int:
    config = Config.load()
    if not args.combo:
        print("\n".join(_describe_hotkeys(config)))
        return 0
    try:
        parsed = hk.parse(args.combo)
    except hk.HotkeyError as exc:
        print(f"keyflip: {exc}", file=sys.stderr)
        return 1
    setattr(config, {"flip": "hotkey", "thai": "hotkey_to_thai",
                     "english": "hotkey_to_english"}[args.which], parsed.spec)
    path = config.save()
    print(f"{parsed.pretty(sys.platform)} saved to {path}")
    print("Restart keyflip for it to take effect.")
    return 0


def cmd_config(args) -> int:
    path = config_path()
    if args.write and not path.exists():
        Config().save()
        print(f"wrote defaults to {path}")
        return 0
    if not path.exists():
        print(f"{path} does not exist yet; run 'keyflip config --write' to create it.")
        return 0
    print(path)
    print(path.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keyflip",
        description="Retype the selected text as if the other keyboard layout "
                    "had been active (Thai Kedmanee <-> US QWERTY).",
    )
    parser.add_argument("--version", action="version", version=f"keyflip {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="listen for the hotkey (default)")
    run.add_argument("--hotkey", help="override the configured shortcut for this run")
    run.add_argument("--no-tray", action="store_true", help="stay in the console")
    run.add_argument("--welcome", action="store_true",
                     help="announce that keyflip is running (the installer uses this)")
    run.add_argument("-v", "--verbose", action="store_true", help="log every flip")
    run.set_defaults(func=cmd_run)

    conv = sub.add_parser("convert", help="convert text on the command line")
    conv.add_argument("text", nargs="*", help="text to convert (default: stdin)")
    conv.add_argument("--to", choices=("auto", "thai", "english"), default="auto")
    conv.add_argument("--normalize", action="store_true",
                      help="fold SARA E + SARA E into SARA AE")
    conv.set_defaults(func=cmd_convert)

    doc = sub.add_parser("doctor", help="check permissions and configuration")
    doc.set_defaults(func=cmd_doctor)

    key = sub.add_parser("hotkey", help="show or change the shortcut")
    key.add_argument("combo", nargs="?",
                     help="e.g. double-rshift, or a chord like ctrl+alt+cmd+l")
    key.add_argument("--which", choices=("flip", "thai", "english"), default="flip")
    key.set_defaults(func=cmd_hotkey)

    cfg = sub.add_parser("config", help="show the config file")
    cfg.add_argument("--write", action="store_true", help="create it with defaults")
    cfg.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") and argv[0] not in ("--version", "-h", "--help"):
        argv.insert(0, "run")
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["run"])
    try:
        return args.func(args)
    except hk.HotkeyError as exc:
        print(f"keyflip: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
