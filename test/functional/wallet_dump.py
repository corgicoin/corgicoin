#!/usr/bin/env python3
"""dumpwallet / importwallet round-trip, importprivkey, plus getrawchangeaddress."""
import hashlib
import os

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WalletDumpTest(CorgiTestFramework):
    num_nodes = 3

    def run_test(self):
        n0, n1, n2 = self.nodes
        self.connect_nodes(0, 1)
        self.connect_nodes(0, 2)

        self.log("getrawchangeaddress is ours but not in the address book")
        change = n1.getrawchangeaddress()
        info = n1.validateaddress(change)
        assert_equal(info["ismine"], True)
        assert change not in n1.getaddressesbyaccount("")

        self.log("fund node1 at a labeled address and at its change address")
        n0.generate(51)
        labeled = n1.getnewaddress("my savings")
        n0.sendtoaddress(labeled, 1000)
        n0.sendtoaddress(change, 250)
        n0.generate(1)
        self.sync_blocks()
        assert_equal(n1.getbalance(), 1250)

        self.log("dumpwallet writes every key with its role")
        dump = os.path.join(self.tmpdir, "node1.dump")
        assert_equal(n1.dumpwallet(dump)["filename"], dump)
        with open(dump) as f:
            text = f.read()
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        by_addr = {l.split("# addr=")[1]: l.split()[2] for l in lines}
        assert_equal(by_addr[labeled], "label=my%20savings")
        assert_equal(by_addr[change], "change=1")
        assert "reserve=1" in by_addr.values()
        assert text.rstrip().endswith("# End of dump")
        for addr in (labeled, change):
            assert n1.dumpprivkey(addr) in text

        self.log("dumpwallet refuses to overwrite an existing file")
        assert_raises_rpc_error(-8, "already exists", n1.dumpwallet, dump)

        self.log("importwallet into an empty wallet recovers funds and labels")
        assert_equal(n2.getbalance(), 0)
        n2.importwallet(dump)
        assert_equal(n2.getbalance(), 1250)
        assert_equal(n2.validateaddress(labeled)["ismine"], True)
        assert labeled in n2.getaddressesbyaccount("my savings")
        assert_equal(n2.validateaddress(change)["ismine"], True)

        self.log("re-importing is a no-op")
        n2.importwallet(dump)
        assert_equal(n2.getbalance(), 1250)
        assert_raises_rpc_error(-8, None, n2.importwallet, os.path.join(self.tmpdir, "missing.dump"))

        self.log("importprivkey adds one key, rescans, and relabels a key it already has")
        assert_raises_rpc_error(-5, "Invalid private key", n2.importprivkey, "notakey")
        single = n0.getnewaddress()
        n0.sendtoaddress(single, 75)
        n0.generate(1)
        self.sync_blocks()
        n2.importprivkey(n0.dumpprivkey(single), "imported")
        assert_equal(n2.validateaddress(single)["ismine"], True)
        assert single in n2.getaddressesbyaccount("imported")
        assert_equal(n2.getbalance(), 1325)
        n2.importprivkey(n0.dumpprivkey(single), "renamed")
        assert single in n2.getaddressesbyaccount("renamed")
        assert_equal(n2.getbalance(), 1325)


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + raw


def b58check_encode(payload):
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out


class WalletDumpBadSecretTest(WalletDumpTest):
    """A dump line whose secret is not a valid key (all ones: at or above the curve order) is a bad line, not an exception that leaves with
    the keys before it added and no search of the chain for them."""

    def run_test(self):
        super().run_test()
        n0, n1, n2 = self.nodes
        self.log("importwallet: a line with an invalid secret is reported, and the good key after it is still added and searched for")
        good_addr = n0.getnewaddress()
        n0.sendtoaddress(good_addr, 40)
        n0.generate(1)
        self.sync_blocks()
        version = b58decode(n0.dumpprivkey(good_addr))[:1]
        bad_wif = b58check_encode(version + b"\xff" * 32 + b"\x01")        # a compressed key whose secret is 2^256 - 1
        path = os.path.join(self.tmpdir, "bad_secret.dump")
        with open(path, "w") as f:
            f.write("%s 2020-01-01T00:00:00Z reserve=1 # addr=bad\n" % bad_wif)
            f.write("%s 2020-01-01T00:00:00Z reserve=1 # addr=%s\n" % (n0.dumpprivkey(good_addr), good_addr))
        before = n2.getbalance()
        assert_raises_rpc_error(-4, "Error adding some keys", n2.importwallet, path)       # no exception out of the daemon: an error, with the rest done
        assert_equal(n2.validateaddress(good_addr)["ismine"], True)
        assert_equal(n2.getbalance(), before + 40)


if __name__ == "__main__":
    WalletDumpBadSecretTest().main()
