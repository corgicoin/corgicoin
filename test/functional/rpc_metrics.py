#!/usr/bin/env python3
"""getmetrics returns the Prometheus text format, and the numbers follow the node."""
import re

from test_framework import CorgiTestFramework, assert_equal, wait_until
from mininode import P2PConnection


def parse(text):
    """{name: {labels-string: value}} for a Prometheus text exposition; HELP and TYPE are each given once per name."""
    helps, types, samples = {}, {}, {}
    for line in text.strip().split("\n"):
        if line.startswith("# HELP "):
            name = line.split()[2]
            assert name not in helps, "second HELP line for " + name
            helps[name] = True
        elif line.startswith("# TYPE "):
            name = line.split()[2]
            assert name not in types, "second TYPE line for " + name
            assert line.split()[3] in ("gauge", "counter"), line
            types[name] = line.split()[3]
        else:
            m = re.match(r'^([a-z_]+)(\{[^}]*\})? (-?[0-9.]+(?:e[+-]?[0-9]+)?)$', line)
            assert m, "not a sample line: %r" % line
            samples.setdefault(m.group(1), {})[m.group(2) or ""] = float(m.group(3))
    for name in samples:
        assert name in helps and name in types, name
    return samples


class MetricsTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        m = parse(node.getmetrics())
        assert_equal(m["corgicoin_blocks"][""], 5)
        assert m["corgicoin_uptime_seconds"][""] >= 0
        assert_equal(m["corgicoin_mempool_transactions"][""], 0)
        assert_equal(m["corgicoin_peers"]['{direction="in"}'], 0)
        assert_equal(m["corgicoin_rpc_active"][""], 1)        # this call

        self.log("the numbers follow the node: a transaction, a block, a peer")
        node.generate(100)
        node.sendtoaddress(node.getnewaddress(), 1)
        peer = P2PConnection(node.p2p_port)
        deadline_peers = 0
        while deadline_peers < 40 and parse(node.getmetrics())["corgicoin_peers"]['{direction="in"}'] < 1:
            import time
            time.sleep(0.25)
            deadline_peers += 1
        m = parse(node.getmetrics())
        assert_equal(m["corgicoin_blocks"][""], 105)
        assert_equal(m["corgicoin_mempool_transactions"][""], 1)
        assert m["corgicoin_mempool_bytes"][""] > 0
        assert_equal(m["corgicoin_peers"]['{direction="in"}'], 1)
        wait_until(lambda: parse(node.getmetrics())["corgicoin_network_received_bytes_total"][""] > 0, timeout=20,
                   what="the peer's first bytes to be counted")
        peer.close()


if __name__ == "__main__":
    MetricsTest().main()
