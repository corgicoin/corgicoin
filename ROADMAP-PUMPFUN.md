# CorgiCoin x Pump.fun Integration Roadmap

> **DISCLAIMER:** This document is a working draft and is entirely in the discovery/exploration phase. Nothing described here is finalized, committed to, or guaranteed to ship. Features, timelines, tokenomics, and partnership details are all subject to change or may be scrapped entirely as we learn more. This is a brainstorm, not a promise.

## Vision

Bridge CorgiCoin's Scrypt PoW mining community with the Solana memecoin ecosystem. Rather than creating yet another token, CorgiCoin positions itself as a **PoW burn layer** — a mineable chain whose burn mechanism can integrate with *multiple* pump.fun community tokens. Miners get access to Solana DeFi; pump.fun communities get the credibility and deflation mechanics of a real proof-of-work chain.

## Existing Community

The [CORG token on pump.fun](https://pump.fun/coin/8uRR3wuidqf2FR3qqxUjgiExnuLCUYb7yRJ6xWd2pump) (`8uRR3wuidqf2FR3qqxUjgiExnuLCUYb7yRJ6xWd2pump`) is the first community token we're looking to integrate with. This is an independently launched token with locked distribution — we want to give that community credit as an early adopter and explore mutual benefit rather than replace them.

This is **not** an exclusive partnership. The burn bridge and partner program are designed to support multiple Solana tokens over time.

## Phase 1: Multi-Token Burn Bridge

**Goal:** Allow CORG holders to burn coins on-chain and receive rewards across one or more partnered Solana tokens.

### How It Works
1. User sends CORG to a provably unspendable burn address with an OP_RETURN containing:
   - Solana destination wallet address
   - Partner token identifier (which token ecosystem to credit)
2. Burn transaction confirmed on-chain (30 block maturity)
3. Bridge oracle verifies the burn and triggers reward distribution on Solana
4. Rewards can take different forms per partner: token airdrops, LP credits, NFT mints, etc.

### Key Difference from Single-Token Bridges
- Burns aren't 1:1 mapped to a single wrapped token
- Each partner token defines its own reward structure for CORG burns
- A single CORG burn could earn rewards across multiple partners simultaneously
- Partners opt-in through the Partner Token Program (Phase 2)

### Technical Requirements
- OP_RETURN burn protocol in CorgiCoin (embed destination + partner ID)
- Bridge oracle service (monitors CORG chain, distributes rewards on Solana)
- Burn registry: on-chain record of all burns with partner attribution
- Solana-side reward distribution program (SPL token transfers, LP deposits, etc.)

## Phase 2: Partner Token Program

**Goal:** A framework that lets any pump.fun token community integrate with CorgiCoin mining and burns.

### How It Works
1. Partner token projects register with the program (token address, reward structure, treasury)
2. Partners define how CORG burns translate to rewards for their holders:
   - **Airdrop model**: burn X CORG, receive Y partner tokens
   - **LP model**: burns fund liquidity for the partner token
   - **Boost model**: burns increase staking/yield multipliers for partner holders
   - **Access model**: burns unlock gated features or tiers in the partner ecosystem
3. Partners fund their reward pools (from their own treasury, transaction fees, etc.)
4. Bridge oracle handles cross-chain reward distribution

### First Partner: Pump.fun CORG Token
- The existing CORG token on pump.fun (`8uRR3w...d2pump`) is the inaugural partner
- Initial integration: CORG burns earn airdrop credits toward pump.fun CORG
- Community recognition: pump.fun CORG holders acknowledged as early supporters
- Joint marketing and community building between both ecosystems

### Future Partners
- Any pump.fun or Solana token can apply to join the partner program
- Corgi-themed tokens get priority (community alignment)
- Partners must have locked or fair-launch distribution (no rug risk)
- Governance vote by CORG miners/holders to approve new partners

## Phase 3: Cross-Chain Mining Rewards

**Goal:** A portion of mining rewards automatically funds partner token ecosystems on Solana.

### How It Works
1. Block reward split: configurable % (e.g. 5-10%) goes to a community treasury address
2. Treasury accumulates CORG, periodically burns through the Phase 1 bridge
3. Burns are distributed across active partners based on governance-set weights
4. Partner-side rewards flow to their communities (LP, airdrops, staking)

### Why This Matters
- Miners directly contribute to Solana-side ecosystems by mining
- Higher hashrate = more rewards = more cross-chain activity
- Partner token communities have a reason to promote CORG mining
- Creates a flywheel between PoW mining and memecoin trading

## Phase 4: Burn-to-Mint NFTs

**Goal:** Gamified burn mechanism where burning CORG mints collectible Corgi NFTs on Solana.

### Rarity Tiers (Example)
| CORG Burned | NFT Tier | Estimated Rarity |
|---|---|---|
| 10,000 | Common Corgi | ~60% of mints |
| 100,000 | Rare Corgi | ~25% of mints |
| 1,000,000 | Epic Corgi | ~12% of mints |
| 10,000,000 | Legendary Corgi | ~3% of mints |

### Utility
- Governance weight in partner program votes
- Boosted rewards across all partner tokens
- Cosmetic traits for future Corgi-themed apps
- Partner tokens can add their own utility to NFT holders

## Phase 5: Bridge Oracle Infrastructure

**Goal:** Decentralize the bridge from a single oracle to a trustless system.

### Progression
1. **V1 — Centralized oracle** (fastest to ship, team-operated)
2. **V2 — Multisig oracle** (3-of-5 or 5-of-7 trusted operators, including partner representatives)
3. **V3 — Light client verification** (Solana program verifies CORG block headers + Merkle proofs)

### Security Considerations
- Oracle keys in HSMs or hardware wallets
- Rate limiting on reward distributions (max per block/hour)
- Emergency pause mechanism on Solana-side programs
- Full audit trail: every reward links back to a verifiable CORG burn tx

## Open Questions

- What percentage of block rewards should fund the community treasury? (governance vote?)
- How do partner tokens opt in — permissionless or curated?
- Should there be a minimum burn threshold to prevent spam?
- How are partner reward weights determined — governance, TVL-based, equal split?
- One-way burn only, or explore two-way bridge for wCORG later?
- Pump.fun launch strategy for any CorgiCoin-native tokens: bonding curve or DEX?
- How to handle partner tokens that fail/rug after integration?

## Timeline (Tentative)

| Phase | Target | Dependencies |
|---|---|---|
| Phase 1: Burn Bridge | Q2 2026 | v4.1 mainnet live, `burncoin` RPC ready, Solana program deployment |
| Phase 2: Partner Program | Q3-Q4 2026 | Phase 1 + pump.fun CORG community coordination |
| Phase 3: Mining Rewards | Q4 2026 | Phase 1-2 operational |
| Phase 4: NFTs | Q1 2027 | Phase 1 + art/metadata pipeline |
| Phase 5: Decentralized Oracle | Q2 2027 | Phase 1-3 battle-tested |
