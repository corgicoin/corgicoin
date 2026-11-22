#!/usr/bin/env python3
"""-rpcauth=<user>:<salt>$<hash>: a login that holds no password in the configuration.

  1. A node with two -rpcauth lines and no -rpcuser/-rpcpassword: both users log in, a wrong password, a wrong user and the hash itself
     as password do not, and no cookie file is made.
  2. -rpcauth beside -rpcuser/-rpcpassword: all three logins work.
  3. A malformed -rpcauth line stops the node with a message that says what the form is.
"""
import base64
import http.client
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "contrib"))
import rpcauth as rpcauth_tool  # noqa: E402

from test_framework import CorgiTestFramework, assert_equal, RPC_USER, RPC_PASS  # noqa: E402


def login(node, user, password):
    auth = "Basic " + base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
    conn = http.client.HTTPConnection("127.0.0.1", node.rpc_port, timeout=30)
    try:
        conn.request("POST", "/", '{"method":"getblockcount","params":[],"id":1}', {"Authorization": auth})
        return conn.getresponse().status
    finally:
        conn.close()


class RPCAuthTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        line_a, pass_a, generated = rpcauth_tool.make("alice")
        assert generated and len(pass_a) >= 32
        line_b, pass_b, _ = rpcauth_tool.make("bob", "bobs password")
        line_t = rpcauth_tool.make(RPC_USER, RPC_PASS)[0]   # the framework's own login, so that it can still talk to the node
        assert "$" in line_a and line_a.split("$")[1] != pass_a

        self.log("-rpcauth beside -rpcuser/-rpcpassword: all three logins work")
        node.stop()
        node.start(["-rpcauth=" + line_a, "-rpcauth=" + line_b])
        assert_equal(login(node, "alice", pass_a), 200)
        assert_equal(login(node, "bob", "bobs password"), 200)
        assert_equal(login(node, RPC_USER, RPC_PASS), 200)
        assert_equal(login(node, "alice", pass_b), 401)

        self.log("only -rpcauth (no -rpcuser, no -rpcpassword): both users in, wrong ones out, no cookie file")
        node.stop()
        with open(os.path.join(node.datadir, "corgicoin.conf"), "w") as f:
            f.write("regtest=1\n")
        node.start(["-rpcauth=" + line_a, "-rpcauth=" + line_b, "-rpcauth=" + line_t])
        assert_equal(login(node, "alice", pass_a), 200)
        assert_equal(login(node, "bob", "bobs password"), 200)
        assert_equal(login(node, "alice", "wrong"), 401)
        assert_equal(login(node, "alice", ""), 401)
        assert_equal(login(node, "carol", pass_a), 401)
        assert_equal(login(node, "bob", pass_a), 401)
        assert_equal(login(node, "alice", line_a.split("$")[1]), 401)      # the hash itself is not the password
        assert_equal(login(node, "", ""), 401)
        assert_equal(login(node, "", pass_a), 401)
        assert not os.path.exists(os.path.join(node.datadir, "regtest", ".cookie")) and not os.path.exists(os.path.join(node.datadir, ".cookie"))
        assert_equal(node.getblockcount(), 0)

        self.log("a malformed -rpcauth stops the node, and says what the form is")
        node.stop()
        for bad in ("nosalt", "u:salt$short", "u:$" + "0" * 64, ":s$" + "0" * 64, "u:s$" + "G" * 64, "u:s$" + "0" * 63):
            try:
                node.start(["-rpcauth=" + bad])
            except Exception:
                pass
            else:
                raise AssertionError("%r was accepted" % bad)
            node.process.wait(timeout=30)
            node._note_exit()
        with open(node.stderr_log, errors="replace") as f:
            text = f.read()
        assert "-rpcauth is <user>:<salt>$<hash>" in text, text[-300:]


if __name__ == "__main__":
    RPCAuthTest().main()
