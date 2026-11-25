#!/usr/bin/env python3
"""A refused RPC request has its body read before the connection is closed.

The server answered a missing or wrong login with 401 and closed the socket without reading the request body. Closing a socket that holds
unread data resets the connection instead of ending it, and on Windows the reset throws away the reply the client has not read yet: a wrong
password reached the client as "connection reset by peer" and not as 401. Now the reply is sent first and the body (up to 64 KB) is read
and dropped before the socket is closed.

The test sends the head of a request with a body length and no body, reads the 401, and then looks at the connection: the old server had
closed it by then, the new one is still waiting for the body. It sends the body, and the connection must end cleanly (no reset).
"""
import base64
import socket

from test_framework import CorgiTestFramework, assert_equal

BODY = 1000


def read_head(s):
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise AssertionError("the connection ended before a reply: %r" % buf)
        buf += chunk
    return buf


class RefusedBodyTest(CorgiTestFramework):
    num_nodes = 1

    def refused(self, node, authorization, what):
        s = socket.create_connection(("127.0.0.1", node.rpc_port), timeout=10)
        try:
            head = "POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: %d\r\n" % BODY
            if authorization:
                head += "Authorization: Basic %s\r\n" % base64.b64encode(authorization).decode()
            s.sendall((head + "\r\n").encode())
            reply = read_head(s)
            assert reply.startswith(b"HTTP/1.") and reply.split(b" ", 2)[1] == b"401", (what, reply[:60])

            # the body has not been sent: a server that has read it, or is waiting for it, keeps the connection; one that closed already does not
            s.settimeout(1.0)
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                pass
            else:
                raise AssertionError("%s: the server closed the connection before the body was read (recv gave %r)" % (what, chunk))

            s.settimeout(10)
            s.sendall(b"x" * BODY)
            try:
                tail = s.recv(4096)
            except ConnectionResetError:
                raise AssertionError("%s: the connection was reset after the body was sent" % what)
            assert_equal(tail, b"")                 # the end of the connection, with nothing more to say
        finally:
            s.close()

    def run_test(self):
        node = self.nodes[0]
        self.log("a request with no login")
        self.refused(node, None, "no login")
        self.log("a request with the wrong password")
        self.refused(node, b"nobody:wrong", "wrong password")
        self.log("the node still answers a correct login")
        assert_equal(node.getblockcount(), 0)


if __name__ == "__main__":
    RefusedBodyTest().main()
