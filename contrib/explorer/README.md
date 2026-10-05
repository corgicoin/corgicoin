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

- **Rich List** (`/richlist`): top addresses by unspent balance.
- **Network** (`/network`): live node info, peers, and mempool via RPC.

## JSON API

Machine-readable endpoints for tools and bots (amounts in satoshis):

- `GET /api/chaininfo` — tip height, difficulty, indexed tx count, total
  burned, and live fork status (from the node's `getblockchaininfo`)
- `GET /api/block/<height|hash>` — block record plus its transaction list
- `GET /api/tx/<txid>` — transaction with its outputs and any decoded burns
- `GET /api/address/<address>` — balance, total received, and outputs
- `GET /api/burns` — recent burns (partner + Solana destination) and the total

Each returns JSON; unknown ids return `{"error": …}` with HTTP 404.

### Wallet backend

Endpoints for a non-custodial browser wallet (keys stay client-side):

- `GET /api/address/<addr>/utxos` — unspent outputs with `scriptPubKey`,
  `value` (satoshis), and `confirmations` — everything needed to build and
  sign a spend. Capped at 500 UTXOs per request.
- `POST /api/broadcast` — relay a signed raw transaction. Body
  `{"hex": "<rawtx>"}` (or the raw hex as the request body); returns
  `{"txid": …}` or `{"error": …}` with HTTP 400.

If you expose these publicly, rate-limit `/api/broadcast` (it reaches the
node's mempool).

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
