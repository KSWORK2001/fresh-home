#!/usr/bin/env python3
"""Sony Bravia adapter — IP Control over HTTP (PSK auth), zero dependencies.

Setup on the TV (once):
  Settings → Network → Home Network Setup → IP Control →
  Authentication → Normal and Pre-Shared Key → set a PSK (any passphrase).

Then:  python3 tv.py pair   (it will ask for that PSK)

Keys go to POST /sony/IRCC (SOAP + IRCC code); apps list/launch use the
JSON-RPC services /sony/appControl and /sony/avContent (setPlayContent).

Status: implemented from Sony's IP-Control documentation and community
references; not yet validated on physical hardware — reports welcome.
"""

import json
import urllib.request

from samsung import TVError, load_config, save_config, wol  # noqa: F401
from samsung import catalog_apps as _file_catalog

# IRCC codes (standard Sony table)
IRCC = {
    "KEY_UP": "AAAAAQAAAAEAAAB0Aw==",
    "KEY_DOWN": "AAAAAQAAAAEAAAB1Aw==",
    "KEY_LEFT": "AAAAAQAAAAEAAAA0Aw==",
    "KEY_RIGHT": "AAAAAQAAAAEAAAAzAw==",
    "KEY_ENTER": "AAAAAQAAAAEAAABlAw==",
    "KEY_RETURN": "AAAAAgAAAJcAAAAjAw==",
    "KEY_HOME": "AAAAAQAAAAEAAABgAw==",
    "KEY_VOLUP": "AAAAAQAAAAEAAAASAw==",
    "KEY_VOLDOWN": "AAAAAQAAAAEAAAATAw==",
    "KEY_MUTE": "AAAAAQAAAAEAAAAUAw==",
    "KEY_POWER": "AAAAAQAAAAEAAAAvAw==",       # PowerOff
    "KEY_CHUP": "AAAAAQAAAAEAAAAQAw==",
    "KEY_CHDOWN": "AAAAAQAAAAEAAAARAw==",
    "KEY_PLAY": "AAAAAgAAAJcAAAAaAw==",
    "KEY_PAUSE": "AAAAAgAAAJcAAAAZAw==",
    "KEY_STOP": "AAAAAgAAAJcAAAAYAw==",
    "KEY_FF": "AAAAAgAAAJcAAAAcAw==",
    "KEY_REWIND": "AAAAAgAAAJcAAAAbAw==",
    "KEY_MENU": "AAAAAgAAAJcAAAA2Aw==",        # Options
    "KEY_INFO": "AAAAAQAAAAEAAAA6Aw==",        # Display
    "KEY_NETFLIX": "AAAAAgAAABoAAAB8Aw==",
    "KEY_YOUTUBE": "AAAAAgAAAMQAAABHAw==",
}

SOAP_IRCC = (
    '<?xml version="1.0"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body><u:X_SendIRCCCommand '
    'xmlns:u="urn:schemas-sony-com:service:IRCC:1">'
    '<CommandName>{code}</CommandName></u:X_SendIRCCCommand></s:Body></s:Envelope>'
)


def is_paired(cfg):
    return bool(cfg.get("psk"))


def get_tv():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured yet — run:  python3 tv.py discover")
    return SonyTV(cfg["ip"], cfg.get("psk")), cfg


def pair():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured — run:  python3 tv.py discover")
    print("On the TV: Settings → Network → Home Network Setup → IP Control →")
    print("           Authentication → Normal and Pre-Shared Key")
    psk = input("Enter the Pre-Shared Key you set on the TV: ").strip()
    if not psk:
        print("No PSK entered — aborted.")
        return None
    tv = SonyTV(cfg["ip"], psk)
    info = tv.system_info()
    save_config(psk=psk)
    print(f"✓ PSK saved — talking to {info.get('model', 'your Bravia')}.")
    return tv


def catalog_apps():
    """Live app list (URIs from the TV); shared catalog as fallback."""
    try:
        cfg = load_config()
        if is_paired(cfg):
            return get_tv()[0].apps()
    except Exception:
        pass
    return _file_catalog()


class SonyTV:
    def __init__(self, ip, psk, port=80):
        self.ip = ip
        self.psk = psk
        self.port = port
        self.rid = 0

    # -- transport -----------------------------------------------------------

    def _post(self, path, body, headers):
        req = urllib.request.Request(
            f"http://{self.ip}:{self.port}{path}", data=body.encode(),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            raise TVError(f"Sony command failed ({path}): {e}")

    def _rpc(self, service, method, params=None, version="1.0"):
        self.rid += 1
        body = json.dumps({"method": method, "params": params or [],
                           "id": self.rid, "version": version})
        rep = self._post(f"/sony/{service}", body,
                         {"X-Auth-PSK": self.psk or "",
                          "Content-Type": "application/json"})
        try:
            data = json.loads(rep)
        except ValueError:
            raise TVError(f"Sony returned non-JSON from {service}")
        if data.get("error") and data["error"] not in (0, None, [0]):
            raise TVError(f"Sony {method}: {data['error']}")
        return data.get("result") or []

    def system_info(self):
        result = self._rpc("system", "getSystemInformation")
        return result[0] if result else {}

    # -- device operations -----------------------------------------------------

    def apps(self):
        result = self._rpc("appControl", "getApplicationList")
        apps = result[0] if result else []
        out = [{"appId": a.get("uri", ""), "name": a.get("title", "?"),
                "ids": {"sony": a.get("uri", "")}}
               for a in apps if a.get("uri")]
        out.sort(key=lambda a: a["name"].lower())
        return out

    def launch(self, app_id):
        self._rpc("avContent", "setPlayContent", [{"uri": app_id}])

    def key(self, name):
        code = IRCC.get(name)
        if not code:
            # allow raw IRCC names too (e.g. "Netflix")
            code = {v: k for k, v in IRCC.items()}.get(name) or \
                   next((c for n, c in IRCC.items() if n.endswith(name.upper())), None)
        if not code:
            raise TVError(f"unsupported key on Sony: {name}")
        self._post("/sony/IRCC", SOAP_IRCC.format(code=code),
                   {"X-Auth-PSK": self.psk or "",
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPACTION": '"urn:schemas-sony-com:service:IRCC:1#X_SendIRCCCommand"'})

    def power(self):
        self.key("KEY_POWER")

    def open_browser(self, url):
        raise TVError("Sony IP control has no browser-open; launch apps instead")
