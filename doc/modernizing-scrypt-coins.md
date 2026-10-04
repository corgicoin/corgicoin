# Modernizing a 2014-era Scrypt Coin: A Playbook

CorgiCoin is a 2014 Dogecoin-family Scrypt chain brought to a 2026 codebase.
This document distills the work into a reusable guide for anyone doing the
same to another old Litecoin/Dogecoin-lineage coin. It is ordered the way we
actually did it — each stage unblocks the next, and the early stages are the
ones that make everything after them safe.

The throughline: **get a build and a test suite and CI working first, then
make changes behind that safety net, newest-risk changes last.**

## 0. Starting point

A typical 2014 Scrypt coin is a Bitcoin 0.8-era C++ codebase plus a Qt
wallet: C++03, OpenSSL 1.0, Boost everywhere, `json_spirit`, qmake/autotools,
`printf` logging, no tests, no CI. It compiles (maybe) on the toolchain of
its era and nothing newer.

## 1. Get it building on a modern toolchain (CMake)

Nothing else is possible until it compiles on a current compiler. Do the
minimum to build, not to beautify.

- **Replace qmake/autotools with CMake.** One `CMakeLists.txt` that builds the
  daemon, the Qt GUI (optional), and a test binary. Options: `BUILD_QT_GUI`,
  `BUILD_TESTS`, `USE_UPNP`. Keep the qmake files until CMake fully works,
  then delete them in a dedicated cleanup commit.
- **Single source of version truth.** Parse `CLIENT_VERSION_*` from
  `version.h` into the CMake `project(VERSION …)` so the build banner can
  never drift from what the binary reports. (We shipped a release whose
  banner lied by a minor version before doing this.)
- **Fix the compile errors the modern compiler surfaces**, nothing more yet.

## 2. OpenSSL 1.0 → 3.x

The biggest mechanical migration. OpenSSL 1.1 made `EVP`/`BN`/`EC` structs
opaque; 3.0 deprecated the low-level ECDSA/EC_KEY API.

- Route key/signature code through `EVP` and the `OSSL_*` interfaces.
- `BN_*` usage in the bignum wrapper mostly survives; the EC key handling is
  the real work.
- Gate anything version-specific on `OPENSSL_VERSION_NUMBER` only if you must
  support both; prefer committing to 3.x.

## 3. C++03 → C++17, incrementally

Do this as a long series of small, individually-building commits, not one
heroic diff:

- `boost::thread/mutex/shared_ptr/array/bind/foreach` → `std::` equivalents
  and range-based for / lambdas.
- `boost::filesystem` → `std::filesystem`.
- Raw `new`/`delete` → smart pointers where ownership is clear.
- `NULL`/`0` → `nullptr`; index loops → range-based.

Leave the hard, consensus-touching Boost pieces (`variant`, `asio`,
`interprocess`, `signals2`) for later or forever — see §8.

## 4. Replace json_spirit with nlohmann/json

`json_spirit` is a Boost.Spirit relic and slow to compile. Rather than
rewrite every RPC, write a thin `json_compat.h` shim that presents the old
`Value`/`Object`/`Array`/`Pair` API on top of `nlohmann::json`. The RPC code
barely changes; the dependency is gone.

> **Gotcha (int width):** `int64_t` is `long` on LP64 Linux but `long long`
> on macOS, while the codebase's `int64` typedef is `long long`. A JSON value
> constructor overloaded on `int64_t`/`uint64_t` is then **ambiguous** for a
> bare `int64` argument on GCC but fine on Clang. Cast to `int64_t` exactly at
> the call site. This bit us twice; see §9.

## 5. A test suite and CI — before the risky changes

This is the hinge of the whole effort. Everything after here is a consensus
or protocol change, and you cannot make those safely without a net.

- Port/enable the Boost.Test unit tests (`scrypt`, `base58`, `script`,
  `transaction`, `key`, serialization, …). Add coin-specific ones (block
  reward schedule, any custom opcodes).
- GitHub Actions matrix: Ubuntu + macOS build the daemon and run the tests on
  every push and PR; add a Windows cross-compile (MinGW) and an MSYS2 Qt
  build for release artifacts.
- **Build on both libstdc++ (Linux) and libc++ (macOS).** They diverge on
  transitive includes and integer-type widths; a change that compiles on one
  can fail on the other. Treat Linux CI as authoritative for header/type
  changes even when developing on a Mac.

## 6. Structured logging, modern addresses, a release pipeline

Quality-of-life modernizations that are low-risk once CI exists:

- `printf` debug spew → a logging framework with categories
  (`LogPrintf`/`LogPrint(category, …)`).
- **Bech32m addresses** (BIP-173/350). A no-segwit chain can still adopt
  bech32m purely as a *new encoding* of its existing P2PKH/P2SH destinations:
  HRP + a 5-bit type byte + the 20-byte hash. Accept it anywhere addresses
  are parsed; keep base58 as the default output. Validate against the
  official BIP test vectors.
- **Tag-triggered release pipeline.** Pushing a `vX.Y.Z` tag builds every
  platform and publishes a GitHub Release with `SHA256SUMS`. This is what
  turns "it compiles" into "people can run it."

## 7. Consensus hard forks (the reason you did all the above)

Old Scrypt coins have two structural time bombs. Fix both via height-gated
hard forks. Spec each one first (a design doc that names the activation
heights and exact algorithm), implement behind the height gate so historical
blocks validate unchanged, add unit tests against the algorithm, and
**rehearse on a fresh testnet** (mine through the fork height on two nodes and
confirm they stay in consensus) before tagging a release.

### 7a. Difficulty retargeting: interval → LWMA

The Bitcoin-era "retarget every N blocks" is fatal at low hashrate: a miner
hash-and-runs, difficulty spikes at the boundary, then the chain freezes for
days because difficulty can't adjust until the next boundary that never
comes. Replace it with **LWMA-1** (Zawy) — a per-block linearly-weighted
moving average with a solvetime cap and monotonic-timestamp guard. Tighten
the future-time-limit (e.g. 2h → 5 minutes) at the same fork. (`doc/lwma-retarget-spec.md`.)

### 7b. 51% resistance: AuxPoW merged mining

A near-CPU-hashrate chain is trivially reorg-able by one rented Scrypt ASIC.
**AuxPoW** lets a high-hashrate parent chain (Litecoin/Dogecoin) secure yours
at near-zero marginal cost — the mechanism that made Dogecoin un-attackable
once it merged with Litecoin. Partition the block `nVersion` into base
version / AuxPoW flag / chain ID; add `CPureBlockHeader` and `CAuxPow`
(parent coinbase + merkle branches + parent header); verify the coinbase
commitment, merkle proofs, and parent PoW. Keep non-merged blocks
byte-identical on the wire (no reindex) and solo mining alive. Add the
standard `createauxblock`/`submitauxblock` pool RPCs. (`doc/auxpow-spec.md`.)

> AuxPoW is necessary but not sufficient: it only improves security once a
> real Scrypt pool actually configures your chain as an aux chain.

## 8. What to leave alone

Not everything should be modernized. The remaining Boost in CorgiCoin is
deliberate: `asio` (RPC server I/O), `interprocess` (URI message queue),
`program_options` (CLI parsing), `signals2` (keystore observer). Each is a
well-contained dependency whose replacement is a rewrite, not a cleanup, with
no user-visible benefit. `boost::date_time` is gone except where
`interprocess` timed operations require a `ptime`. Headers-first sync and
encrypted P2P transport (BIP324) are large protocol changes with little
payoff for a small/pre-launch chain — skip until the chain's scale justifies
them.

## 9. Lessons that cost us time

- **Verify header and integer-type changes on Linux, not just macOS.** Both
  of our post-merge CI breaks were libstdc++-vs-libc++ divergences a macOS
  build couldn't see: (1) the `int64`/`int64_t` JSON ambiguity (§4), and
  (2) removing Boost headers from a hub header silently dropped the transitive
  `<algorithm>`/`<cmath>` the whole codebase relied on — fine on libc++,
  broken on libstdc++.
- **Rehearse forks on a fresh testnet.** Our first LWMA rehearsal uncovered a
  latent pre-existing bug (testnet pow-limit was stricter than testnet genesis
  bits, deadlocking testnet mining) that had nothing to do with the fork — but
  would have blocked any real testnet use.
- **Spec consensus changes before coding them.** The design doc is where you
  catch "what activation height, what exact algorithm, what's the back-compat
  story" — cheaply, before it's in C++.

## Appendix: CorgiCoin reference docs

- `doc/lwma-retarget-spec.md` — difficulty algorithm + activation
- `doc/auxpow-spec.md` — merged mining format, verification, RPCs
- `doc/burn-payload-spec.md` — the on-chain OP_RETURN burn protocol
- `doc/mining.md` — how to mine (solo CPU + external miners)
- `doc/seed-node-upgrade.md` — operator upgrade/rollback runbook
