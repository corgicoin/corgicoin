#!/usr/bin/env python3
"""The JSON-RPC server answers malformed Authorization headers with 401 and keeps running.

The header is decoded (base64) before the credentials are checked, so it is the first thing an
unauthenticated client controls. Each case below must be refused with 401, the node must stay up and
answer a properly authenticated request afterwards, and a correct login must still work.
"""
import base64
import http.client
import json

from test_framework import (CorgiTestFramework, RPC_PASS, RPC_USER, assert_equal)

BODY = json.dumps({"method": "getblockcount", "params": [], "id": 1})


def b64(text):
    return base64.b64encode(text.encode()).decode()


class RPCHTTPAuthTest(CorgiTestFramework):
    num_nodes = 1

    def post(self, node, authorization):
        """POST a JSON-RPC request with the given Authorization header value (None = no header)."""
        headers = {"Content-Type": "application/json"}
        if authorization is not None:
            headers["Authorization"] = authorization
        conn = http.client.HTTPConnection("127.0.0.1", node.rpc_port, timeout=30)
        try:
            conn.request("POST", "/", BODY, headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)
        good = "Basic " + b64("%s:%s" % (RPC_USER, RPC_PASS))

        refused = {
            "no Authorization header": None,
            "wrong scheme": "Bearer abcdef",
            "scheme only": "Basic",
            "invalid base64 (decodes to nothing)": "Basic !!!!",
            "only padding": "Basic ====",
            "valid base64 of nothing useful": "Basic " + b64("x"),
            "user without password": "Basic " + b64(RPC_USER),
            "wrong password": "Basic " + b64("%s:%s" % (RPC_USER, "not-the-password")),
            "right password, wrong user": "Basic " + b64("someone:%s" % RPC_PASS),
            "binary garbage": "Basic " + base64.b64encode(bytes(range(256))).decode(),
            "very long value": "Basic " + "A" * 60000,
        }
        for label, value in refused.items():
            self.log("refuses: %s" % label)
            status, _ = self.post(node, value)
            assert_equal(status, 401, "for %s" % label)
            # the server must still be alive and serving authenticated requests
            assert_equal(node.getblockcount(), 3)

        self.log("a correct login still works")
        status, body = self.post(node, good)
        assert_equal(status, 200)
        assert_equal(json.loads(body)["result"], 3)


if __name__ == "__main__":
    RPCHTTPAuthTest().main()
