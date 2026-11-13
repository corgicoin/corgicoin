#!/usr/bin/env python3
"""The JSON-RPC server bounds what an unauthenticated client can make it do.

The whole request was read before the login was checked: header lines were unbounded, a Content-Length of
32 MiB was allocated up front, every connection got a thread with no limit and no timeout, so one client could use
up the node's memory or threads. Now lines, header count and body are capped (the body is only read after the
login), a stalled connection is closed after -rpcservertimeout seconds, and past -rpcmaxconnections the answer is 503.
"""
import base64
import json
import socket
import time

from test_framework import CorgiTestFramework, RPC_PASS, RPC_USER, assert_equal

AUTH = "Basic " + base64.b64encode(("%s:%s" % (RPC_USER, RPC_PASS)).encode()).decode()
BODY = json.dumps({"method": "getblockcount", "params": [], "id": 1})


class HTTPLimitsTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-rpcservertimeout=3", "-rpcmaxbody=100000", "-rpcmaxconnections=20"]]

    def connect(self, node):
        return socket.create_connection(("127.0.0.1", node.rpc_port), timeout=15)

    def read_status(self, s):
        """First line of the reply, or None when the connection was closed without one."""
        data = b""
        try:
            while b"\r\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    return None
                data += chunk
        except (socket.timeout, ConnectionError):
            return None
        return data.split(b"\r\n")[0].decode(errors="replace")

    def good_request(self, node):
        s = self.connect(node)
        s.sendall(("POST / HTTP/1.1\r\nHost: x\r\nAuthorization: %s\r\nConnection: close\r\nContent-Length: %d\r\n\r\n%s"
                   % (AUTH, len(BODY), BODY)).encode())
        status = self.read_status(s)
        s.close()
        return status

    def run_test(self):
        node = self.nodes[0]
        node.generate(2)
        assert "200" in self.good_request(node)

        self.log("a request line with no end, far longer than any line should be: refused, node fine")
        s = self.connect(node)
        s.sendall(b"POST /" + b"a" * 20000)
        status = self.read_status(s)
        s.close()
        assert status is None or "431" in status, status
        assert "200" in self.good_request(node)

        self.log("more header lines than allowed: refused")
        s = self.connect(node)
        s.sendall(b"POST / HTTP/1.1\r\n" + b"".join(b"X-%d: y\r\n" % i for i in range(300)) + b"\r\n")
        status = self.read_status(s)
        s.close()
        assert status is None or "431" in status, status

        self.log("a huge Content-Length with no login is answered 401 at once, without waiting for or allocating a body")
        s = self.connect(node)
        start = time.time()
        s.sendall(b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 33554432\r\n\r\n")
        status = self.read_status(s)
        s.close()
        assert status is not None and "401" in status, status
        assert time.time() - start < 2, "the 401 should not wait for the body"

        self.log("a huge Content-Length with a login is refused as too large")
        s = self.connect(node)
        s.sendall(("POST / HTTP/1.1\r\nHost: x\r\nAuthorization: %s\r\nContent-Length: 33554432\r\n\r\n" % AUTH).encode())
        status = self.read_status(s)
        s.close()
        assert status is not None and "413" in status, status

        self.log("a Content-Length that is not a number is a bad request")
        s = self.connect(node)
        s.sendall(("POST / HTTP/1.1\r\nHost: x\r\nAuthorization: %s\r\nContent-Length: -5\r\n\r\n" % AUTH).encode())
        status = self.read_status(s)
        s.close()
        assert status is not None and "400" in status, status

        self.log("a body that never arrives: the connection is closed after the timeout")
        s = self.connect(node)
        s.sendall(("POST / HTTP/1.1\r\nHost: x\r\nAuthorization: %s\r\nContent-Length: 100\r\n\r\n{" % AUTH).encode())
        start = time.time()
        assert self.read_status(s) is None
        took = time.time() - start
        s.close()
        assert 2 < took < 12, "closed after %.1f s" % took

        self.log("past -rpcmaxconnections the answer is 503, and the slots come back when the idle ones time out")
        idle = [self.connect(node) for _ in range(40)]
        time.sleep(0.5)
        refused = 0
        for s in idle:
            s.settimeout(0.3)
            try:
                if b"503" in s.recv(200):
                    refused += 1
            except (socket.timeout, ConnectionError):
                pass
        assert refused >= 10, "only %d of 40 connections were refused" % refused
        for s in idle:
            s.close()
        time.sleep(5)       # idle handler threads give up after 3 s
        assert "200" in self.good_request(node)
        assert_equal(node.getblockcount(), 2)


if __name__ == "__main__":
    HTTPLimitsTest().main()
