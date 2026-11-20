#!/usr/bin/env python3
"""importwalletencrypted: what a backup file must not be able to do, even when it is correctly encrypted. (Not in the runner until the node does all of it.)

Each case is a valid encryption made with backup_crafter.py. The cases are independent and all of them are run; the test fails at the end naming
every one that went wrong, so that one run says what is left:
  version   a file that says it is a version this wallet does not know is refused, not read as version 1;
  lying     a key that claims a far-off HD index (a file can write any path next to any key) does not move the next address to where a restore
            from the phrase never looks: the next address is made at or near the highest index of a key that derives from the phrase;
  pool      after the phrase has been adopted, the next address comes from the phrase (the key pool made before is rebuilt, as sethdseed does it),
            not from the random keys that were in the pool before: those are not recoverable from the phrase;
  nesting   a plain text of a million nested arrays does not take the node down (a recursive parser would run out of stack);
  size      a plain text of tens of megabytes (a valid object with a huge field) is not parsed and held in full: the node answers, stays up and
            holds no more than a backup could need.
"""
import os

from backup_crafter import b58check_decode, craft, payload, require_crypto
from test_framework import CorgiTestFramework, JSONRPCException

PASS = "a long backup passphrase"
PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"


class UntrustedBackupTest(CorgiTestFramework):
    num_nodes = 4

    def setup_nodes(self):
        super().setup_nodes()
        require_crypto(self)

    def write(self, node, name, data):
        path = os.path.join(node.datadir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def refused(self, node, path, adopt=False):
        try:
            node.importwalletencrypted(path, PASS, adopt)
        except JSONRPCException:
            return True
        except Exception:                                  # a connection that died with the daemon
            return False
        return False

    def alive(self, node):
        try:
            node.getblockcount()
            return True
        except Exception:
            return False

    def run_test(self):
        a, b, c, d = self.nodes
        for n in self.nodes:
            n.generate(1)
        addr = b.getnewaddress()
        secret = b.dumpprivkey(addr)
        key = {"secret": secret, "time": 1700000000, "hdkeypath": ""}
        failures = []

        self.log("version")
        for version in (2, 99, 0, -1, "1", None):
            f = self.write(a, "version.backup", craft(PASS, payload(version=version, keys=[key])))
            if not self.refused(a, f):
                failures.append("version %r was read as version 1" % (version,))
        if not self.alive(a):
            failures.append("version: the node went down")

        self.log("lying")
        lying = dict(key, hdkeypath="m/44'/99'/0'/0/999999999")
        f = self.write(c, "lying.backup", craft(PASS, payload(hdmnemonic=PHRASE, hdindex=999999999, keys=[lying])))
        c.importwalletencrypted(f, PASS, True)
        index = None
        for _ in range(60):
            info = c.validateaddress(c.getnewaddress())
            if "hdkeypath" in info:
                index = int(info["hdkeypath"].rsplit("/", 1)[1])
                break
        if index is None or index > 1010:
            failures.append("lying: the next address from the phrase is at index %r (a restore from the phrase looks to about 1000)" % (index,))

        self.log("pool")
        f = self.write(d, "pool.backup", craft(PASS, payload(hdmnemonic=PHRASE, keys=[])))
        d.importwalletencrypted(f, PASS, True)
        first = d.validateaddress(d.getnewaddress())
        if "hdkeypath" not in first:
            failures.append("pool: the first address after the phrase was adopted is not from the phrase (the old key pool was kept)")

        self.log("nesting")
        depth = 1000000
        f = self.write(b, "nest.backup", craft(PASS, b"[" * depth + b"]" * depth))
        self.refused(b, f)
        if not self.alive(b):
            failures.append("nesting: a million nested arrays took the node down")

        self.log("size")
        if self.alive(a):
            pad = b'{"version":1,"chain":"regtest","pad":"' + b"a" * (40 * 1024 * 1024) + b'","keys":[],"labels":[]}'
            f = self.write(a, "size.backup", craft(PASS, pad))
            if not self.refused(a, f):
                failures.append("size: a 40 MiB plain text was read and accepted")
            os.remove(f)
            if not self.alive(a):
                failures.append("size: the node went down")

        if failures:
            raise AssertionError("%d things a backup can still do:\n  " % len(failures) + "\n  ".join(failures))


if __name__ == "__main__":
    UntrustedBackupTest().main()
