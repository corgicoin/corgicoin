#!/usr/bin/env python3
"""Shutdown does not wait for idle keep-alive RPC connections.

Pool software holds its HTTP connection open between calls, and the daemon used to wait for that connection to
close before it would finish stopping (under docker or systemd the wait ends in a kill, and the final database
flush never runs). Here a raw client makes one authenticated call, keeps the socket open, and another client asks
the node to stop; the node must exit with status 0 in a few seconds.
"""
import base64
import json
import socket
import time

from test_framework import CorgiTestFramework, RPC_PASS, RPC_USER, AssertionFailed


class ShutdownKeepAliveTest(CorgiTestFramework):
    num_nodes = 1

    def idle_connection(self, node):
        auth = base64.b64encode(("%s:%s" % (RPC_USER, RPC_PASS)).encode()).decode()
        body = json.dumps({"method": "getblockcount", "params": [], "id": 1})
        req = ("POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Basic %s\r\nConnection: keep-alive\r\n"
               "Content-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (auth, len(body), body))
        s = socket.create_connection(("127.0.0.1", node.rpc_port), timeout=30)
        s.sendall(req.encode())
        reply = b""
        while b"\r\n\r\n" not in reply or b'"result"' not in reply:
            chunk = s.recv(4096)
            if not chunk:
                raise AssertionFailed("connection closed before the first reply: %r" % reply)
            reply += chunk
        assert b"keep-alive" in reply.lower(), reply
        return s

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)

        self.log("two clients make a call and then sit on their open connections")
        idle = [self.idle_connection(node), self.idle_connection(node)]

        self.log("stop is requested from a third connection")
        start = time.time()
        node.rpc.stop()
        try:
            node.process.wait(timeout=15)
        except Exception:
            raise AssertionFailed("the node was still running 15 s after stop with idle keep-alive clients connected")
        took = time.time() - start
        self.log("the node exited with status %s after %.1f s" % (node.process.returncode, took))
        if node.process.returncode != 0:
            raise AssertionFailed("exit status %s" % node.process.returncode)
        for s in idle:
            s.close()


if __name__ == "__main__":
    ShutdownKeepAliveTest().main()
