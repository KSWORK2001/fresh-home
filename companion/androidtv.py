#!/usr/bin/env python3
"""Android TV / Google TV adapter — ADB over the network. Zero pip deps
(requires the `adb` binary: `brew install android-platform-tools`).

Covers every Android-based set: Sony Bravia (Google TV), TCL and Onn
Google TV models, Philips/Hisense/TCL Android builds, Fire TV sticks
(network ADB), Nvidia Shield.

Setup on the TV (once): Settings → Device Preferences → About → click
"Build" 7× to enable Developer Options → Device Preferences → Developer
Options → Network debugging ON. First `adb connect` shows an allow prompt
on the TV; accept "always".

Status: implemented; not yet validated on physical hardware — reports welcome.
"""

import shutil
import subprocess

from samsung import TVError, load_config, save_config, wol  # noqa: F401
from samsung import catalog_apps as _file_catalog

KEYCODES = {
    "KEY_UP": "KEYCODE_DPAD_UP", "KEY_DOWN": "KEYCODE_DPAD_DOWN",
    "KEY_LEFT": "KEYCODE_DPAD_LEFT", "KEY_RIGHT": "KEYCODE_DPAD_RIGHT",
    "KEY_ENTER": "KEYCODE_DPAD_CENTER", "KEY_RETURN": "KEYCODE_BACK",
    "KEY_HOME": "KEYCODE_HOME", "KEY_VOLUP": "KEYCODE_VOLUME_UP",
    "KEY_VOLDOWN": "KEYCODE_VOLUME_DOWN", "KEY_MUTE": "KEYCODE_VOLUME_MUTE",
    "KEY_POWER": "KEYCODE_POWER", "KEY_PLAY": "KEYCODE_MEDIA_PLAY",
    "KEY_PAUSE": "KEYCODE_MEDIA_PAUSE", "KEY_STOP": "KEYCODE_MEDIA_STOP",
    "KEY_FF": "KEYCODE_MEDIA_FAST_FORWARD", "KEY_REWIND": "KEYCODE_MEDIA_REWIND",
    "KEY_CHUP": "KEYCODE_CHANNEL_UP", "KEY_CHDOWN": "KEYCODE_CHANNEL_DOWN",
    "KEY_MENU": "KEYCODE_MENU", "KEY_INFO": "KEYCODE_INFO",
}


def _adb():
    path = shutil.which("adb")
    if not path:
        raise TVError("adb not found — install it:  brew install android-platform-tools")
    return path


def is_paired(cfg):
    # ADB keys persist after the first on-TV accept; connect is idempotent
    return True


def get_tv():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured yet — run:  python3 tv.py discover")
    return AndroidTV(cfg["ip"]), cfg


def pair():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured — run:  python3 tv.py discover")
    print("On the TV: enable Developer Options → Network debugging, then")
    print("accept the RSA prompt that appears when we connect…")
    tv = AndroidTV(cfg["ip"])
    out = tv._run("connect", f"{cfg['ip']}:5555")
    print(out.strip() or "(no output)")
    if "connected" in out.lower():
        print("✓ Connected (ADB keys cached — no more prompts).")
    else:
        print("!! Could not connect — check Network debugging is ON.")
    return tv


def catalog_apps():
    """Third-party launcher packages as a list; catalog file as fallback."""
    try:
        return get_tv()[0].apps()
    except Exception:
        return _file_catalog()


class AndroidTV:
    def __init__(self, ip):
        self.ip = ip

    def _run(self, *args, timeout=8):
        cmd = [_adb(), *args]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            raise TVError("adb timed out — is the TV awake?")

    def _shell(self, cmd):
        out = self._run("-s", f"{self.ip}:5555", "shell", cmd)
        if "device offline" in out or "not found" in out.lower() and "no devices" in out.lower():
            # reconnect once and retry
            self._run("connect", f"{self.ip}:5555")
            out = self._run("-s", f"{self.ip}:5555", "shell", cmd)
        return out

    def apps(self):
        out = self._shell("pm list packages -3")
        pkgs = [l.replace("package:", "").strip() for l in out.splitlines()
                if l.startswith("package:")]
        out2 = [{"appId": p, "name": p.split(".")[-1].replace("_", " ").title(),
                 "ids": {"androidtv": p}} for p in sorted(pkgs)]
        return out2

    def launch(self, app_id):
        self._shell(f"monkey -p {app_id} -c android.intent.category.LAUNCHER 1")

    def key(self, name):
        kc = KEYCODES.get(name)
        if not kc:
            raise TVError(f"unsupported key on Android TV: {name}")
        self._shell(f"input keyevent {kc}")

    def power(self):
        self.key("KEY_POWER")

    def open_browser(self, url):
        self._shell(f"am start -a android.intent.action.VIEW -d '{url}'")
