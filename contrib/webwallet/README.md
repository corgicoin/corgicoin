# CorgiCoin Web Wallet (non-custodial)

A browser wallet that runs entirely client-side — the recovery phrase and
private keys are derived and held **in the browser** and never sent to any
server. It talks to the block explorer's JSON API only for public data
(balances, UTXOs) and to broadcast signed transactions.

It derives keys with **BIP32/39/44**, using the same path as the desktop
wallet (`m/44'/99'/0'/0/i`), so a given recovery phrase produces the **same
addresses** in both. This is verified on load by a crypto self-test (the
"crypto verified" badge) that checks the BIP39 seed vector, RIPEMD-160, and a
known CorgiCoin address against the daemon's output.

## Run

Served by the explorer (`contrib/explorer`): start the explorer, then open
`http://<host>:<port>/wallet/`. It uses the explorer's `/api/*` endpoints,
including `/api/address/<addr>/utxos` and `/api/broadcast`.

## Status

- **Watch-only + receive** — open from a phrase, scan addresses, show
  balances, display a receive address. *(this stage)*
- **Send** — client-side transaction signing + broadcast. *(next stage)*

## Files

- `index.html` — the UI (themed to match corgicoin.co / the explorer)
- `wallet.js` — BIP39/BIP32/44 derivation, CorgiCoin address encoding, API client
- `wordlist.js` — the official 2048-word BIP39 English list
- `vendor/` — audited third-party crypto, vendored for a self-contained page:
  - `noble-secp256k1.js` — @noble/secp256k1 1.7.1 (MIT, Paul Miller); the one
    Node `crypto` import is stubbed for the browser (it uses `self.crypto`)
  - `ripemd160.mjs` + `_sha2.mjs` / `utils.mjs` / `_assert.mjs` / `crypto.mjs`
    — @noble/hashes 1.3.3 (MIT) RIPEMD-160 and its deps
  - SHA-256/512, HMAC-SHA512 and PBKDF2 use the browser's native SubtleCrypto.

## Security notes

- Non-custodial by design: keys never leave the browser. Serve over HTTPS in
  production and treat the page's integrity as critical (it handles keys).
- The vendored crypto is pinned; re-verify checksums if you update it.
