#!/usr/bin/env python3
"""Every P2P command, sent with payloads that are wrong in size, count and content: a refusal or a dropped connection is the right
answer, a dead node is not.

For each command the node understands (and one it does not) the test starts from a payload that is well formed or nearly so
(a real block, a real transaction, a locator, inventory) and from nothing, and sends variants: random bytes, a cut-off copy,
flipped bits, a huge element count in front, a copy repeated. Fixed seed. The node runs with -banscore=1000000 so that it keeps
reading from the peer that misbehaves; a new connection is made every few messages. Afterwards the node must be running, hold the
same chain, and answer a fresh peer's ping. Under the sanitizer build any memory error in a handler fails the test as well.
"""
import random
import struct
import time

from mininode import P2PConnection, REGTEST_MAGIC, sha256d, ser_varstr, ser_addr
from test_framework import CorgiTestFramework, assert_equal, wait_until

COMMANDS = ["version", "verack", "addr", "inv", "getdata", "getblocks", "getheaders", "headers", "tx", "block", "getaddr",
            "checkorder", "reply", "ping", "pong", "alert", "feefilter", "mempool", "notfound", "reject", "unknowncmd"]
HUGE_COUNTS = [b"\xfd\xff\xff", b"\xfe\xff\xff\xff\x7f", b"\xfe\x00\x00\x00\x80", b"\xff" + b"\xff" * 8, b"\xff" + b"\xff" * 7 + b"\x7f",
               b"\xfd\x51\xc3", b"\xfe\x40\x42\x0f\x00"]
ROUNDS = 150
PER_ROUND = 25


class P2PMessageFuzz(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-banscore=1000000"]]

    def seeds(self, node):
        """Payloads that the node's own handlers parse as they are: variants of these reach deeper than random bytes."""
        tip = node.getbestblockhash()
        block = bytes.fromhex(node.getblock(tip, False))
        old = bytes.fromhex(node.getblock(node.getblockhash(1), False))
        txid = node.sendtoaddress(node.getnewaddress(), 1)
        tx = bytes.fromhex(node.getrawtransaction(txid))
        h = bytes.fromhex(tip)[::-1]
        locator = struct.pack("<i", 70014) + b"\x02" + h + bytes.fromhex(node.getblockhash(0))[::-1] + b"\x00" * 32
        inv = b"\x03" + struct.pack("<I", 2) + h + struct.pack("<I", 1) + bytes.fromhex(txid)[::-1] + struct.pack("<I", 2) + b"\x11" * 32
        header = block[:80]
        version = (struct.pack("<iQq", 70014, 1, int(time.time())) + ser_addr() + ser_addr() + struct.pack("<Q", 7)
                   + ser_varstr(b"/fuzz/") + struct.pack("<i", 3))
        addr = b"\x02" + (struct.pack("<I", int(time.time())) + ser_addr("8.8.8.8", 62556)) * 2
        return {
            "version": [version],
            "addr": [addr],
            "inv": [inv],
            "getdata": [inv],
            "getblocks": [locator],
            "getheaders": [locator],
            "headers": [b"\x01" + header + b"\x00", b"\x02" + (header + b"\x00") * 2],
            "tx": [tx],
            "block": [block, old],
            "ping": [struct.pack("<Q", 5)],
            "pong": [struct.pack("<Q", 5)],
            "feefilter": [struct.pack("<q", 1000)],
            "checkorder": [b"\x01" * 32 + tx],
            "reply": [b"\x01" * 32 + b"\x00" * 8],
            "alert": [b"\x00" * 10, b"\x40" + b"\x00" * 64],
            "reject": [ser_varstr(b"tx") + b"\x10" + ser_varstr(b"bad") + b"\x00" * 32],
        }

    def variant(self, rnd, seed):
        kind = rnd.randrange(8)
        if kind == 0 or not seed:
            return bytes(rnd.getrandbits(8) for _ in range(rnd.choice([0, 1, 2, 4, 8, 33, 80, 200, 1000])))
        if kind == 1:
            return seed[:rnd.randrange(len(seed) + 1)]
        if kind == 2:
            b = bytearray(seed)
            for _ in range(rnd.randrange(1, 6)):
                b[rnd.randrange(len(b))] ^= 1 << rnd.randrange(8)
            return bytes(b)
        if kind == 3:
            return rnd.choice(HUGE_COUNTS) + seed[1:]
        if kind == 4:
            return rnd.choice(HUGE_COUNTS) + seed
        if kind == 5:
            return seed * rnd.choice([2, 3, 10])
        if kind == 6:
            b = bytearray(seed)
            i = rnd.randrange(len(b))
            b[i:i + rnd.randrange(1, 9)] = bytes(rnd.choice([0, 0xff, 0x7f, 0x80]) for _ in range(rnd.randrange(1, 9)))
            return bytes(b)
        return seed + bytes(rnd.getrandbits(8) for _ in range(rnd.randrange(1, 100)))

    def alive(self, node, height):
        assert node.process.poll() is None, "node exited with status %s" % node.process.returncode
        assert_equal(node.getblockcount(), height)

    def run_test(self):
        node = self.nodes[0]
        node.generate(110)
        height = node.getblockcount()
        seeds = self.seeds(node)
        rnd = random.Random(20261124)
        sent = 0

        self.log("%d connections, %d messages each, over %d commands" % (ROUNDS, PER_ROUND, len(COMMANDS)))
        for r in range(ROUNDS):
            peer = P2PConnection(node.p2p_port, start_height=rnd.choice([0, height, height + 5, 2 ** 31 - 1]))
            wait_until(lambda: peer.got_verack, timeout=30, what="verack")
            for _ in range(PER_ROUND):
                command = rnd.choice(COMMANDS)
                payload = self.variant(rnd, rnd.choice(seeds.get(command, [b""])))
                try:
                    peer.send(command, payload)
                    sent += 1
                except OSError:
                    break           # the node dropped this peer: a new one for the next round
            if r % 10 == 9:
                self.alive(node, height)
            peer.close()

        self.log("raw frames: a length that does not match, a bad magic, a command with no terminator")
        for frame in (REGTEST_MAGIC + b"block".ljust(12, b"\x00") + struct.pack("<I", 0x7fffffff) + b"\x00" * 4,
                      REGTEST_MAGIC + b"tx".ljust(12, b"\x00") + struct.pack("<I", 10) + sha256d(b"x")[:4] + b"x",
                      b"\x00\x01\x02\x03" + b"ping".ljust(12, b"\x00") + struct.pack("<I", 0) + sha256d(b"")[:4],
                      REGTEST_MAGIC + b"A" * 12 + struct.pack("<I", 0) + sha256d(b"")[:4],
                      REGTEST_MAGIC + b"\xff" * 12 + struct.pack("<I", 0) + sha256d(b"")[:4]):
            peer = P2PConnection(node.p2p_port)
            wait_until(lambda: peer.got_verack, timeout=30, what="verack")
            try:
                peer.sock.sendall(frame)
            except OSError:
                pass
            time.sleep(0.2)
            peer.close()
        self.alive(node, height)

        self.log("a fresh peer is still served after %d messages" % sent)
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, timeout=30, what="verack")
        peer.send("ping", struct.pack("<Q", 99))
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, timeout=30, what="pong")
        peer.close()
        self.alive(node, height)


if __name__ == "__main__":
    P2PMessageFuzz().main()
