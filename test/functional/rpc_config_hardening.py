#!/usr/bin/env python3
"""RPC configuration traps: the example password, '#' in a password, and -rpcbind.

- The password in contrib/corgicoin.conf.example is public; the node refuses to serve with it.
- '#' starts a comment anywhere on a config line, so "rpcpassword=abc#def" silently meant "abc". The node refuses.
- -rpcbind restricts the listening address; an invalid one is an error.
"""
import os
import socket

from test_framework import AssertionFailed, CorgiTestFramework, RPC_PASS, RPC_USER, assert_equal


class ConfigHardeningTest(CorgiTestFramework):
    num_nodes = 1

    def conf(self, node):
        return os.path.join(node.datadir, "corgicoin.conf")

    def write_conf(self, node, *lines):
        with open(self.conf(node), "w") as f:
            f.write("\n".join(("regtest=1",) + lines) + "\n")

    def refuses_to_start(self, node, extra=None):
        """True if the node exits instead of coming up. (A node that never answers is not a refusal: it is killed and False is returned.)"""
        try:
            node.start(extra)
        except AssertionFailed:
            if node.process.poll() is not None:
                return True
            node.kill()
            return False
        node.stop()
        return False

    def can_connect(self, host, port, family):
        s = socket.socket(family, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def ipv6_loopback_usable(self):
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            s.bind(("::1", 0))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def run_test(self):
        node = self.nodes[0]
        node.stop()

        self.log("the example password is refused")
        self.write_conf(node, "rpcuser=corgirpc", "rpcpassword=CHANGE_THIS_PASSWORD")
        assert self.refuses_to_start(node), "the node served with the example password"

        self.log("a '#' in rpcpassword is refused")
        self.write_conf(node, "rpcuser=%s" % RPC_USER, "rpcpassword=%s#and-more" % RPC_PASS)
        assert self.refuses_to_start(node), "the node started with a password cut off at '#'"

        self.log("a '#' in a comment line is fine")
        self.write_conf(node, "rpcuser=%s" % RPC_USER, "rpcpassword=%s" % RPC_PASS, "# a comment with a # in it")
        node.start()
        assert_equal(node.getblockcount(), 0)
        node.stop()

        self.log("an invalid -rpcbind is an error")
        self.write_conf(node, "rpcuser=%s" % RPC_USER, "rpcpassword=%s" % RPC_PASS)
        assert self.refuses_to_start(node, ["-rpcbind=not-an-ip"]), "the node started with -rpcbind=not-an-ip"

        self.log("-rpcbind=127.0.0.1 listens on IPv4 loopback only")
        node.start(["-rpcbind=127.0.0.1"])
        assert_equal(node.getblockcount(), 0)
        assert self.can_connect("127.0.0.1", node.rpc_port, socket.AF_INET)
        if self.ipv6_loopback_usable():
            assert not self.can_connect("::1", node.rpc_port, socket.AF_INET6), "also listening on ::1"


if __name__ == "__main__":
    ConfigHardeningTest().main()
