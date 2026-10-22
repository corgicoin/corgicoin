"""A bare-bones P2P peer for functional tests (regtest). Standard library only.

Speaks just enough of the wire protocol to complete the version handshake
and then lets a test decide how to behave, e.g. ignore pings to exercise the
node's ping timeout. Messages are framed as: magic(4) command(12)
length(4, LE) checksum(4, first 4 bytes of sha256d(payload)) payload.
"""
import hashlib
import random
import socket
import struct
import threading
import time

REGTEST_MAGIC = bytes.fromhex("fac0b6da")
PROTOCOL_VERSION = 70001
NODE_NETWORK = 1


def sha256d(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def ser_varstr(s):
    b = s.encode()
    assert len(b) < 0xfd
    return bytes([len(b)]) + b


def ser_addr(host="127.0.0.1", port=0):
    # version-message CAddress: services(8) + IPv4-mapped IPv6(16) + port(2, BE)
    ip = b"\x00" * 10 + b"\xff\xff" + socket.inet_aton(host)
    return struct.pack("<Q", NODE_NETWORK) + ip + struct.pack(">H", port)


class P2PConnection:
    """One outbound connection to a node's P2P port.

    answer_pings=False makes the peer stay silent on "ping", which is what a
    wedged peer looks like to the node.
    """

    def __init__(self, port, answer_pings=True, start_height=0):
        self.answer_pings = answer_pings
        self.got_verack = False
        self.pings_received = 0
        self.closed = False
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.sock.settimeout(None)
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        payload = (struct.pack("<iQq", PROTOCOL_VERSION, NODE_NETWORK, int(time.time()))
                   + ser_addr(port=port) + ser_addr()
                   + struct.pack("<Q", random.getrandbits(64))
                   + ser_varstr("/corgi-mininode:0.1/")
                   + struct.pack("<i", start_height))
        self.send("version", payload)

    def send(self, command, payload=b""):
        header = (REGTEST_MAGIC + command.encode().ljust(12, b"\x00")
                  + struct.pack("<I", len(payload)) + sha256d(payload)[:4])
        with self._lock:
            self.sock.sendall(header + payload)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def _read_loop(self):
        try:
            while True:
                header = self._recv_exact(24)
                if header[:4] != REGTEST_MAGIC:
                    raise ConnectionError("bad magic")
                command = header[4:16].rstrip(b"\x00").decode()
                length = struct.unpack("<I", header[16:20])[0]
                payload = self._recv_exact(length)
                if sha256d(payload)[:4] != header[20:24]:
                    raise ConnectionError("bad checksum")
                self._on_message(command, payload)
        except (OSError, ConnectionError):
            pass
        finally:
            self.closed = True

    def _on_message(self, command, payload):
        if command == "version":
            self.send("verack")
        elif command == "verack":
            self.got_verack = True
        elif command == "ping":
            self.pings_received += 1
            if self.answer_pings:
                self.send("pong", payload)

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
