# CorgiCoin [CORG, Ç]

![CorgiCoin](http://i.imgur.com/jx5vexy.png)

## About

CorgiCoin is a Scrypt-based Proof of Work cryptocurrency. Originally launched in 2014 as a fork of Dogecoin (itself from Litecoin/Bitcoin), CorgiCoin is back in 2026 with a fully modernized codebase.

**Version 4.0.0.0** represents a complete relaunch with:
- C++17 codebase (modernized from C++03)
- OpenSSL 3.x support (1.0.x dropped)
- Protocol version 70001 (incompatible with legacy 1.x nodes)
- CI/CD pipeline with actions

## Chain Specifications

| Parameter | Value |
|-----------|-------|
| **Algorithm** | Scrypt (1024, 1, 1, 256) |
| **Block Time** | 1 minute |
| **Difficulty Retarget** | Every 4 hours (240 blocks) |
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

### v4.0.0.0 — 2026 Relaunch
- C++17 standard across all build systems
- OpenSSL 3.x migration complete (1.0.x dropped)
- Protocol version 70001 (breaks compatibility with 1.x nodes)
- Client identity renamed from "Satoshi" to "CorgiCoin"
- `std::random_shuffle` replaced with `std::shuffle` (C++17 compliance)
- ECDSA_SIG direct member access replaced with accessor functions
- DNS seeds updated for new network
- GitHub Actions CI/CD pipeline added

### v1.4.1.42 - v1.4.1.67 — Modernization Era
- 16 releases, ~645+ individual modernizations
- C++11/14 migration: nullptr, smart pointers, range-based for, enum classes, structured bindings
- OpenSSL 1.1.x/3.x compatibility layer
- Boost 1.70+ compatibility (70% dependency reduction)
- Berkeley DB 4.8-6.2 compatibility
- Qt 4/5 dual support
- IRC peer discovery removal
- See [MODERNIZATION.md](MODERNIZATION.md) for full changelog

### v1.0 - v1.4.1.41 — Original Era (2014)
- Initial Dogecoin fork with Scrypt PoW
- Original network launch and mining

## Roadmap

### Completed
- [x] C++17 codebase upgrade
- [x] OpenSSL 3.x full migration
- [x] New genesis block for 2026 relaunch
- [x] Protocol version bump (v70001)
- [x] CI/CD pipeline (GitHub Actions)
- [x] DNS seed infrastructure update

### In Progress
- [ ] Gen block mining and hash finalization
- [ ] Seed node deployment (VPS infrastructure)
- [ ] Historical holder airdrop mechanism (previous chain data recovery)

### Planned
- [ ] Qt 6 migration (drop Qt 4 support)
- [ ] Replace json_spirit with modern JSON library
- [ ] Replace boost::filesystem with std::filesystem
- [ ] Block explorer
- [ ] Wallet UX improvements
- [ ] Bech32 address support (BIP173)
- [ ] P2P encryption (BIP151)

### Pump.fun / Solana Integration (Future)

CorgiCoin is exploring a cross-chain integration with the Solana memecoin ecosystem. Rather than tying to a single token, CORG aims to be a **PoW burn layer** that can partner with multiple pump.fun community tokens — starting with the existing [CORG token on pump.fun](https://pump.fun/coin/8uRR3wuidqf2FR3qqxUjgiExnuLCUYb7yRJ6xWd2pump).

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
