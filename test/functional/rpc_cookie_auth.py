#!/usr/bin/env python3
"""Cookie authentication and the limit on failed logins.

With no -rpcuser and no -rpcpassword the node makes a random password, writes it to <datadir>/.cookie (mode 0600), serves
with it, and removes the file at a clean shutdown. After -rpcmaxauthfailures failed logins from one address, that address
is refused for a minute, even with the right password.
"""
import base64
import http.client
import json
import os
import stat
import subprocess
import time

from test_framework import CorgiTestFramework, RPC_PASS, RPC_USER, assert_equal

BODY = json.dumps({"method": "getblockcount", "params": [], "id": 1})


def post(node, user_pass):
    conn = http.client.HTTPConnection("127.0.0.1", node.rpc_port, timeout=30)
    try:
        headers = {"Authorization": "Basic " + base64.b64encode(user_pass.encode()).decode()}
        conn.request("POST", "/", BODY, headers)
        return conn.getresponse().status
    finally:
        conn.close()


class RPCCookieAuthTest(CorgiTestFramework):
    num_nodes = 1

    def start_cookie_node(self, node, conf, extra=()):
        """Start the node by hand: the framework's own start() logs in with the test password."""
        args = [node.binary, "-datadir=" + node.datadir, "-conf=" + conf, "-regtest", "-server", "-port=%d" % node.p2p_port,
                "-rpcport=%d" % node.rpc_port, "-bind=127.0.0.1", "-listen=1", "-keypool=10"] + list(extra)
        node.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cookie = os.path.join(node.datadir, "regtest", ".cookie")
        for _ in range(200):
            if os.path.exists(cookie) and open(cookie).read().strip():
                try:
                    if post(node, open(cookie).read().strip()) == 200:
                        return open(cookie).read().strip()
                except OSError:
                    pass
            time.sleep(0.1)
        raise AssertionError("the node did not come up with a cookie")

    def stop_cookie_node(self, node, user_pass):
        conn = http.client.HTTPConnection("127.0.0.1", node.rpc_port, timeout=30)
        conn.request("POST", "/", json.dumps({"method": "stop", "params": [], "id": 1}),
                     {"Authorization": "Basic " + base64.b64encode(user_pass.encode()).decode()})
        conn.getresponse().read()
        conn.close()
        node.process.wait(timeout=60)

    def run_test(self):
        node = self.nodes[0]
        conf = os.path.join(node.datadir, "nocreds.conf")
        cookie = os.path.join(node.datadir, "regtest", ".cookie")
        with open(conf, "w") as f:
            f.write("regtest=1"+chr(10))
        node.stop()

        self.log("no rpcuser or rpcpassword: the node serves with a cookie")
        user_pass = self.start_cookie_node(node, conf)
        if os.name != "nt":
            assert_equal(stat.S_IMODE(os.stat(cookie).st_mode), 0o600)
        assert user_pass.startswith("__cookie__:") and len(user_pass) > 40, user_pass
        assert_equal(post(node, "__cookie__:wrong"), 401)
        assert_equal(post(node, "%s:%s" % (RPC_USER, RPC_PASS)), 401)

        self.log("the file goes at shutdown, and the next start makes a new password")
        self.stop_cookie_node(node, user_pass)
        assert not os.path.exists(cookie), "cookie left behind"
        new_pass = self.start_cookie_node(node, conf, ["-rpcmaxauthfailures=5"])
        assert new_pass != user_pass
        assert_equal(post(node, new_pass), 200)

        self.log("five failed logins lock the address out, even for the right password")
        for _ in range(5):
            assert_equal(post(node, "__cookie__:wrong"), 401)
        assert_equal(post(node, new_pass), 401)
        node.kill()


if __name__ == "__main__":
    RPCCookieAuthTest().main()
