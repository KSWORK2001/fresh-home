#!/usr/bin/env python3
"""Minimal zero-dependency client for Samsung Tizen TVs (2016+).

Speaks just enough WebSocket and the samsung.remote.control protocol to:
  - pair once and cache the token
  - launch any app by ID (catalog in apps.json; this firmware's ms.webapi
    app-list API is gone, so a curated catalog is used instead)
  - send remote-control key presses

Uses the TV's local control channel on port 8002 (wss + token) with fallback
to port 8001 (legacy ws). Hand-rolled WebSocket so nothing needs installing.
"""

import base64
import json
import os
import socket
import ssl
import struct
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")


class TVError(Exception):
    pass


class PairingNeeded(TVError):
    pass


# ---------------------------------------------------------------- config ----

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(**fields):
    cfg = load_config()
    for k, v in fields.items():
        if v is None:
            continue
        cfg[k] = v
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def get_tv():
    cfg = load_config()
    if not cfg.get("ip"):
        raise SystemExit("TV not configured yet — run:  python3 discover.py")
    tv = SamsungTV(cfg["ip"], cfg.get("token"), cfg.get("tv_name") or "Mac Launcher",
                   cfg.get("port") or 8002, cfg.get("encoding"))
    return tv, cfg


def catalog_apps():
    """The editable app catalog (apps.json next to this file)."""
    with open(os.path.join(HERE, "apps.json")) as f:
        return json.load(f)


# ------------------------------------------------------------- websocket ----

class WS:
    """Tiny WebSocket client (text frames only) over plain or TLS sockets."""

    def __init__(self, host, port, secure, resource, timeout=8):
        self.host, self.port, self.secure = host, port, secure
        self.resource, self.timeout = resource, timeout
        self.buf = b""
        self.sock = None

    def connect(self):
        raw = socket.create_connection((self.host, self.port), self.timeout)
        if self.secure:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                ctx.set_ciphers("DEFAULT:@SECLEVEL=1")  # some TVs negotiate weak TLS
            except Exception:
                pass
            raw = ctx.wrap_socket(raw, server_hostname=self.host)
        self.sock = raw
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {self.resource} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise TVError("connection closed during WebSocket handshake")
            resp += chunk
        head, rest = resp.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status:
            self.close()
            raise TVError(f"WebSocket upgrade rejected: {status}")
        self.buf = rest

    def _read(self, n, deadline):
        while len(self.buf) < n:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for the TV")
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise TimeoutError("timed out waiting for the TV")
            if not chunk:
                raise TVError("connection closed by the TV")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_frame(self, opcode, payload=b""):
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        self.sock.sendall(bytes(header) + masked)

    def send(self, text):
        self._send_frame(0x1, text.encode())

    def recv(self, timeout):
        deadline = time.time() + timeout
        frags = []
        while True:
            b1, b2 = self._read(2, deadline)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            masked, n = b2 & 0x80, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2, deadline))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8, deadline))[0]
            mk = self._read(4, deadline) if masked else b""
            payload = self._read(n, deadline)
            if masked:
                payload = bytes(b ^ mk[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise TVError("the TV closed the connection")
            if opcode == 0x9:  # ping -> pong
                self._send_frame(0xA, payload)
                continue
            if opcode in (0x0, 0x1):  # text frame (with continuation support)
                frags.append(payload)
                if fin:
                    return b"".join(frags).decode("utf-8", "replace")
            # ignore binary / other frames

    def close(self):
        try:
            self._send_frame(0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ----------------------------------------------------------- the protocol ---

class SamsungTV:
    def __init__(self, ip, token=None, name="Mac Launcher", port=None, encoding="utf-8"):
        self.ip = ip
        self.token = token
        self.name = name or "Mac Launcher"
        self.port = port or 8002
        self.encoding = encoding or "utf-8"

    def _resource(self, encoding, token=None):
        b64 = base64.b64encode(self.name.encode(encoding)).decode()
        res = f"/api/v2/channels/samsung.remote.control?name={b64}"
        if token:
            res += f"&token={token}"
        return res

    def _open(self, port=None, encoding=None, token="__keep__", timeout=8):
        tok = self.token if token == "__keep__" else token
        ws = WS(self.ip, port or self.port, (port or self.port) == 8002,
                self._resource(encoding or self.encoding, tok), timeout)
        ws.connect()
        return ws

    def pair(self, wait=90, log=print):
        """Ask the TV for a token. Someone must press Allow on the TV once."""
        errors = []
        for port in (8002, 8001):
            for enc in ("utf-8", "utf-16-le"):
                budget = wait if (port, enc) == (8002, "utf-8") else 15
                try:
                    ws = self._open(port, enc, token=None)
                except (TVError, OSError) as e:
                    errors.append(f"port {port}/{enc}: {e}")
                    continue
                log(f"  → connected on port {port}; press Allow on the TV…")
                t0 = time.time()
                try:
                    deadline = t0 + budget
                    while time.time() < deadline:
                        try:
                            raw = ws.recv(2.0)
                        except TimeoutError:
                            # legacy 8001 often has no pairing flow at all
                            if port == 8001 and time.time() - t0 > 6:
                                self.token, self.port, self.encoding = None, port, enc
                                return self
                            continue
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        token = (msg.get("data") or {}).get("token")
                        if token:
                            self.token, self.port, self.encoding = token, port, enc
                            return self
                        if "denied" in raw.lower():
                            raise TVError('you pressed "Deny" on the TV — run pair again')
                        log(f"  … {raw[:110]}")
                    raise TimeoutError("no Allow within the time window")
                finally:
                    ws.close()
        hint = "\n  (If the TV is awake, its IP may have changed — run: python3 discover.py)"
        raise TVError("could not open a control channel:\n  " + "\n  ".join(errors) + hint)

    def _channel(self, timeout=8):
        """Open a control channel and wait until the TV says it is ready.

        Commands sent before the ms.channel.ready / ms.channel.connect event
        are rejected with `ms.error: No Authorized`, so this ordering matters.
        """
        if not self.token and self.port == 8002:
            raise PairingNeeded("not paired yet — run:  python3 tv.py pair")
        ws = self._open(timeout=timeout)
        try:
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    raw = ws.recv(2.0)
                except TimeoutError:
                    continue
                except TVError:
                    raise PairingNeeded("the TV rejected our token — re-run:  python3 tv.py pair")
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                ev = msg.get("event", "")
                if ev in ("ms.channel.ready", "ms.channel.connect"):
                    return ws
                if ev == "ms.error":
                    detail = (msg.get("data") or {}).get("message", "error")
                    raise PairingNeeded(f'TV said "{detail}" — re-run:  python3 tv.py pair')
            raise TVError("the TV never opened the control channel")
        except Exception:
            ws.close()
            raise

    def launch(self, app_id):
        ws = self._channel()
        try:
            variants = (
                {"Cmd": "RunApp", "DataOfApp": f"APP_{app_id}", "AppId": app_id, "Type": "deepview"},
                {"Cmd": "RunApp", "DataOfApp": f"APP_{app_id}", "AppId": app_id,
                 "ActionType": "NATIVE_LAUNCH"},
            )
            for params in variants:
                ws.send(json.dumps({"method": "ms.remote.control", "params": params}))
                try:
                    reply = ws.recv(2.0)
                except (TimeoutError, TVError):
                    reply = ""
                if "error" not in reply.lower():
                    return True
            return True
        finally:
            ws.close()

    def key(self, name):
        ws = self._channel()
        try:
            ws.send(json.dumps({
                "method": "ms.remote.control",
                "params": {"Cmd": "Click", "DataOfCmd": name, "Type": "SendClick"},
            }))
            try:
                ws.recv(1.5)
            except (TimeoutError, TVError):
                pass
            return True
        finally:
            ws.close()

    def power(self):
        return self.key("KEY_POWER")


def wol(mac):
    """Broadcast Wake-on-LAN packets for the TV's MAC."""
    if not mac or ":" not in mac:
        return False
    pkt = bytes.fromhex("ff" * 6 + mac.replace(":", "") * 16)
    for _ in range(3):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(pkt, ("255.255.255.255", 9))
            s.close()
        except OSError:
            pass
    return True
