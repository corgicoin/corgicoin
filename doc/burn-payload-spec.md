# CorgiCoin Burn Payload Spec (v1)

> **Status:** Proof-of-concept. This spec governs on-chain burns that the
> off-chain bridge monitors. It is deliberately minimal — enough to test the
> end-to-end flow on Solana devnet with multiple partner tokens. Expect
> changes before any mainnet reward distribution.

## Purpose

Encode enough information in a CorgiCoin `OP_RETURN` burn output that an
off-chain bridge can:

1. Recognize the burn as a cross-chain reward request (not arbitrary data).
2. Identify which partner token should reward the burner.
3. Know which Solana address receives the reward.

## Layout

A total of **39 bytes**, placed as the data payload of a single `OP_RETURN`
output. Fits well under the 80-byte limit enforced by the daemon.

| Offset | Size | Field      | Value                                          |
|-------:|-----:|------------|------------------------------------------------|
| 0      | 3    | `magic`    | ASCII `"SOL"` (`0x53 0x4F 0x4C`)               |
| 3      | 4    | `partner`  | ASCII partner tag, e.g. `"CORG"` (`0x43 0x4F 0x52 0x47`) |
| 7      | 32   | `sol_dest` | Raw 32-byte Solana public key (pre-base58)     |

The partner tag is case-sensitive and must be exactly 4 printable ASCII
characters `[0x21, 0x7E]`. Shorter tags are not left-padded — pick a 4-char
tag when registering a partner.

The full scriptPubKey looks like:

```
OP_RETURN 0x27 <39 bytes of payload>
```

(`0x27` = 39, the standard push-data length byte for payloads of 1–75 bytes.)

## Why these choices

- **ASCII magic**: `"SOL"` is human-readable in raw tx dumps, makes
  debugging / block-explorer filters cheap, and is vanishingly unlikely to
  collide with arbitrary user-supplied burn data.
- **4-byte ASCII partner tag**: fixed-width parsing, no length prefix needed,
  human-readable. 4 chars also matches typical memecoin ticker length.
- **Raw 32-byte Solana pubkey**: base58 encoding of a Solana address is
  ~44 chars; the raw bytes are 32. We save 12+ bytes per burn and avoid
  shipping a base58 encoder into consensus-relevant code paths.

## Validation rules (bridge side)

A burn output is eligible for cross-chain rewards iff **all** of:

1. `scriptPubKey[0] == OP_RETURN` (`0x6a`).
2. Payload length is exactly 39 bytes.
3. `payload[0..3] == "SOL"`.
4. `payload[3..7]` is 4 printable ASCII characters.
5. That 4-byte tag appears in the bridge's `partners.json` registry.
6. `payload[7..39]` is a valid Solana ed25519 public key (the bridge verifies
   this off-chain; the daemon does not).

Any burn that fails these checks is ignored by the bridge. It still destroys
the CORG on-chain (that is the nature of `OP_RETURN`), but no Solana-side
reward is triggered.

## Producing a burn

The preferred path is the `burnforpartner` RPC:

```
burnforpartner <amount> <partner_tag> <solana_address>
```

The daemon validates the partner tag shape, base58-decodes the Solana
address (must decode to exactly 32 bytes), assembles the 39-byte payload,
and broadcasts the burn transaction. Raw-hex users can still call
`burncoin` directly and hand-assemble the bytes.

## Decoding a burn

The `decodeburn` RPC takes a hex-encoded scriptPubKey and returns either
the parsed payload or an error if it does not match the spec:

```json
{
  "magic": "SOL",
  "partner": "CORG",
  "sol_dest_hex": "…64 hex chars…",
  "sol_dest_base58": "…base58 Solana address…"
}
```

The bridge uses this to avoid re-implementing the parser in Python.

## Versioning

This document describes payload **v1**. There is no explicit version byte —
if the payload shape ever needs to change, a new magic string (e.g. `"SL2"`)
will be used and both the old and new will be accepted during any
transition window.
