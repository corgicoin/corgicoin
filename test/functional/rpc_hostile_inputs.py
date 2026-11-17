#!/usr/bin/env python3
"""Hostile arguments to the RPCs that parse caller-supplied data: each must be refused with an error, and the node
must still answer afterwards.

Covers getblock's verbosity (#106, and integers too large for their argument, which used to be cut to 32 bits),
empty and odd hex fed to the transaction/block decoders (#105), addmultisigaddress limits (#102) and recovery
phrases that are malformed, huge or full of look-alike Unicode (#104). A messily spaced but valid phrase is
accepted, stored in canonical form, and survives a restart.
"""
from test_framework import CorgiTestFramework, JSONRPCException, AssertionFailed, assert_equal

CANON = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
VALID24 = ("legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth "
           "useful legal winner thank year wave sausage worth title")


class HostileInputsTest(CorgiTestFramework):
    num_nodes = 1

    def refused(self, label, method, *params):
        """method(*params) must fail with a JSON-RPC error, not succeed and not take the node down."""
        node = self.nodes[0]
        try:
            r = node.rpc.call(method, *params)
        except JSONRPCException:
            pass
        else:
            raise AssertionFailed("%s: expected an error, got %r" % (label, repr(r)[:100]))
        assert_equal(node.getblockcount(), self.height, "node still answering after: " + label)

    def accepted(self, label, method, *params):
        node = self.nodes[0]
        r = node.rpc.call(method, *params)
        assert_equal(node.getblockcount(), self.height, "node still answering after: " + label)
        return r

    def run_test(self):
        node = self.nodes[0]
        node.generate(60)
        self.height = 60
        h = node.getbestblockhash()

        self.log("getblock: wrong types, out-of-range verbosity, bad hashes")
        for label, v in [("null", None), ("string", "true"), ("float", 1.5), ("array", []), ("object", {}),
                         ("-1", -1), ("3", 3), ("2^31", 2 ** 31), ("2^40", 2 ** 40), ("-2^63", -2 ** 63),
                         ("2^64-1", 2 ** 64 - 1)]:
            self.refused("getblock verbose=" + label, "getblock", h, v)
        for v in (False, 0):
            self.accepted("getblock verbose=%r" % v, "getblock", h, v)
        self.refused("getblock with 3 params", "getblock", h, False, 1)
        self.refused("getblock with no params", "getblock")
        self.refused("getblock hash as int", "getblock", 123)
        for label, bad in [("non-hex", "zz" * 40), ("empty", ""), ("10k chars", "f" * 10000)]:
            self.refused("getblock hash " + label, "getblock", bad, False)

        self.log("empty and odd hex into the decoders")
        for method, params in [("decoderawtransaction", [""]), ("decoderawtransaction", ["zz"]),
                               ("decoderawtransaction", ["0"]), ("sendrawtransaction", [""]),
                               ("testmempoolaccept", [[""]]), ("testmempoolaccept", [["zz"]]),
                               ("submitblock", [""]), ("submitblock", ["00"]),
                               ("signrawtransaction", [""])]:
            self.refused("%s %r" % (method, params), method, *params)

        self.log("addmultisigaddress: counts, sizes, types and integers that don't fit")
        pks = [node.validateaddress(node.getnewaddress())["pubkey"] for _ in range(17)]
        self.accepted("15 keys", "addmultisigaddress", 1, pks[:15])
        self.accepted("15 copies of one key", "addmultisigaddress", 1, [pks[0]] * 15)
        for label, n, keys in [("16 compressed keys", 1, pks[:16]), ("17 keys", 1, pks[:17]),
                               ("1000 keys", 1, (pks * 60)[:1000]), ("nrequired -1", -1, pks[:3]),
                               ("nrequired 2^31-1", 2 ** 31 - 1, pks[:3]),
                               ("nrequired 2^32+1, once read as 1", 2 ** 32 + 1, pks[:3]),
                               ("nrequired 2^64-1", 2 ** 64 - 1, pks[:3]), ("nrequired as string", "2", pks[:3]),
                               ("no keys", 1, []), ("garbage key", 1, ["zz", pks[0]]),
                               ("over-long key", 1, ["02" + "ab" * 200])]:
            self.refused("addmultisigaddress " + label, "addmultisigaddress", n, keys)

        self.log("sethdseed: phrases that must not become a wallet")
        for label, phrase in [("empty", ""), ("only whitespace", " \t\n　 "),
                              ("NUL between words", CANON.replace(" ", "\x00", 1)),
                              ("1 MB of one word", "abandon" * 150000),
                              ("right-to-left override", "‮" + CANON),
                              ("zero-width space instead of a space", CANON.replace(" ", "​", 1)),
                              ("full-width letter", CANON.replace("about", "ａbout")),
                              ("13 words", CANON + " abandon"), ("integer", 12345), ("null", None)]:
            self.refused("sethdseed " + label, "sethdseed", phrase)
        assert_equal(node.getwalletinfo().get("hdseedid"), None, "no seed was set by any refused phrase")

        self.log("sethdseed: messy but valid phrases are accepted and stored in canonical form")
        r = self.accepted("100k spaces between two words", "sethdseed", CANON.replace(" ", " " * 100000, 1))
        assert_equal(r["mnemonic"], CANON)
        r = self.accepted("24 words with ideographic, em and no-break spaces", "sethdseed",
                          "　" + VALID24.replace(" ", "   ") + "\n")
        assert_equal(r["mnemonic"], VALID24)
        seed_id = node.getwalletinfo()["hdseedid"]
        addr = node.getnewaddress()
        node.stop()
        node.start()
        assert_equal(node.getwalletinfo()["hdseedid"], seed_id)
        assert node.validateaddress(addr)["ismine"]


if __name__ == "__main__":
    HostileInputsTest().main()
