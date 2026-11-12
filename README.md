# CorgiCoin [CORG, Ç]

![CorgiCoin](http://i.imgur.com/jx5vexy.png)

## About

CorgiCoin is a Scrypt-based Proof of Work cryptocurrency. Originally launched in 2014 as a fork of Dogecoin (itself from Litecoin/Bitcoin), CorgiCoin is back in 2026 with a fully modernized codebase and a vision to bridge PoW mining with the Solana memecoin ecosystem through a proof-of-burn token bridge and partner program.

**Version 4.8.0.0** — fully modernized, network live, with a multipartner cross-chain burn bridge, LWMA difficulty, AuxPoW merged mining (pool-ready `getauxblock`), an HD (seed-phrase) wallet with Coin Control, and a non-custodial web wallet:
- C++17 codebase (modernized from C++03)
- OpenSSL 3.x, Qt 5/6, nlohmann/json, std::filesystem
- Proper logging framework with categories
- On-chain burn mechanism: `burncoin` (raw) + `burnforpartner` / `decodeburn` (structured, multipartner) for Solana cross-chain integration
- LWMA per-block difficulty retarget (hard fork at block 34,000 — see `doc/lwma-retarget-spec.md`)
- AuxPoW merged mining (hard fork at block 50,000 — see `doc/auxpow-spec.md`)
- Bech32m addresses (`corg1…` / `tcorg1…`) alongside legacy base58
- HD (BIP32/39) wallet with a seed-phrase backup (see `doc/hd-wallet-spec.md`)
- Qt wallet Coin Control (pick inputs, lock coins, custom change) and key import/export
- Non-custodial web wallet (`contrib/webwallet/`): keys stay in the browser, same addresses as the desktop wallet
- Modern P2P diagnostics and control: ping latency, traffic counters, `setban`, runtime `addnode`
- Genesis block mined, mainnet running with seed nodes
- Protocol version 70001

## Chain Specifications

| Parameter | Value |
|-----------|-------|
| **Algorithm** | Scrypt (1024, 1, 1, 256) |
| **Block Time** | 1 minute |
| **Difficulty Retarget** | LWMA per-block from height 34,000 (every 4 hours before) |
| **Max Supply** | 100,000,000,000 CORG |
| **Coinbase Maturity** | 30 blocks |
| **P2P Port** | 62556 |
| **RPC Port** | 62555 |
| **Testnet P2P Port** | 64556 |

### Block Rewards

Random block rewards seeded from previous block hash:

| Block Height | Max Reward |
|---|---|
| 1 - 100,000 | 1,000,000 CORG |
| 100,001 - 200,000 | 500,000 CORG |
| 200,001 - 300,000 | 250,000 CORG |
| 300,001 - 400,000 | 125,000 CORG |
| 400,001 - 500,000 | 62,500 CORG |
| 500,001 - 600,000 | 31,250 CORG |
| 600,001+ | 10,000 CORG (flat) |

## Getting Started

Prebuilt binaries for Linux, macOS, and Windows are on the
[Releases page](https://github.com/corgicoin/corgicoin/releases) — verify
downloads against the attached `SHA256SUMS`.

Want to mine? Network hashrate is low right now, so CPU mining finds
blocks. See **[doc/mining.md](doc/mining.md)** for a five-minute setup
guide, and [contrib/corgicoin.conf.example](contrib/corgicoin.conf.example)
for an annotated config.

Modernizing another 2014-era Scrypt coin? CorgiCoin's whole 2026 overhaul is
written up as a reusable playbook:
**[doc/modernizing-scrypt-coins.md](doc/modernizing-scrypt-coins.md)**.

## Building

### Requirements

- **C++17 compiler**: GCC 9+, Clang 10+, or MSVC 2019+
- **OpenSSL** 1.1.0+ (3.x recommended)
- **Boost** 1.65+
- **Berkeley DB** 5.3+
- **Qt 5.15+** (for GUI wallet, optional)
- **CMake** 3.10+

### Quick Start

```bash
# Install dependencies (Ubuntu/Debian)
sudo apt-get install build-essential libboost-all-dev libssl-dev \
  libdb++-dev libminiupnpc-dev cmake

# Build daemon
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF
make -j$(nproc)

# Build with Qt wallet
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=ON
make -j$(nproc)
```

#### macOS

```bash
brew install boost openssl@3 berkeley-db@5 miniupnpc cmake qt@5

mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3) \
  -DBerkeleyDB_ROOT=$(brew --prefix berkeley-db@5)
make -j$(sysctl -n hw.logicalcpu)
```

See [BUILD.cmake.md](BUILD.cmake.md) for detailed instructions and IDE integration.

### Configuration

```conf
rpcuser=your_secure_username
rpcpassword=your_secure_random_password
rpcport=62555

# Seed nodes (determining network config)
# addnode=<seed-node-ip>
```

## Version History

### Unreleased
- **macOS Qt wallet**: releases now include `corgicoin-qt-<version>-macos-arm64.zip`, a self-contained `CorgiCoin-Qt.app`. The macOS daemon download also bundles its libraries in `lib/`; until now it only ran on Macs with the same Homebrew packages installed. Both are signed ad hoc, not notarized, so the first launch needs **Open Anyway** (see `doc/macos-first-launch.md`)
- **Pool and integration RPCs** (thanks @colneech-dev):
  - `submitblock` (BIP 22, #90)
  - `gettxout` (#89)
  - `testmempoolaccept`, a dry run that reports why a transaction would be refused (#91)
  - `prioritisetransaction` (#92)
  - `abandontransaction`, which gives up on an unconfirmed wallet transaction and its wallet descendants and frees their coins (#93)
- **ZeroMQ notifications** (thanks @colneech-dev, #95): `-zmqpubhashblock`, `-zmqpubrawblock`, `-zmqpubhashtx` and `-zmqpubrawtx`. Opt-in at build time (`-DUSE_ZMQ=ON`); release binaries leave it out. See `doc/mining.md`
- **Low-S signatures** (thanks @colneech-dev, #94): the wallet now always signs with a low S value, so a third party can't re-encode its transactions under a different txid. A new `-standardsigs=1` option makes the node relay only strict-DER, low-S signatures. It is **off by default** for now, because older wallets produce a high S on about half of their inputs. It is relay policy only, and blocks are unaffected
- **RPC credentials are compared in constant time** (thanks @colneech-dev, #87)
- **`importprivkey` rejects keys outside 1…n−1** (zero, the curve order, or larger) instead of importing a key that isn't valid (thanks @colneech-dev, #88)
- **`walletpassphrasechange` keeps the old passphrase working** if the new master key can't be written. Previously, memory and disk could end up disagreeing. A database file that fails to open is now handled instead of leaving a dead handle behind (thanks @colneech-dev, #86)

### v4.8.0.0 — HD Wallet Fixes, Wallet Compatibility + Pool-Ready Merged Mining

> **Required upgrade for HD wallets.** If you ran `sethdseed` (or set a recovery phrase in the GUI) on v4.5–v4.7, coins received on HD addresses created since the node last started could not be spent, and `dumpprivkey` exported those keys in the wrong (uncompressed) form (a restart reloaded the keys correctly). Upgrading fixes both, with the same addresses and no rescan. If you also encrypted such a wallet, v4.5–v4.7 left the HD private keys in `wallet.dat` **unencrypted** and the wallet then refused to load ("Wallet corrupted"). This release loads it, and the first `walletpassphrase` encrypts those keys and deletes the plaintext records. The database may still hold old copies in free space, so if anyone else may have had access to that file, move the funds to a new wallet.

- **HD wallet keys keep their compression flag** (thanks @colneech-dev, #75): copying a `CKey` dropped the flag (a bug in the 2014 code base that HD derivation was the first to hit). Also fixed: a NULL dereference on public-key-only keys, a leaked signature on failed signing, a key left marked as set after a failed signature recovery, and empty inputs. New `wallet_hd_encryption.py`
- **Recovery for HD wallets broken by encryption**: plaintext keys found next to encrypted ones are recognised while locked and encrypted on the next unlock, instead of the wallet failing to load
- **Never continue with an unfilled random buffer** (thanks @colneech-dev, #76): every `RAND_bytes` call is checked. Recovery-phrase generation and wallet encryption fail cleanly, everything else stops the node. A failed generator used to leave all-zero entropy, which is the public "abandon … about" phrase
- **No more indexing empty vectors** in hashing, base58/32/64 decoding and the crypter (thanks @colneech-dev, #77). The results are unchanged and consensus-neutral (the hashes of empty input are pinned in tests)
- **Bounded orphan-block pool** (thanks @colneech-dev, #82): at most 750 blocks / 32 MB, with random eviction. Mainnet's only checkpoint is genesis, so a peer could otherwise fill memory with minimum-difficulty orphans
- **Tests and CI** (thanks @colneech-dev): `rpc_http_auth.py` (malformed `Authorization` headers get 401, #80), `feature_cross_binary.py` (two builds interoperate, `--alt-corgicoind`, #78), a sanitizer CI job running the unit tests under ASan/UBSan/libstdc++ assertions (#81)
- **Encrypted wallets from older clients unlock again**: wallet passphrase derivation method 0 is Bitcoin's `EVP_BytesToKey` (SHA-512) again on every build. Since v4.2, builds against OpenSSL 3 (all release binaries) had silently switched it to PBKDF2 while still recording method 0, so a wallet encrypted by the original CorgiCoin client, or by any build against OpenSSL 1.x, was refused with "passphrase incorrect" even with the right passphrase. Wallets encrypted by v4.2–v4.7 still unlock (both derivations are tried), and `walletpassphrasechange` (the same passphrase is fine) re-encrypts them with the standard one. Note: v4.7 and earlier cannot unlock a wallet encrypted or re-keyed by this release (found via @colneech-dev's crypter tests, #79)
- **`dumpprivkey` on a locked wallet** now asks for the passphrase (error -13) instead of claiming the key is not known
- **Chain recovery**: `invalidateblock <hash>` rolls the node back and makes it refuse any chain through that block (persisted across restarts); `reconsiderblock <hash>` undoes it; `getchaintips` reports such tips as `invalid` (thanks @colneech-dev, #71)
- **Diagnostics**: `getmempoolinfo` (pool size, bytes, min relay fee) and `verifychain [checklevel] [numblocks]` (the startup block checks, run on the live node, read-only) (thanks @colneech-dev, #72)
- **`getnodeaddresses [count]`**: addresses known to the address manager (`peers.dat`), connected or not (thanks @colneech-dev, #69)
- **`getauxblock`**: the Namecoin/Dogecoin single-call merged-mining RPC many pool stacks use (no arguments: work paying a fresh wallet key; `<hash> <auxpow>`: submit). Work objects now also carry `target` in display byte order next to `_target`. `createauxblock`/`getauxblock` refuse work before the AuxPoW fork, and `submitauxblock` rejects malformed hashes and proofs with trailing data; accepted blocks are freed instead of lingering until the tip moves
- **Merged-mining test suite** (`feature_auxpow.py`, with a reusable pool-side proof builder `auxpow_builder.py`): multi-chain proofs under a multi-transaction parent, the legacy no-magic commitment, one rejection per AuxPoW consensus rule (each checked against its exact error), insufficient parent work, stale and expired work, and `getauxblock`
- **`invalidateblock` follow-ups**: a node stopped between saving the invalidation and rolling back now finishes the rollback at startup; failing to switch to another known branch after a successful rollback is logged instead of reported as an error
- **Tests**: new `rpc_invalidateblock.py` and `rpc_mempool_verify.py`; fixed a flaky added-node re-dial step in `p2p_network_rpcs.py` (#70)

### v4.7.0.0 — Wallet UX + Merged-Mining Fixes

> **Required upgrade for merged mining.** Pools merge-mining CorgiCoin and every node that should follow merged-mined blocks need v4.7.0.0. Older nodes cannot validate a transaction that spends a merged-mined block reward and would reject the block containing it. No `-reindex` is needed: before this release no merged-mined block could be accepted at all.

- **Merged mining works end to end** (thanks @colneech-dev, PR #67): `createauxblock` now fills in the coinbase script (previously empty, so every merged-mined block failed the "coinbase script size" check and `submitauxblock` always returned false), and transactions in AuxPoW blocks are indexed at their correct position on disk (the AuxPoW proof was not counted, so `getrawtransaction` could not find them and their outputs could not be spent). New `rpc_createauxblock.py` functional test plays a merged-mining pool on regtest: request work, commit it in a parent coinbase, solve a parent Scrypt header, submit, relay, and spend the matured reward
- **Persistent bans** (`banlist.dat`): manual `setban` bans and misbehavior bans now survive a restart. Same checksummed, network-tagged, write-then-rename format as `peers.dat`; expired bans are dropped on load
- **Ping timeout**: a peer that leaves a ping unanswered for 20 minutes is disconnected, freeing its slot (`-pingtimeout=<seconds>`). Pre-BIP31 peers are unaffected
- **Coin control**: `lockunspent <unlock> [outputs]` / `listlockunspent` set outputs aside so coin selection won't spend them (memory-only, cleared on restart, as in Bitcoin Core)
- **Wallet export/import**: `dumpwallet <file>` writes every key with its label or role (change / unused keypool) in Bitcoin Core's text format, refusing to overwrite an existing file; `importwallet <file>` restores the keys and labels and rescans
- **`getrawchangeaddress`**: a fresh change address for raw-transaction workflows
- **Qt wallet Coin Control**: a "Coin Control" box on the Send tab. "Inputs..." opens a list of your coins (amount, label, address, date, confirmations) to tick exactly which ones a payment spends; right-click to lock/unlock coins or copy details. Optional custom change address (warns if it isn't in this wallet). With nothing ticked, coins are chosen automatically as before
- **Qt wallet key import/export**: File → "Import Private Key...", "Import Keys from File..." and "Export All Keys..." (the GUI versions of `importprivkey`, `importwallet` and `dumpwallet`, sharing one implementation). Export warns that the file is unencrypted; imports unlock the wallet if needed and rescan. `importprivkey` of a key the wallet already has now just updates its label instead of rescanning
- **Functional tests**: a minimal Python P2P peer (`test/functional/mininode.py`) for protocol-level tests; new ping-timeout test and a ban-persistence-across-restart check

### v4.6.0.0 — Web Wallet + P2P Modernization + Regtest
- **Non-custodial web wallet** (`contrib/webwallet/`, served by the explorer at `/wallet/`): recovery phrase and keys are derived and held in the browser and never sent to a server. Same BIP44 path as the desktop wallet (`m/44'/99'/0'/0/i`), so one phrase gives the same addresses in both. Receive, balances, and **send**: transactions are built and signed client-side (legacy P2PKH, SIGHASH_ALL) and broadcast through the explorer. Verified end-to-end on testnet against full daemon validation
- **Explorer wallet API**: `GET /api/address/<addr>/utxos`, `POST /api/broadcast`
- **Peer latency (BIP31)**: nonce'd pings every 2 minutes with pong matching; `getpeerinfo` now reports `pingtime`, `minping`, `pingwait`, plus per-peer `bytessent`/`bytesrecv` and `addrlocal`. New `ping` RPC forces an immediate round.
- **`getnettotals`**: total bytes sent/received since startup
- **Ban management**: `setban <ip> add|remove [bantime] [absolute]`, `listbanned`, `clearbanned` (manual bans disconnect matching peers immediately)
- **Runtime peer management**: `addnode <node> add|remove|onetry`, `getaddednodeinfo [node]`, `disconnectnode <address>`. The `-addnode` thread now re-reads its list every pass, so RPC-added nodes are dialed and kept connected
- **Regtest mode** (`-regtest`): a private chain with its own genesis, network magic, ports (64666/64665) and datadir, minimum-difficulty blocks, and a `generate <n> [address]` RPC that mines instantly
- **Functional test suite** (`test/functional/`): Python harness that runs real multi-node regtest networks over RPC and P2P; covers mining, wallet sends, burns, block sync, reorgs and the network RPCs. Runs in CI on Linux and macOS
- **Sync fix**: a node now requests blocks from any newly connected peer advertising a taller chain. Previously only the first peer was asked, so a node that rejoined a longer fork after a split stayed behind until the next block was mined (found by the new reorg test)
- **`getbestblockhash`** RPC
- No consensus or wire-format changes; RPC error codes match Bitcoin Core

### v4.5.0.0 — HD Wallet + Modern RPCs
- **HD (hierarchical deterministic) wallet** (BIP32/39/44): all keys derive from a single seed, with a 12/24-word recovery phrase that backs up the whole wallet. Works on encrypted wallets (seed encrypted with the wallet passphrase); legacy wallets keep working unchanged. `sethdseed` RPC + a Settings → "Set up / Restore HD Seed" / "Show Recovery Phrase" GUI flow. Spec: `doc/hd-wallet-spec.md`
- **Modern info RPCs**: `getblockchaininfo` (with LWMA/AuxPoW fork status), `getblockheader`, `getnetworkinfo`, `getwalletinfo`, `getchaintips`, `uptime`
- **Analytics RPCs**: `getblockstats`, `getchaintxstats`
- **`-mineraddress`**: pay all mined block rewards to one address instead of a fresh keypool key per block
- **Qt wallet**: visible "Up to date" sync-status label; bech32 (`corg1…`) in the GUI (copy action + Receive QR option)
- **Block explorer** (`contrib/explorer/`): JSON API, difficulty/block-time charts, rich list, network/peers page, fork-status cards, themed to match corgicoin.co
- **`boost::date_time` → `std::chrono`**; CI moved to the `macos-15` runner

### v4.4.0.0 — AuxPoW Merged Mining Hard Fork
- AuxPoW (merged mining) consensus: a high-hashrate Scrypt pool (Litecoin/Dogecoin) can secure CorgiCoin at near-zero marginal cost, closing the 51%-attack exposure of a low-hashrate chain — hard fork at block **50,000 mainnet / 200 testnet**, chain ID `0x00C6` (spec: `doc/auxpow-spec.md`)
- `CPureBlockHeader` / `CAuxPow` types; non-merged blocks serialize byte-identically (no reindex); solo CPU mining preserved post-fork
- `createauxblock` / `submitauxblock` RPCs (standard Dogecoin/Namecoin pool interface)
- Bech32m address encoding (`corg1…` / `tcorg1…`) accepted everywhere addresses are parsed
- `boost::variant` → `std::variant` for `CTxDestination`; `boost::algorithm::string` / `lexical_cast` replaced with std helpers
- Block explorer with burn auditing (`contrib/explorer/`)
- Fork rehearsed end-to-end on testnet; 11 AuxPoW + 8 bech32 unit tests

### v4.3.0.0 — LWMA Difficulty Hard Fork
- LWMA-1 per-block difficulty retarget (90-block window), activating at height 34,000 mainnet / 100 testnet — fixes the hash-and-run stall failure mode of the 4-hour interval retarget (spec: `doc/lwma-retarget-spec.md`)
- Future time limit tightened from 2 hours to 300 seconds post-fork
- Fixed latent testnet bug: pow limit was stricter than testnet genesis bits, deadlocking testnet mining at height 1
- Fork rehearsed end-to-end on a fresh testnet: two nodes mined through activation with no consensus split
- Tag-triggered release pipeline: Linux/macOS/Windows binaries + Qt wallet bundle + SHA256SUMS published automatically on version tags
- First public GitHub release shipped (v4.2.0.0 binaries), mining guide (`doc/mining.md`), seed node upgrade runbook

### v4.2.0.0 — Multipartner Burn Bridge
- `burnforpartner <amount> <partner_tag> <solana_address>` RPC: structured, multipartner burns
- `decodeburn <scriptPubKey_hex>` RPC: parses bridge burn payloads off-chain
- 39-byte OP_RETURN payload spec (`doc/burn-payload-spec.md`): `"SOL"` magic + 4-byte partner tag + 32-byte Solana pubkey
- 8 new unit tests covering the payload encode/decode round-trip (suite now ~87 tests)
- Wallet builds now available for macOS, Windows, and Linux
- Bridge PoC (`contrib/bridge/bridge.py`): first end-to-end devnet dispatch — CORG burn → Solana SPL mint

### v4.1.0.0 — Network Launch + Cross-Chain Burns
- Genesis block mined, mainnet live with seed nodes
- On-chain burn mechanism: `burncoin` RPC with OP_RETURN data embedding
- TX_NULL_DATA script type for provably unspendable burn outputs
- Cross-platform consensus fix (portable random number generation for block rewards)
- Logging framework: LogPrintf/LogError/LogPrint with categories (replaced 400+ printfs)
- Qt wallet: fixed mining page, tab navigation, signal/slot compatibility
- CreateThread return type fix (was causing false "could not start node" errors)
- Version bump to 4.1.0.0

### v4.0.0.0 — 2026 Relaunch
- C++17 standard across all build systems
- OpenSSL 3.x migration complete (1.0.x dropped)
- Protocol version 70001 (breaks compatibility with 1.x nodes)
- `boost::filesystem` → `std::filesystem`, `json_spirit` → nlohmann/json
- Qt 6 support (Qt 4 dropped, Qt 5/6 dual compatibility)
- `boost::tuple/assign/random/type_traits` → C++17 stdlib equivalents
- GitHub Actions CI/CD with tests on Linux and macOS
- 79 unit tests, full rebranding, dead code cleanup
- Client identity renamed from "Satoshi" to "CorgiCoin"

### v1.4.1.42 - v1.4.1.67 — Modernization Era (2025)
- 16 releases, ~645+ individual modernizations
- C++11/14 migration: nullptr, smart pointers, range-based for, enum classes

### v1.0 - v1.4.1.41 — Original Era (2014)
- Initial Dogecoin fork with Scrypt PoW
- Original network launch and mining

## Roadmap

### Completed
- [x] C++17 codebase upgrade
- [x] OpenSSL 3.x full migration
- [x] Protocol version bump (v70001)
- [x] CI/CD pipeline (GitHub Actions) with test suite
- [x] Replace `boost::filesystem` with `std::filesystem`
- [x] Replace `json_spirit` with nlohmann/json
- [x] Full asset rebranding (icons, installer, share/ directory)
- [x] Unit test suite (scrypt, addresses, block rewards, serialization, burn payloads, etc.)
- [x] Qt 6 support (Qt 4 dropped, Qt 5/6 dual support)
- [x] Logging framework with categories
- [x] Genesis block mined (mainnet + testnet)
- [x] Seed node deployment (2 nodes live)
- [x] On-chain burn mechanism (`burncoin` RPC + OP_RETURN)
- [x] Windows cross-compiled wallet build
- [x] Multipartner burn payload spec + `burnforpartner` / `decodeburn` RPCs
- [x] Burn bridge oracle PoC: first end-to-end devnet dispatch (CORG burn → Solana SPL mint)
- [x] Bridge hardening: at-most-once dispatch idempotency + Python test suite
- [x] Tag-triggered release pipeline with binaries for all platforms
- [x] LWMA per-block difficulty retarget (v4.3 hard fork)
- [x] Bech32m address encoding (`corg1…` / `tcorg1…`, accepted everywhere addresses are parsed)
- [x] Block explorer with burn auditing (`contrib/explorer/` — indexes the chain over RPC, decodes bridge burns)
- [x] AuxPoW merged mining (v4.4 hard fork at block 50,000 — see `doc/auxpow-spec.md`)
- [x] Modern P2P/network RPCs: BIP31 ping latency, traffic counters, `setban`/`listbanned`, runtime `addnode`/`disconnectnode`
- [x] Regtest mode + Python functional test suite (multi-node, runs in CI)
- [x] Persistent ban list (`banlist.dat`) + ping-timeout disconnects
- [x] Wallet coin control + dump/import RPCs (`lockunspent`, `dumpwallet`/`importwallet`, `getrawchangeaddress`)
- [x] Boost reduced to essentials (`std::variant`, `std::chrono`, std string helpers; only asio/interprocess/program_options/signals2 remain)

### In Progress
- [ ] Pump.fun partner token integration

### Planned
- [x] Wallet UX improvements (Coin Control, key import/export in the GUI)
- [ ] Encrypted P2P transport (BIP324; BIP151 was withdrawn and superseded)
- [ ] Headers-first block sync

### Pump.fun / Solana Integration (Future)

CorgiCoin is exploring a cross-chain integration with the Solana memecoin ecosystem. Rather than tying to a single token, CORG aims to be a **PoW burn layer** that can partner with multiple pump.fun community tokens.

- [ ] **Multi-Token Burn Bridge** — burn CORG on-chain to boost partnered Solana tokens (rewards, airdrops, LP funding)
- [ ] **Partner Token Program** — framework for pump.fun communities to integrate with CorgiCoin mining
- [ ] **Cross-Chain Mining Rewards** — portion of block rewards fund Solana-side liquidity for partner tokens
- [ ] **Burn-to-Mint NFTs** — burn CORG to mint collectible NFTs on Solana with rarity tiers
- [ ] **Bridge Oracle Infrastructure** — trustless verification of CORG burns for cross-chain rewards

See [ROADMAP-PUMPFUN.md](ROADMAP-PUMPFUN.md) for the full technical spec.

## Contributing

1. Use C++17 features where appropriate
2. Follow existing code style
3. Ensure CI passes before submitting PRs
4. Test on both Linux and macOS
5. Add a functional test for RPC or P2P behavior (see [test/functional/README.md](test/functional/README.md))

## License

CorgiCoin is released under the MIT/X11 license. See [COPYING](COPYING) for details.
