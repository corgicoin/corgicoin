"""Minimal functional-test framework for corgicoind (regtest).

Modeled on Bitcoin Core's test/functional, cut down to what CorgiCoin needs:
start N regtest nodes in a temp dir, talk JSON-RPC to them, wire them
together, and wait for them to agree. Standard library only.

A test is a subclass of CorgiTestFramework that sets `num_nodes` and
implements run_test(). Run it directly, or via test_runner.py:

    python3 test/functional/feature_regtest_basics.py --corgicoind build/corgicoind
"""

import argparse
import base64
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from decimal import Decimal

RPC_USER = "corgitest"
RPC_PASS = "corgitest"


class JSONRPCException(Exception):
    def __init__(self, error):
        self.error = error
        self.code = error.get("code")
        super().__init__("%s (%s)" % (error.get("message"), self.code))


class AssertionFailed(Exception):
    pass


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(predicate, timeout=30, interval=0.25, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionFailed("timed out after %ss waiting for %s" % (timeout, what))


def assert_equal(a, b, msg=""):
    if a != b:
        raise AssertionFailed("%r != %r %s" % (a, b, msg))


def assert_greater_than(a, b):
    if not a > b:
        raise AssertionFailed("%r <= %r" % (a, b))


def assert_raises_rpc_error(code, fragment, fn, *args):
    """Call fn(*args) and require a JSON-RPC error with this code whose
    message contains fragment (either may be None to skip that check)."""
    try:
        fn(*args)
    except JSONRPCException as e:
        if code is not None and e.code != code:
            raise AssertionFailed("expected error code %s, got %s: %s" % (code, e.code, e))
        if fragment is not None and fragment not in e.error.get("message", ""):
            raise AssertionFailed("expected %r in error message, got %r" % (fragment, e.error.get("message")))
        return
    raise AssertionFailed("no RPC error raised")


class RPCProxy:
    """`node.rpc.getblockcount()` style JSON-RPC client.

    corgicoind returns HTTP 500 for application-level errors (Bitcoin RPC
    convention), so the body is always parsed before the status is judged.
    """

    def __init__(self, port, timeout=120):
        self.port = port
        self.timeout = timeout
        self._auth = "Basic " + base64.b64encode(("%s:%s" % (RPC_USER, RPC_PASS)).encode()).decode()
        self._id = 0

    def call(self, method, *params):
        self._id += 1
        body = json.dumps({"version": "1.1", "method": method, "params": list(params), "id": self._id},
                          default=lambda d: float(d) if isinstance(d, Decimal) else str(d))
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            conn.request("POST", "/", body, {"Authorization": self._auth, "Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            reply = json.loads(raw, parse_float=Decimal)
        except ValueError:
            raise Exception("HTTP %s from %s: %r" % (resp.status, method, raw[:200]))
        if reply.get("error"):
            raise JSONRPCException(reply["error"])
        return reply["result"]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *params: self.call(name, *params)


class TestNode:
    def __init__(self, index, binary, datadir, extra_args=None):
        self.index = index
        self.binary = binary
        self.datadir = datadir
        self.p2p_port = free_port()
        self.rpc_port = free_port()
        self.extra_args = list(extra_args or [])
        self.process = None
        self.rpc = RPCProxy(self.rpc_port)
        os.makedirs(datadir, exist_ok=True)
        with open(os.path.join(datadir, "corgicoin.conf"), "w") as f:
            f.write("regtest=1\nrpcuser=%s\nrpcpassword=%s\n" % (RPC_USER, RPC_PASS))

    @property
    def p2p_addr(self):
        return "127.0.0.1:%d" % self.p2p_port

    def start(self, extra_args=None):
        args = [self.binary, "-datadir=" + self.datadir, "-regtest", "-server",
                "-port=%d" % self.p2p_port, "-rpcport=%d" % self.rpc_port,
                "-bind=127.0.0.1", "-listen=1", "-printtoconsole=0", "-keypool=10"]
        args += self.extra_args + list(extra_args or [])
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_for_rpc()

    def wait_for_rpc(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise AssertionFailed("node%d exited during startup (code %s); see %s"
                                      % (self.index, self.process.returncode, self.debug_log))
            try:
                self.rpc.getblockcount()
                return
            except (ConnectionError, OSError, JSONRPCException, Exception) as e:
                # -28-style "loading" errors and refused connections both mean "not yet"
                time.sleep(0.25)
        raise AssertionFailed("node%d RPC did not come up within %ss" % (self.index, timeout))

    def stop(self, timeout=60):
        if not self.process or self.process.poll() is not None:
            return
        try:
            self.rpc.stop()
        except Exception:
            pass
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def kill(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    @property
    def debug_log(self):
        return os.path.join(self.datadir, "regtest", "debug.log")

    def __getattr__(self, name):
        # node.getblockcount() as shorthand for node.rpc.getblockcount()
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.rpc, name)


class CorgiTestFramework:
    num_nodes = 1
    extra_args = None  # list of per-node arg lists

    def __init__(self):
        p = argparse.ArgumentParser(description=self.__doc__)
        p.add_argument("--corgicoind", default=os.environ.get("CORGICOIND", default_binary()),
                       help="path to corgicoind (default: $CORGICOIND or build*/corgicoind)")
        p.add_argument("--tmpdir", help="directory for node datadirs (default: a fresh temp dir)")
        p.add_argument("--nocleanup", action="store_true", help="keep datadirs after a passing run")
        self.options = p.parse_args()
        self.nodes = []

    # -- topology helpers ------------------------------------------------
    def connect_nodes(self, a, b):
        """Have node a dial node b and wait for the handshake on both ends."""
        na, nb = self.nodes[a], self.nodes[b]
        before_a = na.getconnectioncount()
        na.addnode(nb.p2p_addr, "onetry")
        wait_until(lambda: any(p["addr"] == nb.p2p_addr and p["version"] > 0 for p in na.getpeerinfo()),
                   what="node%d -> node%d connection" % (a, b))
        wait_until(lambda: nb.getconnectioncount() > 0, what="node%d to see inbound peer" % b)

    def disconnect_nodes(self, a, b):
        """Drop every link between nodes a and b. All nodes share 127.0.0.1,
        so inbound peers can't be told apart by address; links are found by
        their dialed (outbound) side and the inbound side is inferred from
        connection counts."""
        na, nb = self.nodes[a], self.nodes[b]
        count_a, count_b = na.getconnectioncount(), nb.getconnectioncount()
        links = 0
        for src, dst in ((na, nb), (nb, na)):
            for p in src.getpeerinfo():
                if not p["inbound"] and p["addr"] == dst.p2p_addr:
                    src.disconnectnode(p["addr"])
                    links += 1
        if links == 0:
            raise AssertionFailed("node%d and node%d are not connected" % (a, b))
        wait_until(lambda: na.getconnectioncount() == count_a - links and
                           nb.getconnectioncount() == count_b - links,
                   what="node%d/node%d to disconnect" % (a, b))

    def sync_blocks(self, nodes=None, timeout=60):
        nodes = nodes or self.nodes
        wait_until(lambda: len({n.getbestblockhash() for n in nodes}) == 1, timeout=timeout,
                   what="block sync (%s)" % [n.getblockcount() for n in nodes])

    def sync_mempools(self, nodes=None, timeout=60):
        nodes = nodes or self.nodes
        wait_until(lambda: len({tuple(sorted(n.getrawmempool())) for n in nodes}) == 1,
                   timeout=timeout, what="mempool sync")

    # -- lifecycle ---------------------------------------------------------
    def setup_nodes(self):
        for i in range(self.num_nodes):
            args = self.extra_args[i] if self.extra_args else None
            node = TestNode(i, self.options.corgicoind, os.path.join(self.tmpdir, "node%d" % i), args)
            self.nodes.append(node)
            node.start()

    def run_test(self):
        raise NotImplementedError

    def log(self, msg):
        print("[%s] %s" % (type(self).__name__, msg), flush=True)

    def main(self):
        if not os.path.isfile(self.options.corgicoind):
            print("corgicoind not found at %r (use --corgicoind)" % self.options.corgicoind)
            sys.exit(2)
        self.tmpdir = self.options.tmpdir or tempfile.mkdtemp(prefix="corgi_func_")
        ok = False
        try:
            self.setup_nodes()
            self.run_test()
            ok = True
        except Exception:
            traceback.print_exc()
        finally:
            for n in self.nodes:
                n.stop()
            for n in self.nodes:
                n.kill()
        if ok:
            self.log("PASSED")
            if not self.options.nocleanup and not self.options.tmpdir:
                shutil.rmtree(self.tmpdir, ignore_errors=True)
            sys.exit(0)
        self.log("FAILED; datadirs kept in %s" % self.tmpdir)
        for n in self.nodes:
            if os.path.exists(n.debug_log):
                print("---- node%d debug.log (tail) ----" % n.index)
                with open(n.debug_log, errors="replace") as f:
                    print("".join(f.readlines()[-40:]))
        sys.exit(1)


def default_binary():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    for d in ("build", "build-test", "build-release"):
        p = os.path.join(root, d, "corgicoind")
        if os.path.isfile(p):
            return p
    return os.path.join(root, "build", "corgicoind")
