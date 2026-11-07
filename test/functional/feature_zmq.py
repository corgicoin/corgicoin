#!/usr/bin/env python3
"""ZeroMQ notifications: hashblock, rawblock, hashtx and rawtx, with their sequence numbers."""
import socket

from test_framework import CorgiTestFramework, assert_equal

try:
    import zmq
except ImportError:      # pyzmq is optional for running the suite
    zmq = None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT_BLOCKS, PORT_TXS = free_port(), free_port()


class ZMQTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-zmqpubhashblock=tcp://127.0.0.1:%d" % PORT_BLOCKS, "-zmqpubrawblock=tcp://127.0.0.1:%d" % PORT_BLOCKS,
                   "-zmqpubhashtx=tcp://127.0.0.1:%d" % PORT_TXS, "-zmqpubrawtx=tcp://127.0.0.1:%d" % PORT_TXS]]

    def setup_nodes(self):
        if zmq is None:
            self.skip_test("pyzmq is not installed")
        try:
            super().setup_nodes()
        except Exception as e:      # a build without libzmq refuses the options and exits
            if "exited during startup" in str(e):
                self.skip_test("this corgicoind was built without ZeroMQ")
            raise

    @staticmethod
    def drain(sock, last, wait_ms=300):
        """Read everything pending; record the last sequence number seen for each topic. Returns the messages."""
        out = []
        while sock.poll(wait_ms):
            topic, body, seq = sock.recv_multipart()
            topic, seq = topic.decode(), int.from_bytes(seq, "little")
            last[topic] = seq
            out.append((topic, body, seq))
        return out

    def run_test(self):
        node = self.nodes[0]
        ctx = zmq.Context()
        blocks, txs = ctx.socket(zmq.SUB), ctx.socket(zmq.SUB)
        for sock, port in ((blocks, PORT_BLOCKS), (txs, PORT_TXS)):
            sock.setsockopt_string(zmq.SUBSCRIBE, "")
            sock.connect("tcp://127.0.0.1:%d" % port)
        last_block, last_tx = {}, {}

        self.log("a PUB socket drops what it sends before a subscriber joins: mine until the first message arrives")
        node.generate(51)
        for _ in range(40):
            node.generate(1)
            if blocks.poll(500) and txs.poll(500):
                break
        else:
            raise AssertionError("no ZMQ message arrived")
        self.drain(blocks, last_block)
        self.drain(txs, last_tx)

        self.log("a new block: hashblock (in the printed byte order) then rawblock, sequence numbers one up")
        node.generate(1)
        got = {t: (b, s) for t, b, s in self.drain(blocks, {}, 2000)}
        best = node.getbestblockhash()
        assert_equal(sorted(got), ["hashblock", "rawblock"])
        assert_equal(got["hashblock"][0].hex(), best)
        assert_equal(got["hashblock"][1], last_block["hashblock"] + 1)
        assert_equal(got["rawblock"][1], last_block["rawblock"] + 1)
        assert_equal(got["rawblock"][0][:80].hex(), node.getblockheader(best, False)[:160])
        assert got["rawblock"][0].endswith(bytes.fromhex(node.getrawtransaction(node.getblock(best)["tx"][-1])))
        self.drain(txs, last_tx)    # the block's coinbase

        self.log("a transaction is announced when it enters the pool: hashtx then rawtx")
        txid = node.sendtoaddress(node.getnewaddress(), 5)
        seen = {t: (b, s) for t, b, s in self.drain(txs, {}, 2000)}
        assert_equal(seen["hashtx"][0].hex(), txid)
        assert_equal(seen["rawtx"][0].hex(), node.getrawtransaction(txid))
        assert_equal(seen["hashtx"][1], last_tx["hashtx"] + 1)
        assert_equal(seen["rawtx"][1], last_tx["rawtx"] + 1)
        last_tx = {"hashtx": seen["hashtx"][1], "rawtx": seen["rawtx"][1]}

        self.log("and again when a block carries it, together with that block's coinbase")
        node.generate(1)
        mined = self.drain(txs, {}, 2000)
        hashes = [b.hex() for t, b, _s in mined if t == "hashtx"]
        assert txid in hashes, "the mined transaction was not announced"
        assert_equal(len(hashes), 2)
        seqs = [s for t, _b, s in mined if t == "hashtx"]
        assert_equal(seqs, [last_tx["hashtx"] + 1, last_tx["hashtx"] + 2])

        ctx.destroy(linger=0)


if __name__ == "__main__":
    ZMQTest().main()
