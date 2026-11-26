#!/usr/bin/env python3
"""A version message that is cut short does not pass for a handshake.

The version handler read the peer's protocol number into the connection before it read the rest. A message of four bytes threw after that,
the exception was caught further out, and the peer was left with a protocol number and no handshake: the "version first" check passed,
the check on the number (too old) was skipped, and the peer was answered (a ping got its pong) without a version or a verack.
Now such a peer is disconnected and nothing it sends afterwards is answered. An ordinary handshake still works.
"""
import socket
import struct
import time

from mininode import P2PConnection, REGTEST_MAGIC, sha256d
from test_framework import CorgiTestFramework, assert_equal, wait_until


def frame(command, payload=b""):
    return REGTEST_MAGIC + command.encode().ljust(12, b"\x00") + struct.pack("<I", len(payload)) + sha256d(payload)[:4] + payload


def talk(port, messages, seconds=4):
    """Send the messages one after the other; return the commands the node sent and whether it closed the connection."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.settimeout(0.5)
    got, closed, buf = [], False, b""
    try:
        for m in messages:
            try:
                s.sendall(m)
            except OSError:
                closed = True
                break
        deadline = time.time() + seconds
        while time.time() < deadline and not closed:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                closed = True
                break
            if not chunk:
                closed = True
                break
            buf += chunk
        while len(buf) >= 24:
            n = struct.unpack("<I", buf[16:20])[0]
            if len(buf) < 24 + n:
                break
            got.append(buf[4:16].rstrip(b"\x00").decode())
            buf = buf[24 + n:]
    finally:
        s.close()
    return got, closed


class TruncatedVersionTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(2)
        ping = frame("ping", struct.pack("<Q", 7))

        for label, number in (("a current protocol number", 70014), ("a number below the minimum", 1)):
            self.log("a 4-byte version message with %s, then a ping" % label)
            got, closed = talk(node.p2p_port, [frame("version", struct.pack("<i", number)), ping])
            assert "pong" not in got, "the ping of a peer with no handshake was answered: %s" % got
            assert "verack" not in got, got
            assert closed, "the peer was not disconnected (the node sent %s)" % got

        self.log("a version message cut short after the services field, then a ping")
        got, closed = talk(node.p2p_port, [frame("version", struct.pack("<iQ", 70014, 1)), ping])
        assert "pong" not in got and closed, (got, closed)

        self.log("an ordinary peer still completes the handshake and is answered")
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")
        peer.send("ping", struct.pack("<Q", 9))
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="pong")
        peer.close()
        assert node.process.poll() is None
        assert_equal(node.getblockcount(), 2)


if __name__ == "__main__":
    TruncatedVersionTest().main()
