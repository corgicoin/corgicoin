# CorgiCoin Burn Bridge (PoC)

Cross-chain burn bridge that watches `corgicoind` for burn transactions
matching the spec in [`doc/burn-payload-spec.md`](../../doc/burn-payload-spec.md)
and dispatches SPL token rewards on Solana from per-partner treasuries.

> **Devnet only.** This is a proof-of-concept. Do not point the treasury
> keypair(s) at mainnet until we replace it with something more paranoid
> (Solana program + multisig, minimum).

## How it works

```
corgicoind  ──JSON-RPC──▶  bridge.py  ──solana-py──▶  Solana devnet
                              │
                           state.json   (tip height + processed txids)
```

Per tick, the bridge:

1. Polls `getblockcount` and walks every block since `state.last_height`,
   waiting `--confirmations` blocks (default 10) for reorg safety.
2. For each tx, calls `decodeburn <scriptPubKey_hex>` on every output —
   the daemon is the authoritative parser, the bridge does not re-implement
   payload parsing.
3. Looks up the decoded partner tag in `partners.json`. Unknown partners
   are logged and marked `skipped_unknown_partner`; the burn still destroys
   the CORG on-chain, it just doesn't trigger a reward.
4. Sends an SPL `transfer_checked` from that partner's treasury ATA to the
   burner's Solana address, creating the destination ATA if needed.
5. Appends the result to `state.json`. The same CORG txid will never be
   processed twice.

## Install

```bash
cd contrib/bridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configure

### 1. Partner registry (`partners.json`)

```json
{
  "CORG": {
    "token_mint": "<devnet SPL mint address>",
    "decimals": 6,
    "reward_ratio": 1.0,
    "treasury_keypair": "corg-treasury.json"
  }
}
```

- `token_mint` — SPL mint address on devnet.
- `decimals` — must match the mint's decimals.
- `reward_ratio` — multiplier: 1 CORG burned = `reward_ratio` partner tokens.
  Use `1.0` until you have real tokenomics.
- `treasury_keypair` — filename under `keys/`, standard Solana JSON-array
  secret key format (the one `solana-keygen new` produces).

Add a new partner = add a JSON entry + drop its keypair in `keys/`.

### 2. Devnet treasury setup

```bash
# Install the solana CLI, then:
solana config set --url https://api.devnet.solana.com

# Generate a treasury keypair (moves to contrib/bridge/keys/)
solana-keygen new --no-bip39-passphrase -o keys/corg-treasury.json
solana airdrop 2 --keypair keys/corg-treasury.json

# Create an SPL mint (note the mint address it prints)
spl-token create-token --decimals 6 --fee-payer keys/corg-treasury.json \
  --mint-authority keys/corg-treasury.json

# Create the treasury's ATA for that mint and fund it
spl-token create-account <MINT> --fee-payer keys/corg-treasury.json
spl-token mint <MINT> 1000000000 --fee-payer keys/corg-treasury.json \
  --mint-authority keys/corg-treasury.json

# Paste the <MINT> value into partners.json as token_mint
```

### 3. corgicoind credentials

The bridge reads the daemon RPC creds from the environment:

```bash
export CORGI_RPC_URL="http://127.0.0.1:62555"   # default
export CORGI_RPC_USER="<from corgicoin.conf>"
export CORGI_RPC_PASSWORD="<from corgicoin.conf>"
export SOLANA_RPC_URL="https://api.devnet.solana.com"   # default
```

## Run

```bash
# Single tick (good for smoke testing)
python bridge.py --once

# Long-running loop, polling every 30s
python bridge.py
```

Run under systemd / launchd / `while true; sleep 30; done` as you prefer.
The bridge is safe to stop and restart at any time — all state lives in
`state.json`.

## Smoke test

From a wallet with CORG, with the bridge running:

```bash
corgicoin-cli burnforpartner 1.0 CORG <your-solana-devnet-address>
```

After ~10 blocks + one poll interval, the bridge logs:

```
dispatched 1.0 CORG -> <your-solana-address> (corg tx ..., sol sig ...)
```

Verify on a Solana devnet explorer using the returned signature.

## Operational notes

- **Idempotency** is on CORG txid. If the bridge crashes mid-dispatch, a
  retry may produce a duplicate Solana transfer. The current PoC does not
  detect this — any future hardening should move the dedupe check onto the
  Solana side (e.g. a program that records processed CORG txids).
- **Confirmation depth** defaults to 10. CorgiCoin's coinbase maturity is
  30 blocks and reorgs past that are vanishingly rare, but 10 is already
  much deeper than realistic chain churn in PoC conditions.
- **Treasury drain** is the bridge's only failure mode worth caring about
  right now. Monitor the treasury ATA balance out-of-band.
- **Unknown partners** are logged and skipped. Useful if someone burns with
  a partner tag we haven't registered yet — we can backfill later by
  looking at `state.json`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Tests are pure-mock — they don't need corgicoind or Solana RPC.
