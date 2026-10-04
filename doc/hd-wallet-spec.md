# HD (Hierarchical Deterministic) Wallet — Design Spec

Status: **draft** — design for review before implementation. This is a
wallet-only change (no consensus impact); it can ship in a normal release.
Staged like the consensus forks: primitives + tests first, then the wallet
integration, then the GUI, each independently reviewable.

## Motivation

CorgiCoin's wallet is pre-HD: `CWallet::GenerateNewKey()` makes an
independent random key (`CKey::MakeNewKey`) for every address, pre-filling a
keypool of 100. Two problems follow, both of which users hit this session:

- **Fragile backups.** `wallet.dat` must be re-backed-up after new keys are
  generated; an old backup silently misses funds received on newer
  addresses. (This is also why the explorer's rich list showed thousands of
  distinct mining-reward addresses.)
- **No portable seed.** There's no 12/24-word phrase to write down, restore
  on another device, or import into another wallet.

**HD wallets (BIP32/39/44)** derive every key deterministically from one
seed. A single backup — the seed, or its mnemonic — covers all past and
future keys forever. This is the defining modern wallet convention and the
largest one CorgiCoin lacks.

## Scope

In scope:
- BIP32 extended keys and child key derivation (the cryptographic core)
- BIP39 mnemonic ⇄ seed (the user-facing backup phrase)
- BIP44 derivation path for account/receive/change key organization
- An HD seed stored in the wallet (encrypted with the wallet passphrase when
  the wallet is encrypted), with keys derived on demand into the keypool
- Back-compat: existing random-key wallets keep working unchanged; HD and
  legacy keys coexist in one wallet
- RPCs and a GUI backup flow

Out of scope (later, if ever): descriptor wallets, multi-account UI,
hardware-wallet/xpub watch-only. These build naturally on this foundation.

## Cryptographic core (BIP32)

New `src/bip32.{h,cpp}` (and extended-key types, likely in `key.h`):

- **`CExtKey`** — a 32-byte private key + 32-byte chain code + depth / parent
  fingerprint / child number. `Derive(child, i)` implements CKDpriv:
  `I = HMAC-SHA512(key = chainCode, data = (hardened ? 0x00||ser256(k) :
  serP(point(k))) || ser32(i))`; child key = `(IL + k) mod n`, child chain
  code = `IR`. Hardened when `i >= 0x80000000`.
- **`CExtPubKey`** — 33-byte public key + chain code; `Derive` implements
  CKDpub (non-hardened only). Enables future xpub watch-only.
- **`CExtKey::SetSeed(seed)`** — master key: `I = HMAC-SHA512("Bitcoin seed",
  seed)`, master key = `IL`, master chain code = `IR`.

HMAC-SHA512 uses OpenSSL (already a dependency; `crypter` uses `EVP_sha512`).
`CKey::SetSecret` already accepts a 32-byte secret, so each derived child
slots straight into the existing key type. Extended keys serialize in the
standard BIP32 format (version bytes chosen for CorgiCoin — xprv/xpub
analogues; these only affect wallet import/export strings, not consensus).

## Mnemonic (BIP39)

New `src/bip39.{h,cpp}` + the 2048-word English wordlist:

- `GenerateMnemonic(entropy_bits=128|256)` → 12/24 words (entropy + SHA256
  checksum, mapped to the wordlist).
- `MnemonicToSeed(mnemonic, passphrase="")` → 64-byte seed via PBKDF2-HMAC-
  SHA512, 2048 iterations, salt `"mnemonic"+passphrase` (OpenSSL
  `PKCS5_PBKDF2_HMAC`).
- `CheckMnemonic(mnemonic)` validates words + checksum.

The 64-byte seed feeds `CExtKey::SetSeed`.

## Derivation path (BIP44)

`m / 44' / <coinType>' / <account>' / <change> / <index>`

- **coinType**: a fixed CorgiCoin value (propose **`0x80000063` → coin type
  99`'`**; must be confirmed and is ideally SLIP-44-registered, but it only
  affects this wallet's own derivation, so any stable value works).
- account 0', change ∈ {0 external, 1 internal}, index incrementing.
- The keypool becomes two derived ranges (receive and change) instead of
  random keys.

## Wallet integration (CWallet)

- **New `WalletFeature::FEATURE_HD`** (a value above the current
  `FEATURE_LATEST = 60000`, e.g. `130000`); `FEATURE_LATEST` bumped to match.
- **Stored in the wallet db** (`CWalletDB`): the HD seed (or its master
  `CExtKey`), the active account’s derivation counters for external/internal
  chains, and an HD seed id (a fingerprint) tagged on each derived key’s
  metadata so keys trace back to their seed.
- **`GenerateNewKey()`** gains an HD path: if the wallet has an HD seed,
  derive the next child at the current counter and increment it (persisted in
  the same db txn as the key), instead of `MakeNewKey`. Legacy wallets with
  no seed keep the random path.
- **Encryption**: when the wallet is encrypted, the HD seed is stored
  encrypted with the master key, exactly like private keys today
  (`CCryptoKeyStore`). Deriving new keys requires the wallet to be unlocked —
  same constraint as topping up the keypool today.
- **Back-compat / migration**:
  - Existing wallets load and operate unchanged (no seed ⇒ legacy behavior).
  - New wallets are created HD by default (generate a seed on first run).
  - `sethdseed`/`upgradetohd` converts an existing wallet: sets a seed and
    makes *future* keys HD; pre-existing random keys remain valid and
    spendable. (Full HD coverage of old keys is impossible — they aren’t
    derivable — so this is additive, matching Bitcoin Core’s behavior.)

## RPCs

- `sethdseed [newkeypool] [seed]` — set/replace the HD seed (seed as a BIP32
  xprv or a mnemonic); optionally flush and re-derive the keypool.
- `getwalletinfo` — add `hdseedid` and `hdmasterkeyid` fields.
- `dumpwallet` — include the HD seed / mnemonic so a text backup is complete.
- `getnewaddress` — unchanged interface; derives from the HD chain when HD.
- (Optional) `deriveaddresses` / `getdescriptorinfo`-lite for tooling.

## GUI

- **First-run / new-wallet backup dialog**: show the 12/24-word mnemonic once,
  require the user to confirm they’ve written it down, before funds can be
  received. This is the single biggest UX win — the "write down your seed
  phrase" flow every modern wallet has.
- A **"Show recovery phrase"** item (behind the passphrase prompt when
  encrypted) and a **"Restore from recovery phrase"** option on new-wallet
  creation.

## Testing

- **BIP32 vectors** (test vectors 1–5 from the BIP): master + child
  derivation, hardened/non-hardened, xprv/xpub round-trip.
- **BIP39 vectors** (the Trezor reference set): mnemonic ⇄ entropy ⇄ seed,
  checksum rejection.
- **BIP44 path** derivation determinism.
- **Wallet**: create HD wallet → derive N addresses → restore from the same
  seed in a fresh wallet → identical addresses; encrypt/unlock round-trip;
  legacy wallet still generates random keys; `sethdseed` on an existing
  wallet keeps old keys spendable.
- All crypto tests run headless in the existing Boost suite; the wallet
  round-trip can be exercised on a throwaway regtest/testnet datadir.

## Staging (independently shippable PRs)

1. **BIP32 primitives + tests** — `CExtKey`/`CExtPubKey`, CKD, seed; BIP32
   vectors. No wallet change, no risk to funds.
2. **BIP39 mnemonic + tests** — wordlist, generate/validate/to-seed; BIP39
   vectors. Still standalone.
3. **Wallet HD keypool** — seed storage (+ encryption), HD `GenerateNewKey`,
   counters, `FEATURE_HD`, `sethdseed`/`getwalletinfo`/`dumpwallet`, back-
   compat. The careful one; extensive wallet round-trip tests.
4. **GUI backup/restore flow** — mnemonic display, confirm-written, restore.

## Risks & non-goals

- **Fund safety is paramount.** HD touches key generation and the wallet
  file. Each stage lands behind the test suite; the wallet stage ships only
  after seed→address determinism and encrypt/unlock round-trips pass, and
  never removes or rewrites existing keys.
- **No consensus impact** — addresses derived by HD are ordinary P2PKH/P2SH
  destinations; the chain can’t tell HD from random keys.
- Old keys in an upgraded wallet are **not** retroactively covered by the
  seed; the recovery phrase protects funds received *after* the upgrade.
  Users keep their `wallet.dat` backup for pre-HD keys (documented clearly).

## References

- BIP32 (hierarchical deterministic wallets)
- BIP39 (mnemonic code for generating deterministic keys)
- BIP44 (multi-account hierarchy)
- SLIP-44 (registered coin types)
- `doc/lwma-retarget-spec.md`, `doc/auxpow-spec.md` — the spec-first,
  staged-rollout pattern this follows
