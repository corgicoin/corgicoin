#!/usr/bin/env python3
"""getblock <hash> [verbose]: JSON by default, the serialized block as hex when verbose is false/0.

The hex form is the network serialization: 80-byte header, the AuxPoW proof when the
AuxPoW version bit is set, then the transactions. Pool software that asks for the raw
block of a merged-mined block needs the proof to be there.
"""
from mininode import sha256d
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error
from auxpow_builder import build_auxpow

AUXPOW_FORK_REGTEST = 200
CHAIN_ID = 0xC6


def read_compact_size(b, pos):
    n = b[pos]
    if n < 0xfd:
        return n, pos + 1
    if n == 0xfd:
        return int.from_bytes(b[pos + 1:pos + 3], "little"), pos + 3
    if n == 0xfe:
        return int.from_bytes(b[pos + 1:pos + 5], "little"), pos + 5
    return int.from_bytes(b[pos + 1:pos + 9], "little"), pos + 9


class GetBlockVerboseTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        addr = node.getnewaddress()

        self.log("a plain block: JSON by default, JSON for true/1/2, hex for false/0")
        h = node.generate(1)[0]
        as_json = node.getblock(h)
        assert_equal(as_json["hash"], h)
        for verbose in (True, 1, 2):
            assert_equal(node.getblock(h, verbose), as_json)
        for verbose in (False, 0):
            raw = bytes.fromhex(node.getblock(h, verbose))
            assert_equal(sha256d(raw[:80])[::-1].hex(), h)
            ntx, pos = read_compact_size(raw, 80)
            assert_equal(ntx, len(as_json["tx"]))
        assert_equal(len(bytes.fromhex(node.getblock(h, False))), as_json["size"])

        self.log("errors: unknown block, wrong type")
        assert_raises_rpc_error(-5, "Block not found", node.getblock, "00" * 32, False)
        assert_raises_rpc_error(-8, "boolean or an integer", node.getblock, h, "yes")

        self.log("a merged-mined block: the hex carries the AuxPoW proof between header and transactions")
        node.generate(AUXPOW_FORK_REGTEST)
        work = node.createauxblock(addr)
        proof = build_auxpow(work["hash"], int(work["bits"], 16), CHAIN_ID)
        assert_equal(node.submitauxblock(work["hash"], proof), True)
        aux_hash = node.getbestblockhash()
        assert_equal(aux_hash, work["hash"])
        aux_json = node.getblock(aux_hash)
        raw = bytes.fromhex(node.getblock(aux_hash, False))
        assert_equal(sha256d(raw[:80])[::-1].hex(), aux_hash)
        assert_equal(len(raw), aux_json["size"])
        # the proof is the bytes the submitter sent, in between the header and the transactions
        assert_equal(raw[80:80 + len(bytes.fromhex(proof))], bytes.fromhex(proof))
        ntx, _ = read_compact_size(raw, 80 + len(bytes.fromhex(proof)))
        assert_equal(ntx, len(aux_json["tx"]))


if __name__ == "__main__":
    GetBlockVerboseTest().main()
