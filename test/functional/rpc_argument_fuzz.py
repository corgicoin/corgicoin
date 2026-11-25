#!/usr/bin/env python3
"""Every RPC method, called with arguments of the wrong type, size and range: an error is the right answer, a dead node is not.

The method list comes from `help`. For each method the test sends each value of a pool of awkward values on its own, then random
combinations of 0 to 6 of them (fixed seed). A reply, whether a result or a JSON-RPC error, is fine. A dropped connection, a
non-JSON answer or a node that is no longer running fails the test, which under the sanitizer build also surfaces any memory error.
A few methods are left out because they write outside the data directory or end the node (stop) or start work that does not end
(setgenerate).
"""
import random

from test_framework import CorgiTestFramework, JSONRPCException, assert_equal

SKIP = {"stop", "setgenerate", "dumpwallet", "importwallet", "backupwallet", "exportwalletencrypted", "importwalletencrypted", "exportbootstrap", "importbootstrap",
        "walletpassphrasechange", "encryptwallet", "dumpprivkey", "keypoolrefill", "rescanblockchain", "generate", "generatetoaddress", "generateblock"}

POOL = [
    None, True, False, "", "0", "A" * 10000, "00" * 300, "ff" * 80, "-1", " ", "\u0000", "é中", "1e999",
    0, 1, -1, 2, 50, 2 ** 31, 2 ** 32, 2 ** 53, 2 ** 63, -2 ** 63, 2 ** 64, 10 ** 30,
    0.0, -0.0, 0.5, 1e-9, 1e308, -1e308, 21000000.0, 1e15,
    [], {}, [[]], [{}], {"a": 1}, [1, 2, 3], ["x"] * 200, [[[[[[]]]]]], {"": ""},
    "mnzrQWwsBwnwgMA8AzAGzqCFxbJzdoRYhd", "n" * 34, "0" * 64, "f" * 64, "00" * 80, "00" * 1000,
]


class RPCArgumentFuzz(CorgiTestFramework):
    num_nodes = 1

    def alive(self, node):
        assert node.process.poll() is None, "node exited with status %s" % node.process.returncode
        assert node.getblockcount() >= 5

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        methods = []
        for line in node.help().splitlines():
            name = line.split(" ")[0].strip()
            if name and name.isalnum() and name not in SKIP:
                methods.append(name)
        assert len(methods) > 40, methods
        self.log("%d methods" % len(methods))
        rng = random.Random(20261122)
        calls = 0
        for m in methods:
            combos = [[v] for v in POOL]
            for _ in range(60):
                combos.append([rng.choice(POOL) for _ in range(rng.randint(0, 6))])
            for params in combos:
                try:
                    node.rpc.call(m, *params)
                except JSONRPCException:
                    pass
                except Exception as e:
                    raise AssertionError("%s%r: %s: %s" % (m, str(params)[:120], type(e).__name__, str(e)[:200]))
                calls += 1
            self.alive(node)
        self.log("%d calls, node still up" % calls)


if __name__ == "__main__":
    RPCArgumentFuzz().main()
