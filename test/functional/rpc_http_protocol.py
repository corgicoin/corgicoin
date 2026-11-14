#!/usr/bin/env python3
"""The HTTP / JSON-RPC layer: batches, and what a malformed request gets (an error answer, never a crash or a hang)."""
import base64
import http.client
import json

from test_framework import CorgiTestFramework, RPC_PASS, RPC_USER, assert_equal


class HTTPProtocolTest(CorgiTestFramework):
    num_nodes = 1

    def post(self, node, body, method="POST", path="/"):
        conn = http.client.HTTPConnection("127.0.0.1", node.rpc_port, timeout=20)
        try:
            auth = "Basic " + base64.b64encode((RPC_USER + ":" + RPC_PASS).encode()).decode()
            conn.request(method, path, body, {"Authorization": auth})
            r = conn.getresponse()
            return r.status, json.loads(r.read())
        finally:
            conn.close()

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)

        self.log("a batch gets one answer per request, in order, each with its own id")
        status, reply = self.post(node, json.dumps([
            {"method": "getblockcount", "params": [], "id": "a"},
            {"method": "getbestblockhash", "params": [], "id": "b"},
            {"method": "nosuchmethod", "params": [], "id": "c"},
        ]))
        assert_equal(status, 200)
        assert_equal([r["id"] for r in reply], ["a", "b", "c"])
        assert_equal(reply[0]["result"], 3)
        assert_equal(reply[1]["result"], node.getbestblockhash())
        assert_equal(reply[2]["error"]["code"], -32601)
        assert reply[2]["result"] is None

        self.log("an empty batch is an empty answer")
        assert_equal(self.post(node, "[]"), (200, []))

        self.log("what is not JSON, or not an object or a batch, is a parse error")
        for body in ("hello", "42", "", '{"method": '):
            status, reply = self.post(node, body)
            assert_equal(status, 500)
            assert_equal(reply["error"]["code"], -32700)

        self.log("a request with no method, or params that are not an array, is an invalid request")
        status, reply = self.post(node, json.dumps({"method": None, "params": [], "id": 1}))
        assert_equal((status, reply["error"]["code"]), (400, -32600))
        status, reply = self.post(node, json.dumps({"method": "getblockhash", "params": {"height": 1}, "id": 2}))
        assert_equal((status, reply["error"]["code"]), (400, -32600))

        self.log("the node is still fine afterwards")
        assert_equal(node.getblockcount(), 3)


if __name__ == "__main__":
    HTTPProtocolTest().main()
