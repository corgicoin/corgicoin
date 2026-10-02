# CorgiCoin [CORG, Ç]

![CorgiCoin](http://i.imgur.com/jx5vexy.png)

## About

CorgiCoin is a Scrypt-based Proof of Work cryptocurrency. Originally launched in 2014 as a fork of Dogecoin (itself from Litecoin/Bitcoin), CorgiCoin is back in 2026 with a fully modernized codebase and a vision to bridge PoW mining with the Solana memecoin ecosystem through a proof-of-burn token bridge and partner program.

**Version 4.3.0.0** — fully modernized, network live, with multipartner cross-chain burn bridge and modern per-block difficulty retargeting:
- C++17 codebase (modernized from C++03)
- OpenSSL 3.x, Qt 5/6, nlohmann/json, std::filesystem
- Proper logging framework with categories
- On-chain burn mechanism: `burncoin` (raw) + `burnforpartner` / `decodeburn` (structured, multipartner) for Solana cross-chain integration
- LWMA per-block difficulty retarget (hard fork at block 34,000 — see `doc/lwma-retarget-spec.md`)
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

### In Progress
- [ ] Pump.fun partner token integration

### Planned
- [ ] Block explorer
- [ ] Wallet UX improvements
- [ ] P2P encryption (BIP151)

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

## License

CorgiCoin is released under the MIT/X11 license. See [COPYING](COPYING) for details.
