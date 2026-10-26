#!/usr/bin/env python3
"""LG webOS adapter — SSAP protocol over WebSocket, zero dependencies.

Reuses the hand-rolled WebSocket client from the Samsung adapter. Pair once
(the TV shows a permission prompt); the returned client-key is cached and
reused forever. Unlike Samsung, webOS still exposes a LIVE app list.

Status: protocol implemented from the SSAP spec and community clients;
not yet validated against a physical webOS TV — reports welcome.
"""

import json
import os
import time

from samsung import (WS, TVError, load_config, save_config, wol,  # noqa: F401
                     catalog_apps as _file_catalog)

NEXT_ID = [0]


def catalog_apps():
    """Live installed-app list when paired; the shared catalog otherwise."""
    try:
        cfg = load_config()
        if is_paired(cfg):
            return get_tv()[0].apps()
    except Exception:
        pass
    return _file_catalog()

POINTER_KEYS = {
    "KEY_UP": "UP", "KEY_DOWN": "DOWN", "KEY_LEFT": "LEFT", "KEY_RIGHT": "RIGHT",
    "KEY_ENTER": "ENTER", "KEY_RETURN": "BACK", "KEY_HOME": "HOME",
    "KEY_CHUP": "CHANNELUP", "KEY_CHDOWN": "CHANNELDOWN",
    "KEY_MENU": "MENU", "KEY_EXIT": "EXIT", "KEY_INFO": "INFO",
}
AUDIO_KEYS = {
    "KEY_VOLUP": "ssap://audio/volumeUp",
    "KEY_VOLDOWN": "ssap://audio/volumeDown",
    "KEY_MUTE": "ssap://audio/setMute",
}
MEDIA_KEYS = {
    "KEY_PLAY": "ssap://media.controls/play",
    "KEY_PAUSE": "ssap://media.controls/pause",
    "KEY_STOP": "ssap://media.controls/stop",
    "KEY_FF": "ssap://media.controls/fastForward",
    "KEY_REWIND": "ssap://media.controls/rewind",
}


def is_paired(cfg):
    return bool(cfg.get("client_key"))


def get_tv():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured yet — run:  python3 tv.py discover")
    return LGTV(cfg["ip"], cfg.get("client_key")), cfg


def pair():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured — run:  python3 tv.py discover")
    print(f"Pairing with webOS TV at {cfg['ip']} — press Allow on the TV…")
    tv = LGTV(cfg["ip"], None)
    tv.pair()
    save_config(client_key=tv.key)
    print("✓ Paired — client-key saved.")
    return tv


class LGTV:
    def __init__(self, ip, key=None, port=3001):
        self.ip = ip
        self.key = key
        self.port = port

    # -- connection plumbing -------------------------------------------------

    def _open(self, timeout=8):
        ws = WS(self.ip, self.port, self.port == 3001, "/", timeout)
        try:
            ws.connect()
        except TVError:
            if self.port == 3001:          # older firmware: plain ws on 3000
                self.port = 3000
                ws = WS(self.ip, 3000, False, "/", timeout)
                ws.connect()
            else:
                raise
        return ws

    def _register(self, ws, wait=60):
        msg = {"type": "register", "pairingType": "PROMPT"}
        if self.key:
            msg["client-key"] = self.key
        ws.send(json.dumps(msg))
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                data = json.loads(ws.recv(3.0))
            except TimeoutError:
                continue
            if data.get("type") == "registered":
                self.key = (data.get("payload") or {}).get("client-key")
                return ws
            if data.get("type") == "error":
                raise TVError(f"webOS refused registration: {data}")
        raise TimeoutError("no registration response — check the TV screen")

    def pair(self):
        ws = self._open()
        try:
            self._register(ws)
            if not self.key:
                raise TVError("TV registered without returning a client-key")
        finally:
            ws.close()

    def _channel(self):
        if not self.key:
            raise TVError("not paired yet — run:  python3 tv.py pair")
        ws = self._open()
        try:
            self._register(ws, wait=8)
        except Exception:
            ws.close()
            raise
        return ws

    def _request(self, ws, uri, payload=None):
        NEXT_ID[0] += 1
        rid = str(NEXT_ID[0])
        ws.send(json.dumps({"type": "request", "id": rid, "uri": uri,
                            "payload": payload or {}}))
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                data = json.loads(ws.recv(2.5))
            except TimeoutError:
                continue
            if data.get("id") == rid:
                return data
        raise TVError(f"no response for {uri}")

    # -- device operations ------------------------------------------------------

    def apps(self):
        """Live installed-app list (webOS still allows this, unlike Tizen)."""
        ws = self._channel()
        try:
            rep = self._request(ws, "ssap://com.webos.applicationManager/listApps")
            apps = (rep.get("payload") or {}).get("apps") or []
            out = [{"appId": a.get("id", ""), "name": a.get("title", "?"),
                    "ids": {"webos": a.get("id", "")}}
                   for a in apps if a.get("id") and a.get("visible", True)]
            out.sort(key=lambda a: a["name"].lower())
            return out
        finally:
            ws.close()

    def launch(self, app_id):
        ws = self._channel()
        try:
            self._request(ws, "ssap://system.launcher/launch", {"id": app_id})
        finally:
            ws.close()

    def power(self):
        self._simple("ssap://system/turnOff")

    def open_browser(self, url):
        self._simple("ssap://system.launcher/open", {"url": url})

    def _simple(self, uri, payload=None):
        ws = self._channel()
        try:
            self._request(ws, uri, payload)
        finally:
            ws.close()

    def key(self, name):
        if name in AUDIO_KEYS:
            payload = {"mute": True} if name == "KEY_MUTE" else {}
            self._simple(AUDIO_KEYS[name], payload)
            return
        if name in MEDIA_KEYS:
            self._simple(MEDIA_KEYS[name])
            return
        if name in POINTER_KEYS:
            self._pointer_button(POINTER_KEYS[name])
            return
        raise TVError(f"unsupported key on webOS: {name}")

    def _pointer_button(self, button):
        """D-pad keys go over a secondary socket obtained from the TV."""
        ws = self._channel()
        pointer_path = None
        try:
            rep = self._request(ws,
                "ssap://com.webos.service.networkinput/getPointerInputSocket")
            pointer_path = (rep.get("payload") or {}).get("socketPath")
        finally:
            ws.close()
        if not pointer_path:
            raise TVError("TV did not provide a pointer-input socket")
        # socketPath looks like wss://<ip>:<port>/<uuid>
        rest = pointer_path.split("://", 1)[1]
        host, _, resource = rest.partition("/")
        host, _, port = host.partition(":")
        pw = WS(host, int(port) or self.port, "wss" in pointer_path or True,
                "/" + resource, 8)
        try:
            pw.connect()
            pw.send(json.dumps({"type": "button", "name": button}))
            time.sleep(0.1)
        finally:
            pw.close()
