#!/usr/bin/env python3
"""Roku adapter — ECP protocol, plain HTTP on port 8060. Zero dependencies,
no pairing, works with Roku TVs and sticks on the same network.
"""

import re
import json
import urllib.request

from samsung import TVError, load_config, save_config, wol  # noqa: F401
from samsung import catalog_apps as _file_catalog


def catalog_apps():
    """Live channel list (Roku exposes it freely); catalog file as fallback."""
    try:
        return get_tv()[0].apps()
    except Exception:
        return _file_catalog()

KEY_MAP = {
    "KEY_UP": "Up", "KEY_DOWN": "Down", "KEY_LEFT": "Left", "KEY_RIGHT": "Right",
    "KEY_ENTER": "Select", "KEY_RETURN": "Back", "KEY_HOME": "Home",
    "KEY_VOLUP": "VolumeUp", "KEY_VOLDOWN": "VolumeDown", "KEY_MUTE": "VolumeMute",
    "KEY_POWER": "PowerOff", "KEY_PLAY": "Play", "KEY_PAUSE": "Play",
    "KEY_FF": "FastForward", "KEY_REWIND": "Rev", "KEY_CHUP": "ChannelUp",
    "KEY_CHDOWN": "ChannelDown", "KEY_INFO": "Info", "KEY_MENU": "Options",
}


def is_paired(cfg):
    return True  # ECP needs no pairing


def get_tv():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured yet — run:  python3 tv.py discover")
    return RokuTV(cfg["ip"]), cfg


def pair():
    print("Roku needs no pairing — ECP is open on the local network.")
    return None


class RokuTV:
    def __init__(self, ip):
        self.base = f"http://{ip}:8060"

    def _post(self, path, payload=None):
        req = urllib.request.Request(self.base + path, method="POST",
                                     data=(payload.encode() if payload else b""))
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                return r.read()
        except Exception as e:
            raise TVError(f"Roku command failed: {e}")

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=6) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            raise TVError(f"Roku query failed: {e}")

    def apps(self):
        """Live channel list with IDs (Roku exposes this over ECP)."""
        xml = self._get("/query/apps")
        out = []
        for m in re.finditer(r'<app[^>]*\bid="([^"]+)"[^>]*>([^<]+)</app>', xml):
            out.append({"appId": m.group(1), "name": m.group(2).strip(),
                        "ids": {"roku": m.group(1)}})
        out.sort(key=lambda a: a["name"].lower())
        return out

    def launch(self, app_id):
        self._post(f"/launch/{app_id}")

    def key(self, name):
        ro = KEY_MAP.get(name)
        if not ro:
            raise TVError(f"unsupported key on Roku: {name}")
        self._post(f"/keypress/{ro}")

    def power(self):
        self.key("KEY_POWER")

    def open_browser(self, url):
        raise TVError("Roku has no open browser — launch a channel instead")
