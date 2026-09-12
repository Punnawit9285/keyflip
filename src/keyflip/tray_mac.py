"""A menu-bar item for macOS, built on NSStatusItem.

NSApp's run loop is the main CFRunLoop, and the event tap lives on the hotkey
thread's own run loop, so the two never contend.

Everything defined inside an NSObject subclass becomes an Objective-C method,
so plain helpers stay at module level where PyObjC will not try to bridge them.
"""

from __future__ import annotations

import subprocess

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from . import hotkey as hk
from .config import Config, config_path

#: NSStatusItem holds only a weak-ish reference; keep ours alive here.
_RETAIN: list = []


def _disabled_item(menu, title):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
    item.setEnabled_(False)
    menu.addItem_(item)
    return item


def _action_item(menu, title, target, action, key=""):
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
    item.setTarget_(target)
    menu.addItem_(item)
    return item


class KeyflipController(NSObject):
    def initWithDaemon_(self, daemon):
        self = objc.super(KeyflipController, self).init()
        if self is None:
            return None
        self.daemon = daemon
        self.statusRow = None
        self.item = None
        return self

    def buildMenu(self):
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self.item.button()
        button.setTitle_("ก⇄A")
        button.setToolTip_("keyflip — flip the selection between Thai and English")

        menu = NSMenu.alloc().init()
        menu.setDelegate_(self)

        self.statusRow = _disabled_item(menu, "No flips yet")
        menu.addItem_(NSMenuItem.separatorItem())

        cfg = self.daemon.config
        for spec, label in ((cfg.hotkey, "flip selection"),
                            (cfg.hotkey_to_thai, "force → Thai"),
                            (cfg.hotkey_to_english, "force → English")):
            if spec:
                _disabled_item(menu, f"{hk.parse(spec).pretty('darwin')}   {label}")

        menu.addItem_(NSMenuItem.separatorItem())
        _action_item(menu, "Flip clipboard now", self, "flipClipboard:")
        _action_item(menu, "Open config file", self, "openConfig:")
        menu.addItem_(NSMenuItem.separatorItem())
        _action_item(menu, "Quit keyflip", self, "quitApp:", "q")

        self.item.setMenu_(menu)

    # -- NSMenuDelegate ----------------------------------------------------
    def menuWillOpen_(self, menu):
        count = self.daemon.flips
        if not count:
            self.statusRow.setTitle_("No flips yet")
            return
        last = self.daemon.last
        if len(last) > 46:
            last = last[:45] + "…"
        self.statusRow.setTitle_(f"{count} flip{'' if count == 1 else 's'}  ·  {last}")

    # -- actions -----------------------------------------------------------
    def flipClipboard_(self, sender):
        self.daemon.flip_clipboard_in_place()

    def openConfig_(self, sender):
        path = config_path()
        if not path.exists():
            Config().save(path)
        subprocess.run(["open", str(path)], check=False)

    def quitApp_(self, sender):
        self.daemon.stop()
        NSApplication.sharedApplication().terminate_(self)


def run_tray(daemon) -> None:
    app = NSApplication.sharedApplication()
    # Accessory: menu-bar presence, no Dock icon, no menu bar of its own.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = KeyflipController.alloc().initWithDaemon_(daemon)
    controller.buildMenu()
    _RETAIN.append(controller)
    app.run()
