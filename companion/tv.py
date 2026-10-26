#!/usr/bin/env python3
"""Fresh Home companion — local launcher + remote for your TV. Zero deps.

Brand-agnostic: the adapter (samsung | lg | roku) is chosen by the "brand"
field in config.json, set automatically by discovery.

  python3 tv.py discover        find TVs on this network (any brand)
  python3 tv.py pair            one-time pairing (Samsung/LG; Roku needs none)
  python3 tv.py apps            list apps (live list on LG/Roku, catalog on Samsung)
  python3 tv.py launch <query>  launch an app (fuzzy): tv.py launch netflix
  python3 tv.py key <KEY>       send a key: KEY_VOLUP, KEY_MUTE, KEY_HOME…
  python3 tv.py power           power off
  python3 tv.py browse <url>    open a URL in the TV's browser
  python3 tv.py wake            wake the TV (Wake-on-LAN)
  python3 tv.py serve           web launcher + phone remote + bridge (port 8590)
"""

import argparse
import base64
import difflib
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discover

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()
PAIRING = {"active": False, "message": ""}


def _brand():
    """The adapter module for the configured TV brand (samsung | lg | roku)."""
    import importlib
    try:
        with open(os.path.join(HERE, "config.json")) as f:
            name = json.load(f).get("brand") or "samsung"
    except Exception:
        name = "samsung"
    if name not in ("samsung", "lg", "roku"):
        name = "samsung"
    return importlib.import_module(name)


# --- controller bridge relay -------------------------------------------------
# /bridge      — page on the Mac/phone: reads a gamepad, streams over WS
# /ws/bridge   — websocket the bridge page connects to (sends input)
# /ws/feed     — websocket the TV launcher connects to (receives input)

FEED_CLIENTS = set()
FEED_LOCK = threading.Lock()
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_read_frame(rfile):
    """Read one client (masked) frame; returns (opcode, payload bytes) or None."""
    hdr = rfile.read(2)
    if len(hdr) < 2:
        return None
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked, n = b2 & 0x80, b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", rfile.read(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", rfile.read(8))[0]
    mask = rfile.read(4) if masked else b""
    data = rfile.read(n) if n else b""
    if masked and data:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


def _ws_send_text(sock, text):
    """Send an unmasked server text frame."""
    payload = text.encode()
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + payload)


def _ws_handshake(handler):
    key = handler.headers.get("Sec-WebSocket-Key", "")
    accept = base64.b64encode(
        hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
    handler.connection.sendall(
        ("HTTP/1.1 101 Switching Protocols\r\n"
         "Upgrade: websocket\r\n"
         "Connection: Upgrade\r\n"
         "Sec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())


def _handle_bridge_ws(handler):
    """Bridge page connection: read input frames, relay to every feed client."""
    _ws_handshake(handler)
    sock = handler.connection
    try:
        while True:
            frame = _ws_read_frame(handler.rfile)
            if frame is None:
                break
            opcode, data = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:  # ping -> pong
                sock.sendall(bytes([0x8A, 0x00]))
                continue
            if opcode != 0x1:
                continue
            with FEED_LOCK:
                targets = list(FEED_CLIENTS)
            for c in targets:
                try:
                    _ws_send_text(c, data.decode("utf-8", "replace"))
                except OSError:
                    with FEED_LOCK:
                        FEED_CLIENTS.discard(c)
    except OSError:
        pass


def _handle_feed_ws(handler):
    """TV launcher connection: register, then keep the socket alive."""
    _ws_handshake(handler)
    sock = handler.connection
    with FEED_LOCK:
        FEED_CLIENTS.add(sock)
    try:
        while True:
            frame = _ws_read_frame(handler.rfile)
            if frame is None or frame[0] == 0x8:
                break
            if frame[0] == 0x9:
                sock.sendall(bytes([0x8A, 0x00]))
    except OSError:
        pass
    finally:
        with FEED_LOCK:
            FEED_CLIENTS.discard(sock)


# ------------------------------------------------------------------ cli ----

def cmd_discover(args):
    return discover.main()


def cmd_pair(args):
    B = _brand()
    cfg = B.load_config()
    if not cfg.get("ip"):
        print("TV not configured — run:  python3 tv.py discover")
        return 1
    print(f"Pairing with {cfg.get('friendly') or 'the TV'} "
          f"({cfg.get('brand', 'samsung')}) at {cfg['ip']}…")
    B.pair()
    return 0


def cmd_apps(args):
    B = _brand()
    for a in B.catalog_apps():
        print(f"{a['appId']:>28}  {a['name']}")
    return 0


def _pick(query):
    apps = _brand().catalog_apps()
    q = query.lower().strip()
    for a in apps:
        ids = [a["appId"]] + a.get("alt", [])
        if query in ids or a["name"].lower() == q:
            return a
    close = difflib.get_close_matches(q, [a["name"].lower() for a in apps], n=1, cutoff=0.3)
    if close:
        return next(a for a in apps if a["name"].lower() == close[0])
    return None


def cmd_launch(args):
    tv, _ = _brand().get_tv()
    app = _pick(args.app)
    if not app:
        print(f'No app matching "{args.app}". See:  python3 tv.py apps')
        return 1
    print(f"Launching {app['name']}…")
    tv.launch(app["appId"])
    return 0


def cmd_key(args):
    tv, _ = _brand().get_tv()
    tv.key(args.key.upper())
    return 0


def cmd_power(args):
    tv, _ = _brand().get_tv()
    tv.power()
    return 0


def cmd_browse(args):
    tv, _ = _brand().get_tv()
    url = args.url if "://" in args.url else "https://" + args.url
    print(f"Opening {url} on the TV…")
    tv.open_browser(url)
    return 0


def cmd_wake(args):
    B = _brand()
    cfg = B.load_config()
    if not cfg.get("mac"):
        print("No MAC in config.json (run discover.py while the TV is awake).")
        return 1
    B.wol(cfg["mac"])
    print("Wake-on-LAN packets sent.")
    return 0


# ---------------------------------------------------------------- server ----

def _tv_from_config():
    B = _brand()
    try:
        return B.get_tv()
    except SystemExit:
        return None, B.load_config()


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "TVLauncher/2.0"

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            # websocket endpoints for the controller bridge (raw socket upgrade)
            if self.path in ("/ws/bridge", "/ws/feed") and \
                    "upgrade" in (self.headers.get("Connection") or "").lower():
                if self.path == "/ws/bridge":
                    _handle_bridge_ws(self)
                else:
                    _handle_feed_ws(self)
                return
            if self.path == "/remote":
                self._serve_file("remote.html")
                return
            if self.path == "/bridge":
                self._serve_file("bridge.html")
                return
            try:
                if self.path in ("/", "/index.html"):
                    self._serve_file("index.html")
                elif self.path == "/api/status":
                    B = _brand()
                    tv, cfg = _tv_from_config()
                    self._json({
                        "found": bool(cfg.get("ip")),
                        "paired": B.is_paired(cfg),
                        "brand": cfg.get("brand", "samsung"),
                        "ip": cfg.get("ip"), "model": cfg.get("model"),
                        "friendly": cfg.get("friendly"),
                        "pairing": PAIRING["active"],
                        "pairing_message": PAIRING["message"],
                    })
                elif self.path == "/api/apps":
                    tv, cfg = _tv_from_config()
                    if not tv:
                        self._json({"error": "TV not discovered yet"}, 409)
                    else:
                        self._json({"apps": _brand().catalog_apps()})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:
                self._json({"error": f"TV unreachable: {e}"}, 503)

        def _serve_file(self, name):
            with open(os.path.join(HERE, name), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                if self.path == "/api/launch":
                    body = self._body()
                    tv, _ = _tv_from_config()
                    with LOCK:
                        tv.launch(body.get("id", ""))
                    self._json({"ok": True})
                elif self.path == "/api/key":
                    body = self._body()
                    tv, _ = _tv_from_config()
                    with LOCK:
                        tv.key(body.get("key", ""))
                    self._json({"ok": True})
                elif self.path == "/api/power":
                    tv, _ = _tv_from_config()
                    with LOCK:
                        tv.power()
                    self._json({"ok": True})
                elif self.path == "/api/wake":
                    B = _brand()
                    cfg = B.load_config()
                    ok = B.wol(cfg.get("mac", ""))
                    self._json({"ok": ok})
                elif self.path == "/api/browse":
                    body = self._body()
                    tv, _ = _tv_from_config()
                    with LOCK:
                        tv.open_browser(body.get("url", ""))
                    self._json({"ok": True})
                elif self.path == "/api/pair":
                    if PAIRING["active"]:
                        self._json({"ok": True, "started": False})
                        return

                    def run():
                        B = _brand()
                        PAIRING.update(active=True, message="Looking for the TV…")
                        try:
                            cfg = B.load_config()
                            if not cfg.get("ip"):
                                rec = discover.find_tv(verbose=False)
                                if not rec:
                                    PAIRING.update(active=False,
                                                   message="No TV found — turn it on and re-scan")
                                    return
                                cfg = B.save_config(ip=rec["ip"], mac=rec.get("mac"),
                                                    model=rec.get("model"),
                                                    friendly=rec.get("friendly"))
                            PAIRING.update(message="Waiting for Allow on the TV…")
                            B.pair()
                            PAIRING.update(active=False, message="")
                        except Exception as e:
                            PAIRING.update(active=False, message=str(e))

                    threading.Thread(target=run, daemon=True).start()
                    self._json({"ok": True, "started": True})
                elif self.path == "/api/discover":
                    rec = discover.find_tv(verbose=False)
                    self._json({"ok": bool(rec)})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:
                self._json({"error": str(e)}, 500)

    return Handler


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def cmd_serve(args):
    B = _brand()
    cfg = B.load_config()
    if not cfg.get("ip"):
        print("No TV configured — discovering…")
        if not discover.find_tv(verbose=True):
            print("Couldn't find a TV. Turn it on / check Wi-Fi, then: python3 tv.py serve")
            return 1
        cfg = B.load_config()

    port, httpd = args.port, None
    for _ in range(10):
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler())
            break
        except OSError:
            port += 1
    if not httpd:
        print("Could not bind a port.")
        return 1

    print(f"\n  Fresh Home →   http://localhost:{port}")
    lan = _lan_ip()
    if lan:
        print(f"  from phone →   http://{lan}:{port}  (/remote for the phone remote)")
    paired = B.is_paired(cfg)
    print(f"  TV: {cfg.get('friendly') or cfg['ip']} ({cfg.get('brand', 'samsung')}, {cfg['ip']})"
          f"  —  {'paired ✓' if paired else 'needs pairing (click Pair in the web UI)'}\n")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


# ------------------------------------------------------------------ main ----

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover").set_defaults(fn=cmd_discover)
    sub.add_parser("pair").set_defaults(fn=cmd_pair)
    sub.add_parser("apps").set_defaults(fn=cmd_apps)
    sp = sub.add_parser("launch")
    sp.add_argument("app")
    sp.set_defaults(fn=cmd_launch)
    sp = sub.add_parser("key")
    sp.add_argument("key")
    sp.set_defaults(fn=cmd_key)
    sp = sub.add_parser("browse")
    sp.add_argument("url", help="open this URL in the TV's browser")
    sp.set_defaults(fn=cmd_browse)
    sub.add_parser("power").set_defaults(fn=cmd_power)
    sub.add_parser("wake").set_defaults(fn=cmd_wake)
    sp = sub.add_parser("serve")
    sp.add_argument("--port", type=int, default=8590)
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(fn=cmd_serve)
    args = p.parse_args()
    try:
        rc = args.fn(args) or 0
    except KeyboardInterrupt:
        rc = 130
    except (_brand().TVError, OSError) as e:
        print(f"error: {e}")
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
