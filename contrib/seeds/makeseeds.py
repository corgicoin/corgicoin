#!/usr/bin/env python3
"""Check candidate seed nodes and print the lines to paste into src/net.cpp.

    contrib/seeds/makeseeds.py candidates.txt [--port 62556] [--magic c0c0c0c0] [--max-behind 100] [--per-group 2]

candidates.txt holds one IPv4 address per line (blank lines and lines starting with # are ignored). Each is probed with a
real version handshake. A node is kept if it answers within the timeout, calls itself CorgiCoin (not another chain's node
that shares the magic bytes), speaks protocol 70001 or newer, offers the network service, and is not far behind the best
height seen among the candidates (a stuck node is a bad seed). No more than --per-group (default 2) are kept from one /16,
so the list does not rest on one hosting provider.

Output: the pnSeed[] entries (network byte order, as the array holds them), and the same list as plain addresses for a DNS
seeder. Run it from at least two places before a release; a node that is down from one of them is not a good seed.
"""
import argparse
import hashlib
import random
import socket
import struct
import sys
import time

PROTOCOL_VERSION = 70001
NODE_NETWORK = 1
FOREIGN = ("shibetoshi", "dogecoin")


def sha256d(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def varstr(b):
    return bytes([len(b)]) + b


def netaddr(host, port):
    return struct.pack("<Q", NODE_NETWORK) + b"\x00" * 10 + b"\xff\xff" + socket.inet_aton(host) + struct.pack(">H", port)


def frame(magic, command, payload=b""):
    return magic + command.encode().ljust(12, b"\x00") + struct.pack("<I", len(payload)) + sha256d(payload)[:4] + payload


def read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def read_varstr(b, i):
    n = b[i]
    return b[i + 1:i + 1 + n], i + 1 + n


def probe(host, port, magic, timeout):
    """Handshake with one node. Returns a dict (version, services, subver, height), or raises."""
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        payload = (struct.pack("<iQq", PROTOCOL_VERSION, NODE_NETWORK, int(time.time())) + netaddr(host, port) + netaddr("0.0.0.0", 0)
                   + struct.pack("<Q", random.getrandbits(64)) + varstr(b"/seedprobe:0.1/") + struct.pack("<i", 0))
        sock.sendall(frame(magic, "version", payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            header = read_exact(sock, 24)
            if header[:4] != magic:
                raise ConnectionError("not this network (magic %s)" % header[:4].hex())
            command = header[4:16].rstrip(b"\x00").decode(errors="replace")
            length = struct.unpack("<I", header[16:20])[0]
            if length > 1 << 20:
                raise ConnectionError("message too large")
            body = read_exact(sock, length)
            if command == "version":
                version, services = struct.unpack_from("<iQ", body, 0)
                i = 4 + 8 + 8 + 26 + 26 + 8        # version, services, time, addr_recv, addr_from, nonce
                subver, i = read_varstr(body, i)
                height = struct.unpack_from("<i", body, i)[0]
                return {"version": version, "services": services, "subver": subver.decode(errors="replace"), "height": height}
        raise TimeoutError("no version message")
    finally:
        sock.close()


def group(host):
    a, b = host.split(".")[:2]
    return a + "." + b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--port", type=int, default=62556)
    ap.add_argument("--magic", default="c0c0c0c0", help="message start bytes, hex (regtest: fac0b6da)")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--max-behind", type=int, default=100, help="drop nodes this many blocks behind the best seen")
    ap.add_argument("--per-group", type=int, default=2, help="most nodes kept from one /16")
    args = ap.parse_args()
    magic = bytes.fromhex(args.magic)

    hosts = []
    for line in open(args.candidates):
        line = line.strip()
        if line and not line.startswith("#"):
            hosts.append(line)

    good = []
    for host in hosts:
        try:
            info = probe(host, args.port, magic, args.timeout)
        except (OSError, ConnectionError, TimeoutError, struct.error, IndexError) as e:
            print("# %s: skipped (%s)" % (host, e), file=sys.stderr)
            continue
        low = info["subver"].lower()
        if any(f in low for f in FOREIGN) or "corgicoin" not in low:
            print("# %s: skipped (user agent %r is not CorgiCoin)" % (host, info["subver"]), file=sys.stderr)
            continue
        if info["version"] < PROTOCOL_VERSION or not info["services"] & NODE_NETWORK:
            print("# %s: skipped (protocol %d, services %d)" % (host, info["version"], info["services"]), file=sys.stderr)
            continue
        good.append((host, info))

    if not good:
        print("# no usable nodes", file=sys.stderr)
        return 1
    best = max(info["height"] for _, info in good)
    kept, per_group = [], {}
    for host, info in good:
        if info["height"] < best - args.max_behind:
            print("# %s: skipped (height %d, best %d)" % (host, info["height"], best), file=sys.stderr)
            continue
        if per_group.get(group(host), 0) >= args.per_group:
            print("# %s: skipped (already %d from %s.0.0)" % (host, args.per_group, group(host)), file=sys.stderr)
            continue
        per_group[group(host)] = per_group.get(group(host), 0) + 1
        kept.append(host)

    print("// pnSeed[] entries (network byte order, as net.cpp holds them):")
    for host in kept:
        print("    0x%08x,  // %s" % (struct.unpack("<I", socket.inet_aton(host))[0], host))
    print("// plain list, for a DNS seeder:")
    for host in kept:
        print(host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
