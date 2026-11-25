#!/usr/bin/env python3
"""A replacement in a pool that is full: it is not thrown out by the size limit after it has taken its conflicts with it.

The pool is held to about 10 kB. It is filled with replaceable transactions; the one with the lowest fee rate is X. A bigger replacement R of X
(more inputs) needs more room than the pool has:
  - when R's fee rate is the lowest in the pool once X is gone, it would be the one thrown out: it is refused (mempool-full) and X is still there,
    the pool is as it was. (Before the check was made ahead of the removal, X went and R was thrown out after it: both lost.)
  - when R pays more per byte than the others, it is accepted, X is gone, the lowest of the others went to make room, and the pool is within its limit.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, JSONRPCException, assert_equal, assert_raises_rpc_error

CAP = 10000
SAT = Decimal("0.00000001")


class RBFFullPoolTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-maxmempoolkb=10", "-mempoolreplacement"]]

    def build(self, node, coins, outputs, signal):
        ins = [{"txid": c["txid"], "vout": c["vout"]} for c in coins]
        raw = node.createrawtransaction(ins, outputs)
        if signal:
            pos = 8 + 2 + 72 + 2
            for _ in ins:
                raw = raw[:pos] + "fdffffff" + raw[pos + 8:]
                pos += 8 + 72 + 2
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(300)
        utxos = [c for c in node.listunspent() if c["amount"] > 100]
        dest = node.getnewaddress()

        self.log("fill the pool with replaceable transactions that pay 5 coins and a bit, each a little more than the one before")
        info = {}                                              # txid -> (fee, size, coin)
        for i, c in enumerate(utxos[:80]):
            fee = Decimal(5) + Decimal(i) / 100
            hexs = self.build(node, [c], {dest: c["amount"] - fee}, True)
            txid = node.sendrawtransaction(hexs)
            info[txid] = (fee, len(hexs) // 2, c)
        pool = node.getrawmempool()
        assert node.getmempoolinfo()["bytes"] <= CAP
        assert 20 < len(pool) < 80, len(pool)
        by_rate = sorted(pool, key=lambda t: info[t][0] / info[t][1])
        x, y = by_rate[0], by_rate[1]
        rate_x, rate_y = info[x][0] / info[x][1], info[y][0] / info[y][1]
        assert rate_y > rate_x * Decimal("1.0001"), "the two lowest rates are too close to put one between them"
        before = sorted(pool)
        bytes_before = node.getmempoolinfo()["bytes"]

        # R: X's coin and three others, to one output: bigger than X by far, so the pool has no room for it
        extra = utxos[80:83]
        coins_r = [info[x][2]] + extra
        total = sum(c["amount"] for c in coins_r)
        size_r = len(self.build(node, coins_r, {dest: total - Decimal(10)}, True)) // 2
        assert size_r > info[x][1] + 300

        self.log("R pays more than X per byte but less than the others: it would be thrown out, so it is refused and X stays")
        fee_low = ((rate_x + rate_y) / 2 * size_r).quantize(SAT)
        assert fee_low > info[x][0] + 3
        try:
            node.sendrawtransaction(self.build(node, coins_r, {dest: total - fee_low}, True))
            raise AssertionError("R was accepted: it would be the lowest in the pool")
        except JSONRPCException as e:
            # refused either way, for whichever rule sees it first: R pays less per byte than one it replaces, or it would be thrown out
            assert e.error["code"] == -22 and ("replacement-feerate-too-low" in e.error["message"] or "mempool-full" in e.error["message"]), e.error
        assert_equal(sorted(node.getrawmempool()), before)
        assert_equal(node.getmempoolinfo()["bytes"], bytes_before)

        self.log("R pays more per byte than all of them: it replaces X, the lowest of the rest goes to make room, the pool is within its limit")
        top = max(info[t][0] / info[t][1] for t in pool)
        fee_high = (top * Decimal("1.5") * size_r).quantize(SAT)
        rid = node.sendrawtransaction(self.build(node, coins_r, {dest: total - fee_high}, True))
        after = node.getrawmempool()
        assert rid in after and x not in after
        assert node.getmempoolinfo()["bytes"] <= CAP
        assert y not in after or len(after) < len(pool), "nothing was thrown out to make room"
        assert set(after) - {rid} <= set(before) - {x}


if __name__ == "__main__":
    RBFFullPoolTest().main()
