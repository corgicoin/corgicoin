#!/usr/bin/env python3
"""A failed sethdseed must leave the wallet on its old seed, in memory and on disk.

The seed id, chain index, phrase and minimum version are written in one database transaction, and the in-memory
state is put back if any write fails. Before, the writes were separate and unchecked, so a failure left the node
running on a seed that was not the one in wallet.dat. The fault is injected with the regtest-only
-testwalletwritefault=hdseed.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

OLD = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
NEW = "legal winner thank year wave sausage worth useful legal winner thank yellow"


class WalletHDSeedAtomicTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.sethdseed(OLD)
        old_id = node.getwalletinfo()["hdseedid"]
        addr = node.getnewaddress()

        self.log("restart with the write fault: sethdseed fails and nothing changes")
        node.stop()
        node.start(["-testwalletwritefault=hdseed"])
        assert_raises_rpc_error(-4, None, node.sethdseed, NEW)
        assert_equal(node.getwalletinfo()["hdseedid"], old_id)
        assert_equal(node.gethdseed(True)["mnemonic"], OLD)
        node.dumpprivkey(addr)

        self.log("the file still holds the old seed after a restart")
        node.stop()
        node.start()
        assert_equal(node.getwalletinfo()["hdseedid"], old_id)
        assert_equal(node.gethdseed(True)["mnemonic"], OLD)

        self.log("without the fault the change goes through")
        node.sethdseed(NEW)
        new_id = node.getwalletinfo()["hdseedid"]
        assert new_id != old_id
        node.stop()
        node.start()
        assert_equal(node.getwalletinfo()["hdseedid"], new_id)
        assert_equal(node.gethdseed(True)["mnemonic"], NEW)


if __name__ == "__main__":
    WalletHDSeedAtomicTest().main()
