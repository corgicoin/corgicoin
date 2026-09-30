# LWMA Difficulty Retarget — v4.3 Hard Fork Spec

Status: **draft** — activation heights to be confirmed before release.

## Motivation

CorgiCoin inherits Bitcoin's interval retarget: difficulty adjusts once
every 240 blocks (4 hours at the 60-second target), using the elapsed time
of the previous window, clamped to a 4x change (`src/main.cpp
GetNextWorkRequired`). On a low-hashrate chain this is the classic
small-Scrypt-coin failure mode:

- **Hash-and-run:** a large miner (one rented Scrypt ASIC dwarfs the
  current ~CPU-scale network) mines hundreds of blocks in minutes,
  difficulty quadruples at the next boundary, the miner leaves, and the
  remaining hashrate faces a 4x wall — at 4x floor difficulty and one CPU,
  the next 240-block window takes days-to-weeks, during which difficulty
  cannot adjust at all.
- **Observed in practice:** the chain sat idle Apr 18 – May 1 2026
  (height 18390) because the retarget gave no path for difficulty to
  track reality between boundaries.

Every surviving Doge-family chain replaced interval retargeting with a
per-block algorithm. The current best practice for small chains is
**LWMA (Linearly Weighted Moving Average)**, deployed by Bitcoin Gold,
Bitcoin Cash forks, Verge, and dozens of small PoW chains since 2018.

### Why LWMA over DGW3 (Dark Gravity Wave)

Both retarget every block over a trailing window. LWMA is chosen because:

- Its linear weighting (most recent solvetime weighted highest) responds
  faster to hashrate arrival/departure than DGW's flat average, with
  provably stable mean solvetime.
- DGW3 has known exploits on low-hashrate chains (timestamp manipulation
  oscillation) that LWMA's design specifically addressed; LWMA was written
  by Zawy after cataloging DGW failures across small coins.
- LWMA is simpler to implement correctly: no reference-block walk
  special cases, one pass over N headers.

## Algorithm — LWMA-1

Parameters:

| Symbol | Value | Meaning |
|--------|-------|---------|
| `T` | 60 s | target block spacing (unchanged) |
| `N` | 90 | averaging window (blocks) |
| `k` | `N*(N+1)/2 * T` = 245,700 | normalization constant |

For the next block after `pindexLast` (height `h+1`), using the `N+1`
most recent block headers:

```text
# blocks indexed i = 1..N from oldest to newest within the window
prev_ts = timestamp(h - N)
sum_weighted_solvetime = 0
sum_target = 0

for i in 1..N:
    ts = max(timestamp(h - N + i), prev_ts + 1)   # enforce monotonic view
    solvetime = min(ts - prev_ts, 6*T)             # cap at 6*T = 360 s
    prev_ts = ts
    sum_weighted_solvetime += solvetime * i        # newest gets weight N
    sum_target += target(h - N + i)                # expanded from nBits

avg_target  = sum_target / N
next_target = avg_target * sum_weighted_solvetime / k
next_target = min(next_target, pow_limit)
```

Properties:

- Mean solvetime converges to `T` (the weighting is chosen so a steady
  hashrate yields `sum_weighted_solvetime == k`).
- A miner 10x-ing the hashrate is fully re-priced within ~N blocks and
  meaningfully within ~N/4; when they leave, difficulty decays every
  block instead of freezing until a 240-block boundary that may never come.
- The `6*T` solvetime cap and monotonic-timestamp view bound how far a
  single dishonest timestamp can drag difficulty in either direction.
- No 4x clamps needed; the window itself bounds the per-block step.

Implementation notes:

- Arithmetic uses the existing `CBigNum` 256-bit integers (targets summed
  across 90 blocks cannot overflow 256-bit space given the compact-bits
  domain; solvetime sums fit trivially in `int64`).
- Division order follows the pseudocode exactly — consensus code, so the
  truncation behavior must match across all nodes/platforms (all integer
  ops, no floating point).

## Companion rule: reduce the future time limit (FTL)

`CheckBlock()` currently accepts timestamps up to **2 hours** ahead of
node adjusted time (`src/main.cpp:1825`). With per-block retargeting, a
2-hour forward timestamp lets a miner claim a 7200-second solvetime
(capped to 360 by the rule above, but repeatedly) to push difficulty
down. Standard LWMA deployment guidance:

- **FTL becomes `5*T` = 300 seconds** for blocks at/after the fork height.
- The existing median-time-past lower bound (`src/main.cpp:1884`) is
  unchanged.
- Node peer-time adjustment (`GetAdjustedTime`) is already bounded well
  inside 300 s, so no change there.

## Activation

Height-based, no versionbits (this codebase predates BIP9 and the added
machinery isn't warranted for a chain with two seeds and one miner).

| Network | Fork height | Rationale |
|---------|-------------|-----------|
| mainnet | **34,000** | tip is 31,403 as of 2026-09-29; ~86 blocks/day recently → roughly a month of margin, sooner if mining picks up. Adjust before release if pace changes. |
| testnet | **100** | fresh testnet chains rehearse the transition almost immediately |

Rules:

- `height < fork_height`: legacy interval retarget, byte-for-byte
  unchanged (including the historical `<5000` / `<10000` clamp tiers,
  which remain necessary to validate the existing chain).
- `height >= fork_height`: LWMA-1 as specified; FTL 300 s.
- The first blocks after activation read pre-fork headers into the LWMA
  window — no special seeding needed, the window is simply the last N
  headers regardless of which rule produced them.
- Testnet keeps its min-difficulty escape (20-minute rule) pre-fork
  **and drops it at the fork height** — LWMA windows containing
  min-difficulty blocks produce pathological targets, and post-fork
  difficulty decays quickly on its own, which is what the escape existed
  to approximate.

## Deployment plan

1. Implement behind the height gate; unit tests (see below).
2. Fresh testnet: mine through height 100 on two local nodes, verify the
   transition block and post-fork retargeting under start/stop mining.
3. Cut **v4.3.0.0** release (tag-triggered pipeline).
4. Upgrade both seed nodes (`doc/seed-node-upgrade.md`) — seed1 goes
   v4.1.0 → v4.3.0.0 directly, one SSH pass, well before height 34,000.
5. Any other node operators upgrade before activation; a v4.2 node at the
   fork height rejects/accepts blocks by the old rule and forks off — with
   the current node population this is a controlled event.

## Test plan

New `src/test/difficulty_tests.cpp` driving `GetNextWorkRequired` (or the
extracted LWMA function) with synthetic `CBlockIndex` chains:

- **Steady state:** N blocks at exactly T spacing → next target equals
  average target (regression anchor).
- **Hashrate arrival:** window of T/10 solvetimes → target drops toward
  1/10 within N blocks; verify monotonic approach.
- **Hashrate departure:** simulate 6*T-capped solvetimes → target rises
  every block (contrast: legacy algorithm frozen until boundary).
- **Timestamp attack:** alternating max-forward (FTL) and MTP-floor
  timestamps → mean solvetime stays within a few percent of T
  (the monotonic + cap rules absorb it).
- **Fork boundary:** heights below the gate use the legacy path
  (bit-identical against recorded mainnet nBits around a historical
  retarget boundary); the gate height itself computes via LWMA.
- **Pow-limit clamp:** all-slow window cannot exceed `bnProofOfWorkLimit`.

## References

- Zawy, "LWMA difficulty algorithm" — github.com/zawy12/difficulty-algorithms/issues/3
- Bitcoin Gold LWMA deployment (first major adopter, post-51%-attack)
- `doc/seed-node-upgrade.md` — operator procedure for the v4.3 rollout
