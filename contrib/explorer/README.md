# CorgiCoin Block Explorer

Single-file block explorer in the spirit of `contrib/bridge`: an indexer
thread walks the chain over RPC into SQLite, and a small Flask UI serves
block / transaction / address pages. The daemon has no address index RPC,
so the explorer maintains its own.

The **Burns** page decodes every OP_RETURN burn via the `decodeburn` RPC —
partner tag, Solana destination, amount — making the cross-chain bridge
publicly auditable (every Solana-side reward links back to a CORG burn tx).

## Run

```bash
cd contrib/explorer
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python explorer.py            # reads ~/.corgicoin/corgicoin.conf
# open http://127.0.0.1:8080
```

Options: `--conf <path>` (corgicoin.conf with rpcuser/rpcpassword),
`--db <sqlite path>`, `--bind`, `--port`.

Initial index of the current chain (~31k blocks) takes a few minutes; the
indexer then follows the tip, polling every 10 s, and unwinds reorgs by
re-checking the stored tip hash against the chain.

## Notes

- Balances are computed from the output index (sum of unspent outputs per
  address) — consistent with the node once the indexer reaches the tip.
- Search accepts a height, block hash, txid, or address (base58 or bech32
  `corg1…`; bech32 lookups resolve through the node's `validateaddress`).
- This is operator tooling, not a hardened public service. If you expose
  it publicly, put it behind a reverse proxy and rate-limit.
- Themed to match corgicoin.co (forest green, Bungee/Inter from Google
  Fonts). The fonts load over the network; offline, the page falls back to
  system fonts and stays fully usable.
- The home page shows LWMA/AuxPoW fork activation status via the node's
  `getblockchaininfo` (v4.4+); against older nodes those cards are omitted.
