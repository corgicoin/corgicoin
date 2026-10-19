# Functional tests (regtest)

End-to-end tests that start real `corgicoind` processes on a private
**regtest** chain, drive them over JSON-RPC, and wire them together over P2P.
They complement the C++ unit tests (`test_corgicoin`), which test functions in
isolation. Python 3 standard library only, so there's nothing to install.

```bash
# all tests, 4 in parallel (finds build/corgicoind or build-test/corgicoind)
python3 test/functional/test_runner.py

# explicit binary, one test, keep datadirs for inspection
python3 test/functional/test_runner.py --corgicoind build/corgicoind wallet_send.py
python3 test/functional/feature_block_sync.py --corgicoind build/corgicoind --nocleanup
```

CI runs the suite on Linux and macOS after the unit tests.

## Regtest mode

`corgicoind -regtest` runs a private chain that cannot touch any public
network:

| | Regtest |
|---|---|
| Genesis | `0807d4f5…501f819e` (min difficulty, nonce 0) |
| Network magic | `fa c0 b6 da` |
| P2P / RPC port | 64666 / 64665 |
| Datadir | `<datadir>/regtest/` |
| Difficulty | always minimum (no retarget) |
| Addresses | testnet formats (`n…`/`2…`, `tcorg1…`) |

`generate <n> [address]` mines `n` blocks instantly and returns their hashes.
The CPU miner (`setgenerate true`) also runs without peers in regtest. Coinbase
outputs need 30 confirmations by consensus. The wallet waits 50 before counting
them in `getbalance`, so mine 50+ blocks before spending.

## Writing a test

```python
from test_framework import CorgiTestFramework, assert_equal

class MyTest(CorgiTestFramework):
    """One-line description (shown in --help)."""
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)
        n0.generate(10)
        self.sync_blocks()
        assert_equal(n1.getblockcount(), 10)

if __name__ == "__main__":
    MyTest().main()
```

Then add it to `TESTS` in `test_runner.py`. Each node gets free ports and its
own datadir under a temp dir. On failure the datadirs are kept and the tail of
each node's `debug.log` is printed.

| Helper | Does |
|---|---|
| `node.<rpc>(...)` | JSON-RPC call; errors raise `JSONRPCException` with `.code` |
| `connect_nodes(a, b)` | node a dials node b, waits for the handshake |
| `disconnect_nodes(a, b)` | drops every link between them |
| `sync_blocks()` / `sync_mempools()` | wait until all nodes agree |
| `wait_until(fn)` | poll a predicate with a timeout |
| `assert_raises_rpc_error(code, msg, fn, *args)` | expect a specific RPC error |

## Tests

| Test | Covers |
|---|---|
| `feature_regtest_basics.py` | chain identity, `generate`, coinbase maturity, spends, partner burn + `decodeburn`, restart |
| `wallet_send.py` | two-node payment relay, confirmation, spend-back, overspend |
| `feature_block_sync.py` | late-joiner catch-up, network split, reorg to the longer fork |
| `p2p_network_rpcs.py` | ping latency, traffic counters, bans, `addnode`, `disconnectnode` |
