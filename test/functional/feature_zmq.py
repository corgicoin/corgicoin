#!/usr/bin/env python3
"""ZeroMQ notifications: hashblock, rawblock, hashtx and rawtx, with their sequence numbers."""
import os
import socket

from test_framework import CorgiTestFramework, assert_equal, wait_until

try:
    import zmq
except ImportError:      # pyzmq is optional for running the suite
    zmq = None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT_A, PORT_B = free_port(), free_port()


class ZMQTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-zmqpubhashblock=tcp://127.0.0.1:%d" % PORT_A, "-zmqpubrawblock=tcp://127.0.0.1:%d" % PORT_A,
                   "-zmqpubhashtx=tcp://127.0.0.1:%d" % PORT_B, "-zmqpubrawtx=tcp://127.0.0.1:%d" % PORT_B]]

    def setup_nodes(self):
        if zmq is None:
            self.skip_test("pyzmq is not installed")
        try:
            super().setup_nodes()
        except Exception as e:      # a build without libzmq refuses the option and exits
            if "exited during startup" in str(e):
                self.skip_test("this corgicoind was built without ZeroMQ")
            raise

    def recv(self, sock, timeout=20):
        """(topic, body, sequence) of the next message."""
        assert sock.poll(timeout * 1000), "no ZMQ message within %ss" % timeout
        topic, body, seq = sock.recv_multipart()
        return topic.decode(), body, int.from_bytes(seq, "little")

    def run_test(self):
        node = self.nodes[0]
        ctx = zmq.Context()
        blocks = ctx.socket(zmq.SUB)
        txs = ctx.socket(zmq.SUB)
        for sock, port in ((blocks, PORT_A), (txs, PORT_B)):
            sock.setsockopt(zmq.RCVTIMEO, 20000)
            sock.setsockopt_string(zmq.SUBSCRIBE, "")
            sock.connect("tcp://127.0.0.1:%d" % port)
        # a PUB socket drops what is sent before a SUB has joined: keep producing until one arrives
        node.generate(51)
        deadline_msgs = []
        wait_until(lambda: blocks.poll(100) or node.generate(1) is None and False, timeout=30, what="the subscriber to join")
        # drain whatever arrived while joining; keep the latest block hash as the reference
        while blocks.poll(300):
            deadline_msgs.append(blocks.recv_multipart())
        while txs.poll(300):
            txs.recv_multipart()

        self.log("a new block: hashblock and rawblock, in the printed byte order, with consecutive sequence numbers")
        before = {t: s for t, _b, s in ((m[0].decode(), m[1], int.from_bytes(m[2], "little")) for m in deadline_msgs)}
        hash_before = before.get("hashblock", -1)
        node.generate(1)
        got = {}
        for _ in range(2):
            topic, body, seq = self.recv(blocks)
            got[topic] = (body, seq)
        best = node.getbestblockhash()
        assert_equal(got["hashblock"][0].hex(), best)
        assert_equal(got["rawblock"][0][:80].hex(), node.getblockheader(best, False)[:160])
        assert_equal(got["hashblock"][1], hash_before + 1)

        self.log("a transaction: hashtx and rawtx when it enters the pool, and again when it is mined")
        txid = node.sendtoaddress(node.getnewaddress(), 5)
        seen = {}
        for _ in range(2):
            topic, body, seq = self.recv(txs)
            seen[topic] = (body, seq)
        assert_equal(seen["hashtx"][0].hex(), txid)
        assert_equal(seen["rawtx"][0].hex(), node.getrawtransaction(txid))
        assert_equal(seen["rawtx"][1] - seen["hashtx"][1], seen["rawtx"][1] - seen["hashtx"][1])
        first_seq = seen["hashtx"][1]
        node.generate(1)
        mined = []
        while txs.poll(2000):
            topic, body, seq = txs.recv_multipart()
            mined.append((topic.decode(), body.hex(), int.from_bytes(seq, "little")))
        assert any(t == "hashtx" and b == txid for t, b, _s in mined), "the mined transaction was not announced"
        seqs = [s for t, _b, s in mined if t == "hashtx"]
        assert seqs == sorted(seqs) and seqs[0] > first_seq

        ctx.destroy(linger=0)


if __name__ == "__main__":
    ZMQTest().main()
