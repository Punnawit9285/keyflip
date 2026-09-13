# keyflip

Select text that came out in the wrong keyboard layout, press one shortcut, and
it is retyped correctly in place. Thai Kedmanee ⇄ US QWERTY, on macOS and
Windows.

```
รสนอำันีแสฟีกำ   →  iloveyouclaude
ggvxgxbh]        →  เเอปเปิ้ล
l;ylfu8iy[       →  สวัสดีครับ
```

It works in any app that supports copy and paste: Chrome, Word, Anki, Line,
Slack, Notes, the terminal.

---

## Install

Download the latest build from the
[Releases page](https://github.com/Punnawit9285/keyflip/releases). No terminal
needed.

### macOS

Open the `.dmg` — `arm64` for Apple silicon, `x86_64` for Intel — and drag
keyflip to Applications. Open it from there.

On first launch it asks for Accessibility permission and offers to take you
straight to the right pane:

> System Settings → Privacy & Security → **Accessibility** → turn on **keyflip**

**keyflip starts by itself the moment you flip that switch** — you do not have
to open it again. Every shortcut utility on macOS needs this permission; there
is no way to read a global hotkey without it.

It then lives in the menu bar as **ก⇄A**, with no Dock icon. Tick **Start at
login** in its menu and you are done.

> Because this build is not signed with a paid Apple Developer ID, macOS will
> say the developer cannot be verified. To get past it once:
> **right-click keyflip in Applications → Open → Open**. Drag it out of the
> disk image to Applications *before* opening it — an app run from inside a
> downloaded `.dmg` is launched from a temporary read-only copy, and an
> Accessibility grant can never stick to that.

### Windows

Open `keyflip-<version>-setup.exe` and click **Install**. That is the whole
installation — one click. There is no administrator prompt (it installs for
the current user only), no questions, and keyflip needs no permissions at all
on Windows.

It starts as soon as setup closes, says so with a notification, and from then
on starts at every sign-in. Untick **Start at login** in its tray menu to stop
that; upgrading later will not switch it back on. Uninstall from **Settings →
Apps** like anything else.

SmartScreen may warn that the publisher is unknown, because the installer is
not code-signed: **More info → Run anyway**.

### From source

```sh
git clone https://github.com/Punnawit9285/keyflip && cd keyflip
python3 -m venv .venv && .venv/bin/python -m pip install -e .
.venv/bin/keyflip
```

Run this way, the Accessibility permission belongs to your *terminal* rather
than to keyflip. To build the downloadable artifacts yourself:

```sh
./packaging/build_macos.sh && ./packaging/build_dmg.sh   # macOS
.\packaging\build_windows.ps1                            # Windows
```

---

## The shortcut

**Tap the right ⇧ Shift twice** — same gesture on macOS and Windows.

Your left hand never leaves the text, there is no chord to memorise, and it is
the same motion on both platforms.

### Why this one does not collide with anything

A modifier on its own has nothing to modify, so no application anywhere binds
it. There is no chord to lose, no letter to give up, and nothing to check
against Chrome, Office, Anki or a GPU overlay — they all live in the one- and
two-modifier space, which keyflip now leaves entirely alone.

The whole design problem moves somewhere else: right shift is a key you press
dozens of times a minute while typing, so the gesture has to be recognised
without going off mid-sentence. A tap only counts when the key was pressed
**for its own sake**:

| What you do | Does it fire? |
| --- | --- |
| Tap right shift, tap it again within 400 ms | **yes** |
| Type `Hello World` — right shift twice, with a letter each time | no: a key pressed while shift was held cancels the tap |
| Hold right shift and let go | no: a tap has to be short, not held |
| Tap the **left** shift twice | no: the two shifts are separate keys, so the other one stays free |
| Tap once, pause, tap again | no: the second tap has to land inside the window |
| Tap three times | one flip, not two |

There are tests for every row of that table.

Two more things keep it out of the way:

- **The key is matched by position, not by the character it produces.** You are
  mid-sentence on a Thai layout when you reach for this, so it reads hardware
  key codes; the shortcut is identical in both layouts.
- **Shift is never swallowed.** Both taps reach the application exactly as
  normal — anything else would break typing capitals.

### Changing it

```sh
keyflip hotkey "double-rctrl"                     # another double tap
keyflip hotkey "ctrl+alt+shift+k"                 # or a plain chord
keyflip hotkey --which thai    "ctrl+alt+cmd+t"   # force English → Thai
keyflip hotkey --which english "ctrl+alt+cmd+e"   # force Thai → English
```

Double taps are `double-rshift`, `double-lshift`, `double-rctrl`,
`double-lctrl`, `double-ralt`, `double-lalt`, `double-rcmd`, `double-lcmd`
(`cmd` = `win`). `double right shift`, `rshift x2` and `rshift rshift` all mean
the same thing. Widen or tighten the window with `double_tap_ms` in the config.

Chords still work: modifiers are `ctrl`, `alt` (= `option`), `shift`, `cmd`
(= `win`), and at least two are required — one modifier plus a letter is almost
certainly already taken by something. Safe chords if you prefer one:
`ctrl+alt+shift+;`, `ctrl+alt+shift+space`, `ctrl+alt+cmd+\`, or any
`F13`–`F19`.

---

## How it works

There is no API on either OS for "give me the text the user has selected", so
keyflip does the same thing every tool in this category does — with the failure
modes handled:

1. Wait for you to let go of the shortcut. Anything it types while shift is
   still physically down would arrive at the app as a different chord.
2. Remember your clipboard, then send **Copy**.
3. Watch the clipboard's change counter. If it never changes, nothing was
   selected — stop, touch nothing.
4. Detect the direction, convert, send **Paste**.
5. Put your clipboard back.

It never pastes when the text would not change, and it declines when there is
nothing to infer a direction from: a selected `2026` or `+66 81-234-5678` is
left alone, because digits and punctuation sit on *both* layouts and guessing
would quietly mangle them. Use a one-way shortcut if you really do want those
converted.

### What it costs to watch for the shortcut

On **macOS** a `CGEventTap` sees the keys either way, and its callback compares
two integers and hands the event straight back. Nothing is logged, buffered, or
inspected.

On **Windows** it depends on which shortcut you use, and this is the one real
trade-off the double tap makes:

- A **chord** goes through `RegisterHotKey`, which asks the window manager to
  reserve one combination. keyflip is then not in the keystroke path at all,
  and if another program already owns the chord you are told at startup instead
  of the two silently fighting.
- A **double tap** cannot be registered — `RegisterHotKey` has no way to say
  "this modifier, twice, on its own" — so it needs a `WH_KEYBOARD_LL` hook,
  which does put the program in the delivery path of every keystroke. That is
  the class of tool with a reputation for input lag in games and for upsetting
  anti-cheat and driver overlays. The hook is installed **only** when a double
  tap is configured, and its callback does nothing but compare a virtual-key
  code against a small dict before passing the key on. If you would rather not
  have it there at all, set a chord instead:

  ```sh
  keyflip hotkey "ctrl+alt+shift+l"
  ```

---

## Configuration

`keyflip config` prints the path and contents.
`keyflip config --write` creates it with the defaults.

- macOS — `~/Library/Application Support/keyflip/config.json`
- Windows — `%APPDATA%\keyflip\config.json`

| Key | Default | |
| --- | --- | --- |
| `hotkey` | `"double-rshift"` | the main flip, direction auto-detected |
| `hotkey_to_thai` | `""` | optional one-way shortcut |
| `hotkey_to_english` | `""` | optional one-way shortcut |
| `double_tap_ms` | `400` | how long the second tap has to arrive |
| `normalize_thai` | `false` | fold a typed `เ`+`เ` into `แ` (see below) |
| `restore_clipboard` | `true` | put your own clipboard back after pasting |
| `copy_timeout_ms` | `600` | how long to wait for the app to answer the copy |
| `paste_settle_ms` | `350` | how long to leave the text on the clipboard |
| `modifier_release_timeout_ms` | `1000` | how long to wait for your hand to come off |
| `notify` | `false` | desktop notification on each flip (macOS) |

**Start at login** is a tick in the menu rather than a config key. macOS gets a
LaunchAgent at `~/Library/LaunchAgents/com.keyflip.agent.plist`; Windows gets a
`keyflip` value under `HKCU\...\CurrentVersion\Run`. Both are per-user, need no
administrator rights, and untick cleanly — deleting either by hand also works.

### About `normalize_thai`

`ggvxgxbh]` converts to `เเอปเปิ้ล` — two SARA E, because that is literally what
`g` `g` types on a Thai keyboard. It looks identical to `แอปเปิ้ล` but is a
different string, so search and spellcheck will not match it. Turning
`normalize_thai` on folds the pair into a single `แ`. It is off by default
because it is a spelling fix rather than a layout fix, and it means the
conversion no longer round-trips exactly.

---

## Command line

```sh
keyflip run                 # listen for the shortcut (the default)
keyflip run --no-tray -v    # stay in the console and log every flip
keyflip convert 'ggvxgxbh]' # convert without touching the clipboard
keyflip convert --to thai --normalize 'ggvxgxbh]'
keyflip doctor              # check permissions, shortcut, clipboard
keyflip hotkey              # show the current bindings
keyflip config
```

---

## Troubleshooting

**Nothing happens when I press the shortcut.** Run `keyflip doctor`. On macOS
the usual cause is that Accessibility permission is attached to the wrong
binary — macOS pins the grant to the binary's signature, so a rebuilt or
replaced app needs a fresh one. Remove keyflip from the Accessibility list with
**−**, add it again with **+**, and if it is still refused:

```sh
tccutil reset Accessibility com.keyflip.app
```

**The app bounces and disappears when I open it.** That is the permission check
failing. It should show an alert explaining so; if you want the detail in
writing, it is appended to
`~/Library/Application Support/keyflip/startup.log`. Note that running
`keyflip` from a terminal can *look* like it works while the app itself does
not — a terminal-launched process inherits the terminal's permission, so the
grant you need is the one on `keyflip.app`.

**It works everywhere except one app.** On Windows, a shortcut pressed while an
elevated (administrator) window has focus only reaches an elevated program; run
keyflip as administrator too. On macOS, a few apps refuse synthetic ⌘C — try
the menu-bar item's **Flip clipboard now** instead: copy manually, flip, paste.

**"another program already owns …"** on Windows means exactly that. Pick
another combination with `keyflip hotkey`.

**It fires while I am typing.** It should not — a shift press that modifies
another key never counts as a tap. If it still happens, lower `double_tap_ms`.
And if it is not firing when you want it to, raise it.

**The wrong direction was chosen.** Auto-detection goes by whether the
selection contains Thai script. For a mixed selection, select less — or bind
the one-way shortcuts.

---

## Development

```sh
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

The layout table lives in `src/keyflip/layout.py` as one row per physical key,
written with `\u` escapes because several Thai characters are combining marks
that cannot be proofread in a literal table. The tests check it is a clean
bijection in both directions.

MIT.
