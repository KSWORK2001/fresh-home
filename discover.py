#!/usr/bin/env python3
"""Discover a Samsung TV on the local network.

Strategy:
  1. SSDP M-SEARCH multicast (TVs answer with their UPnP/DIAL description URL)
  2. Fallback: sweep the subnet for open Samsung control ports (8002/8001/9197)

Saves what it finds to config.json next to this file. Zero dependencies.
"""

import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

SSDP = ("239.255.255.250", 1900)
TARGETS = [
    "urn:dial-multiscreen-org:service:dial:1",
    "urn:samsung.com:device:MainTVAgentServer:1",
    "urn:samsung.com:service:MainTVAgentServer:1",
    "upnp:rootdevice",
    "ssdp:all",
]
SAMSUNG_PORTS = (8002, 8001, 9197)


# ------------------------------------------------------------- low level ----

def _local_subnet():
    """(ip, prefix_len) of the interface that owns the default route."""
    iface = "en0"
    try:
        out = subprocess.run(["route", "-n", "get", "default"],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"interface:\s*(\S+)", out)
        if m:
            iface = m.group(1)
    except Exception:
        pass
    try:
        out = subprocess.run(["ifconfig", iface], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-fA-F]+)", out)
        if not m:
            return None
        return m.group(1), bin(int(m.group(2), 16)).count("1")
    except Exception:
        return None


def ssdp_scan(timeout=8):
    """Multicast M-SEARCH; returns {description_url: {ip, server, st, usn}}."""
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 0))
    sock.settimeout(0.4)
    start = time.time()
    next_burst = -1.0
    while time.time() - start < timeout:
        now = time.time() - start
        if now >= next_burst:
            for st in TARGETS:
                msg = "\r\n".join([
                    "M-SEARCH * HTTP/1.1",
                    "HOST: 239.255.255.250:1900",
                    'MAN: "ssdp:discover"',
                    "MX: 2",
                    "ST: " + st,
                    "", "",
                ]).encode()
                try:
                    sock.sendto(msg, SSDP)
                except OSError:
                    pass
            next_burst = now + 1.5
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        headers = {}
        for line in data.decode("utf-8", "replace").split("\r\n\r\n", 1)[0].split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        loc = headers.get("location")
        if not loc:
            continue
        rec = found.setdefault(loc, {"ip": addr[0], "server": headers.get("server", ""),
                                     "st": headers.get("st", ""), "usn": headers.get("usn", "")})
        if headers.get("st"):
            rec["st"] = headers["st"]
    sock.close()
    return found


def fetch_description(url, timeout=3):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _tag(xml, tag):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def probe(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def sweep_scan(subnet):
    """Probe every host on the subnet for Samsung control ports."""
    ip, prefix = subnet
    base = ip.rsplit(".", 1)[0]
    hosts = [ip] if prefix >= 30 else [f"{base}.{i}" for i in range(1, 255)]

    def probe_all(h):
        return h, [p for p in SAMSUNG_PORTS if probe(h, p, 0.7)]

    with ThreadPoolExecutor(max_workers=128) as ex:
        results = list(ex.map(probe_all, hosts))
    return {h: ports for h, ports in results if ports}


def get_mac(ip):
    try:
        subprocess.run(["ping", "-c", "1", "-W", "200", "-t", "1", ip], capture_output=True)
        out = subprocess.run(["arp", "-n", ip], capture_output=True, text=True, timeout=5).stdout
        # macOS prints single-digit octets ("80:d:3f:…"); normalize to full form
        m = re.search(r"at ([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})", out)
        if not m:
            return None
        return ":".join(o.zfill(2) for o in m.group(1).split(":")).lower()
    except Exception:
        return None


# -------------------------------------------------------------- top level ---

def _is_samsung(rec):
    hay = " ".join(str(v) for v in rec.values()).lower()
    return "samsung" in hay or "tizen" in hay


def find_tv(verbose=True):
    """Return the best Samsung-TV record found, or None."""
    if verbose:
        print("Scanning the network via SSDP (up to ~8s)…")
    recs = []
    for loc, rec in ssdp_scan().items():
        xml = fetch_description(loc)
        rec.update({
            "location": loc,
            "friendly": _tag(xml, "friendlyName"),
            "model": _tag(xml, "modelName"),
            "manufacturer": _tag(xml, "manufacturer"),
            "device_type": _tag(xml, "deviceType"),
        })
        recs.append(rec)
        if verbose:
            print(f"  · {rec['ip']:15} {rec['friendly'] or rec['server'] or 'device':40} {rec['model']}")

    tvs = [r for r in recs if _is_samsung(r)]
    if not tvs:
        if verbose:
            print("Nothing Samsung via SSDP — sweeping the subnet for control ports…")
        subnet = _local_subnet()
        if subnet:
            for ip, ports in sweep_scan(subnet).items():
                tvs.append({"ip": ip, "ports": ports, "friendly": "", "model": ""})

    if not tvs:
        return None

    # Prefer the M70HB if multiple Samsungs are around
    tvs.sort(key=lambda r: 0 if "m70" in f"{r.get('model', '')}{r.get('friendly', '')}".lower() else 1)
    tv = tvs[0]
    tv["ports"] = tv.get("ports") or [p for p in SAMSUNG_PORTS if probe(tv["ip"], p, 1.0)]
    tv["mac"] = get_mac(tv["ip"])
    return tv


def main():
    tv = find_tv()
    if not tv:
        print("\nNo Samsung TV found. Make sure it's powered on and on this Wi-Fi, then retry.")
        return 1
    print("\n✓ Samsung TV found")
    for key, label in (("friendly", "Name"), ("model", "Model"), ("ip", "IP"),
                       ("mac", "MAC"), ("ports", "Ports")):
        if tv.get(key):
            print(f"    {label:6} {tv[key]}")
    import samsung
    samsung.save_config(ip=tv["ip"], mac=tv.get("mac"), model=tv.get("model"),
                        friendly=tv.get("friendly"), ports=tv.get("ports"))
    print("\nSaved to config.json. Next step:  python3 tv.py pair")
    return 0


if __name__ == "__main__":
    sys.exit(main())
