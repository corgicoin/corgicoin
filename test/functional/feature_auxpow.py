#!/usr/bin/env python3
"""Merged mining as real pools do it, and every way a proof can be wrong.

rpc_createauxblock.py covers the simplest proof end to end. This test adds:
- a multi-chain proof (our hash is one leaf of a larger merged-mining tree, in
  the slot GetExpectedAuxIndex() picks) under a parent block with several txs
- the legacy commitment form without the merged-mining magic
- one rejection per rule of CAuxPow::Check, plus insufficient parent work
- the Namecoin/Dogecoin-style getauxblock RPC that many pool stacks call
- stale work, the pre-fork guard, and decode errors
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error
from auxpow_builder import build_auxpow, expected_index

AUXPOW_FORK_REGTEST = 200
CHAIN_ID = 0xC6


class AuxPowTest(CorgiTestFramework):
    num_nodes = 2

    @staticmethod
    def log_size(node):
        with open(node.debug_log, "rb") as f:
            return len(f.read())

    @staticmethod
    def log_since(node, offset):
        with open(node.debug_log, "rb") as f:
            return f.read()[offset:].decode(errors="replace")

    def proof(self, work, **kw):
        return build_auxpow(work["hash"], int(work["bits"], 16), CHAIN_ID, **kw)

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)
        addr = n0.getnewaddress()

        self.log("merged mining is refused before the fork height")
        n0.generate(AUXPOW_FORK_REGTEST - 2)
        assert_raises_rpc_error(-1, "not active until block 200", n0.createauxblock, addr)
        assert_raises_rpc_error(-1, "not active until block 200", n0.getauxblock)
        n0.generate(2)                 # next block is the fork block
        self.sync_blocks()

        self.log("every broken rule is rejected, and the tip does not move")
        work = n0.createauxblock(addr)
        tip = n0.getbestblockhash()
        # (keyword arguments that break one rule, the CAuxPow::Check error it must produce)
        bad = {
            "parent carries our chain ID":     (dict(parent_version=(CHAIN_ID << 16) | 1), "parent has the same chain ID"),
            "parent is itself merged-mined":   (dict(parent_version=0x20000100), "parent block is itself AuxPoW"),
            "coinbase is not the first tx":    (dict(coinbase_index=1, parent_extra_txs=1), "parent coinbase is not the first tx"),
            "coinbase not under parent root":  (dict(bad_parent_merkle=True), "coinbase not in parent block merkle tree"),
            "a different hash is committed":   (dict(commit_hash_hex="11" * 32), "aux merkle root not found in parent coinbase"),
            "two merged-mining headers":       (dict(magic_count=2), "multiple merged-mining headers"),
            "bytes between magic and root":    (dict(gap_after_magic=b"\x00"), "merged-mining header not just before merkle root"),
            "no magic and root past byte 20":  (dict(magic=False, script_prefix=b"\x00" * 21), "aux merkle root too far into coinbase"),
            "tree size does not match branch": (dict(tree_height=1, size_field=4), "merkle tree size does not match branch length"),
            "our hash in the wrong slot":      (dict(tree_height=3, mm_nonce=7,
                                                     chain_index=(expected_index(7, CHAIN_ID, 3) + 1) % 8),
                                                "chain index does not match expected slot"),
        }
        for what, (kw, error) in bad.items():
            seen = self.log_size(n0)
            assert_equal(n0.submitauxblock(work["hash"], self.proof(work, **kw)), False, what)
            assert error in self.log_since(n0, seen), "%s: expected '%s' in debug.log" % (what, error)
        # CheckWork() drops a proof whose parent hash misses the target before
        # validating anything else, so there is no Check() error to look for
        assert_equal(n0.submitauxblock(work["hash"], self.proof(work, meet_target=False)), False)
        assert_equal(n0.getbestblockhash(), tip)

        self.log("malformed submissions are errors, not crashes")
        assert_raises_rpc_error(-22, "decode failed", n0.submitauxblock, work["hash"], "zz")
        assert_raises_rpc_error(-22, "decode failed", n0.submitauxblock, work["hash"], "00")
        assert_raises_rpc_error(-22, "trailing data", n0.submitauxblock, work["hash"], self.proof(work) + "00")
        assert_raises_rpc_error(-8, "64 hex", n0.submitauxblock, "1234", self.proof(work))
        assert_raises_rpc_error(-8, "unknown", n0.submitauxblock, "00" * 32, self.proof(work))

        self.log("after rejected proofs, a valid multi-chain proof for the same block is accepted")
        proof = self.proof(work, tree_height=3, mm_nonce=12345, parent_extra_txs=4)
        assert_equal(n0.submitauxblock(work["hash"], proof), True)
        assert_equal(n0.getbestblockhash(), work["hash"])
        self.sync_blocks()
        assert_equal(n1.getbestblockhash(), work["hash"])
        assert_raises_rpc_error(-8, "unknown", n0.submitauxblock, work["hash"], proof)

        self.log("the legacy commitment (no magic, root in the first 20 bytes) is accepted")
        work = n0.createauxblock(addr)
        assert_equal(n0.submitauxblock(work["hash"], self.proof(work, magic=False, script_prefix=b"\x03abc")), True)
        self.sync_blocks()

        self.log("getauxblock returns work in both target byte orders and pays this wallet")
        work = n0.getauxblock()
        for key in ("hash", "chainid", "previousblockhash", "coinbasevalue", "bits", "height", "target", "_target"):
            assert key in work, key
        assert_equal(work["chainid"], CHAIN_ID)
        assert_equal(work["target"], bytes.fromhex(work["_target"])[::-1].hex())
        assert_equal(work["height"], n0.getblockcount() + 1)
        assert_raises_rpc_error(-1, None, n0.getauxblock, work["hash"])   # one argument is a usage error
        assert_equal(n0.getauxblock(work["hash"], self.proof(work)), True)
        self.sync_blocks()
        coinbase = n0.getrawtransaction(n0.getblock(work["hash"])["tx"][0], 1)
        paid = coinbase["vout"][0]["scriptPubKey"]["addresses"][0]
        assert_equal(n0.validateaddress(paid)["ismine"], True)

        self.log("getauxblock moves to a fresh key once a block pays the last one")
        work = n0.getauxblock()
        assert_equal(n0.getauxblock(work["hash"], self.proof(work)), True)
        coinbase = n0.getrawtransaction(n0.getblock(work["hash"])["tx"][0], 1)
        assert coinbase["vout"][0]["scriptPubKey"]["addresses"][0] != paid

        self.log("work goes stale when the tip moves, then expires")
        work = n0.createauxblock(addr)
        n0.generate(1)
        assert_equal(n0.submitauxblock(work["hash"], self.proof(work)), False)    # stale
        n0.createauxblock(addr)                                                    # flushes old work
        assert_raises_rpc_error(-8, "unknown", n0.submitauxblock, work["hash"], self.proof(work))
        self.sync_blocks()


if __name__ == "__main__":
    AuxPowTest().main()
