# Phase 2 — Partner Token Program: Design

> **Scope.** This document is a working design for the Solana-side program
> that backs Phase 2 of `ROADMAP-PUMPFUN.md`. It is exploratory, not a
> commitment. Open questions are flagged inline.

## What Phase 1 leaves on the table

The Phase 1 bridge (`contrib/bridge/bridge.py`) is operational on devnet
as of 2026-05-01: it watches `corgicoind` for `burnforpartner` txns and
dispatches SPL token rewards from a per-partner treasury keypair held on
the bridge host. The full architecture is one Python script + a JSON
config file. It works for one team running one bridge for one partner.

Five things that don't scale beyond a PoC:

1. **Treasury custody.** Each partner's SPL tokens live behind a raw keypair
   stored next to the bridge code. Compromise of the bridge host = total
   drain of every partner's vault.
2. **Permissioned registration.** Partners are added by editing
   `partners.json` and restarting the bridge. There is no path for a third
   partner team to onboard without us.
3. **Trusted oracle is implicit.** The bridge IS the oracle, and there is
   no rate limit, dedupe, or audit on what it can do. A bug or compromise
   has nothing standing between it and the funds.
4. **Single reward model.** Only "airdrop" (SPL transfer) is supported.
   The roadmap calls for LP / boost / access models too.
5. **Idempotency lives off-chain.** Dedupe is in `state.json`; rebuilding
   the bridge from scratch (or running a second bridge) re-dispatches all
   historical burns.

Phase 2 is the framework that fixes all five. This doc focuses on (1),
(2), (3), and (5). Reward-model expansion (4) is deferred to a future
phase.

## Architecture

A single Solana program, written in Anchor, owns three account types:

```
┌─────────────────────────────────┐
│  PartnerRegistry (1 PDA total)  │
│   admin_authority               │
└─────────────────────────────────┘

┌─────────────────────────────────┐    ┌─────────────────────────┐
│  Partner (1 PDA per partner)    │───▶│  Partner Vault (ATA)    │
│   tag, mint, oracle, params     │    │   owned by Partner PDA  │
└─────────────────────────────────┘    └─────────────────────────┘
                  │
                  │ on each burn
                  ▼
┌─────────────────────────────────┐
│  ProcessedBurn                  │
│   (1 PDA per (partner, txid))   │
│   audit + atomic dedupe         │
└─────────────────────────────────┘
```

The bridge becomes a thin client: it watches `corgicoind`, signs
`dispatch_reward` instructions with the oracle key, and submits them.
All correctness logic — dedupe, rate limits, reward math, vault
authority — is enforced by the program.

### Why this layout

- **One program, many partners.** The same code path serves every partner;
  partner-specific state is in their PDA. Adding a new partner does not
  require a code change or redeploy.
- **PDA-owned vault.** The vault ATA is owned by the Partner PDA, not by
  any wallet. The program is the only thing that can move the tokens, and
  only via instructions that pass the program's validation. Compromise of
  the oracle key drains *one partner up to its rate limit*, not everyone.
- **PDA per processed burn.** Creating an account with a deterministic
  seed fails atomically if the account exists. This is Solana-native
  exactly-once dedupe — the same primitive Wormhole and most cross-chain
  bridges use.
- **Per-partner oracle authority.** Each partner names which Solana
  account is allowed to call `dispatch_reward` for them. Partners can pick
  shared infrastructure (the team's bridge oracle) or their own oracle.

## Account structures

```rust
#[account]
pub struct PartnerRegistry {
    pub admin_authority: Pubkey,  // can revoke partners; cannot move funds
    pub bump: u8,
}
// PDA seeds: ["registry"]

#[account]
pub struct Partner {
    pub tag: [u8; 4],                     // matches OP_RETURN tag
    pub mint: Pubkey,                     // SPL token to dispatch
    pub vault: Pubkey,                    // ATA owned by this PDA
    pub oracle_authority: Pubkey,         // who may call dispatch_reward
    pub partner_authority: Pubkey,        // who may withdraw / update / rotate
    pub reward_ratio_numerator: u64,
    pub reward_ratio_denominator: u64,    // reward = amount * num / denom
    pub max_reward_per_burn: u64,         // per-call cap
    pub max_reward_per_window: u64,       // rolling window cap
    pub window_seconds: u32,
    pub window_started_at: i64,           // resets when current window expires
    pub window_dispatched: u64,
    pub revoked: bool,
    pub bump: u8,
}
// PDA seeds: ["partner", tag]

#[account]
pub struct ProcessedBurn {
    pub corg_txid: [u8; 32],
    pub dispatched_at: i64,
    pub corg_amount_microcorg: u64,
    pub reward_amount: u64,
    pub sol_dest: Pubkey,
    pub bump: u8,
}
// PDA seeds: ["processed", tag, corg_txid]
```

Sizing: Partner ~150 bytes, ProcessedBurn ~120 bytes. At rent-exemption
rates (~7M lamports per 100 bytes), each ProcessedBurn costs ~0.0008 SOL
to create. The vault keepalive is ~0.002 SOL one-time. Cheap.

## Instruction set

| Name | Caller | Purpose |
|---|---|---|
| `initialize_registry` | `payer` | Create the singleton PartnerRegistry. Run once at deploy time. |
| `register_partner(tag, mint, oracle_authority, partner_authority, ratio_num, ratio_denom, max_per_burn, max_per_window, window_seconds)` | anyone, pays rent | Create Partner PDA + vault ATA. |
| `update_partner(tag, …)` | `partner_authority` | Change ratio / rate limits / oracle. Cannot change tag or mint. |
| `transfer_partner_authority(tag, new_authority)` | `partner_authority` | Rotate the partner authority key. |
| `deposit(tag, amount)` | anyone | Move SPL tokens into the partner's vault. |
| `withdraw(tag, amount)` | `partner_authority` | Move tokens out. Always permitted, even after revocation. |
| `dispatch_reward(corg_txid, sol_dest, corg_amount_microcorg)` | `oracle_authority` | Atomic: create ProcessedBurn PDA (refuses if exists), apply rate limit, transfer from vault to recipient ATA, create recipient ATA if needed. |
| `revoke_partner(tag)` | `admin_authority` | Sets `revoked=true`; subsequent `dispatch_reward` calls fail. Withdraw still works. |

### `dispatch_reward` validation flow

```
1. Signer must be partner.oracle_authority
2. Partner must not be revoked
3. Compute reward = (corg_amount_microcorg * ratio_num) / ratio_denom
4. Reject if reward > max_reward_per_burn
5. If now > window_started_at + window_seconds: reset window counters
6. Reject if window_dispatched + reward > max_reward_per_window
7. Init ProcessedBurn PDA (init = atomic; init_if_needed would defeat dedupe)
8. CPI to SPL token: transfer reward from vault to recipient ATA
   (with init_if_needed for the destination ATA, payer = signer)
9. Update window_dispatched += reward
```

Step 7 is the dedupe primitive. Solana's runtime enforces that creating
a PDA that already exists is an error — the whole transaction reverts.
No race, no double-spend, no off-chain coordination required.

## Bridge changes

Today, `contrib/bridge/bridge.py` does this per burn:

```python
src_ata = get_associated_token_address(treasury, mint)
dst_ata = get_associated_token_address(burner_sol, mint)
# create dst_ata if missing, then transfer_checked from src_ata
```

After Phase 2:

```python
ix = program.instruction(
    "dispatch_reward",
    args=(corg_txid_bytes, burner_sol, corg_amount_microcorg),
    accounts={
        "partner": partner_pda,
        "vault": partner.vault,
        "processed_burn": processed_burn_pda,        # init in instruction
        "recipient_ata": recipient_ata,              # init_if_needed
        "oracle_authority": oracle_keypair.pubkey(), # signer
        ...
    },
)
sig = client.send_transaction(Transaction.new_signed_with_payer(
    [ix], oracle_keypair, [oracle_keypair], blockhash
))
```

`partners.json` goes away — `load_partners` becomes "fetch all Partner
accounts under the program ID via `getProgramAccounts`, decode with the
Anchor IDL, build a tag→Partner map." The oracle keypair is the only
secret the bridge holds.

The state.json reconciliation flow we just shipped becomes vestigial:
on-chain ProcessedBurn IS the canonical state. The bridge can keep a
local cache for replay-from-tip-on-restart performance, but correctness
no longer depends on it.

## Migration from Phase 1

The current devnet partner (`8xudSD6kdeFu1nu5sEiy9zBm2iYhKnnsZfyfF6HGyPq4`)
is a raw mint with a treasury keypair. Migration plan:

1. Deploy the program to devnet.
2. `register_partner` for tag "CORG" with mint = current devnet mint,
   `oracle_authority` = the bridge's keypair, `partner_authority` = the
   current treasury keypair. Reward ratio 1:1, no rate limits initially.
3. Transfer the existing treasury balance into the new vault ATA via a
   plain SPL transfer (one-time, signed by the old treasury key).
4. Update the bridge to call the program. Verify a fresh devnet burn
   dispatches through the new path.
5. Old `partners.json` and treasury keypair retired. Partner authority
   can later be rotated to a multisig if desired.

Steps 1-4 are roughly one session. Step 5 is housekeeping.

## Phased implementation plan

| Session | Deliverable | Blocking deps |
|---|---|---|
| 1 | Anchor workspace under `contrib/partner-program/`. PartnerRegistry + Partner accounts. `initialize_registry` and `register_partner` instructions. Local validator tests. | none |
| 2 | `dispatch_reward` with ProcessedBurn dedupe + rate limits. Tests: happy path, double-dispatch refused, rate-limit exhaustion, revoked partner refused. | session 1 |
| 3 | `update_partner`, `transfer_partner_authority`, `deposit`, `withdraw`, `revoke_partner`. Admin tests. | session 1 |
| 4 | Bridge rewrite: read partners from on-chain registry, dispatch via program. End-to-end devnet smoke test. | session 2 + 3 |
| 5 | Migration of existing devnet partner. Documentation update. | session 4 |

Total: 4-6 working sessions, depending on Anchor familiarity and how
much time goes to fighting solana-test-validator on macOS. None of the
sessions are larger than what we did for the Phase 1 idempotency work.

## Open questions

These are decisions we should make before starting session 1. None are
blockers but each affects the account schema or instruction signatures.

1. **Trusted oracle vs. multisig oracle vs. light client.**
   Today's plan: per-partner oracle is a single Solana account, partner
   chooses who to trust. The roadmap's Phase 5 progression (single →
   multisig → light client) maps onto this if we leave room — multisig
   is just "oracle_authority is a Squads multisig PDA" with no schema
   change. Light client requires verifying scrypt PoW headers on Solana,
   which is non-trivial; defer entirely until Phase 5.

2. **Reward ratio precision.** `u64 num / u64 denom` allows arbitrary
   ratios but rounds toward zero. For 1:1 we use 1/1, fine. For
   "100 partner micro-tokens per 1 CORG" we use 100/1. Need to think
   about decimals difference between CORG (8) and arbitrary SPL mints
   (commonly 6 or 9). Probably want to fold mint decimals into the
   ratio rather than carry CORG decimals into the program's storage.

3. **Multi-mint per partner.** A single `burnforpartner` triggers one
   reward today. Future: a basket — one CORG burn pays out tokens from
   N mints. Cleanest extension is a `MintAllocation` sub-account vector;
   doable later without breaking the Partner schema if we leave room.
   Decide now whether to ship 1-mint or N-mint in MVP.

4. **Governance / curated registration.**
   Permissionless `register_partner` means anyone can squat tags. Three
   options: (a) admin-gated registration (requires registry's
   `admin_authority` signature), (b) permissionless + admin-revocable
   (current plan), (c) on-chain governance vote per partner. Roadmap
   leans toward (c) eventually; (b) is the right MVP.

5. **Fee model.** Who pays the Solana txn fee for `dispatch_reward`?
   Currently the oracle wallet, which means we need to keep it topped
   up with SOL. Could shift to the partner's vault paying via a SOL
   sub-account, but that's another moving part. Keep oracle-pays for
   MVP, document the operational requirement.

6. **Upgradeability.** Anchor programs default to upgradeable via the
   program upgrade authority. We probably want this during Phase 2/3
   while we iterate, locked down to a multisig before any partner
   commits real money. Worth documenting in the security model.

7. **Versioning the OP_RETURN payload.** If we want to carry more than
   "partner tag + sol_dest" later (e.g., reward model selector,
   reference id for an LP deposit), we'll need to bump the on-chain
   spec in `doc/burn-payload-spec.md` and accept both versions during
   the transition. Decide now whether v1 is fine for the foreseeable
   future or whether we should rev it before locking the program in.

## Non-goals (for Phase 2)

- LP / boost / access reward models. These need their own design pass.
- Cross-chain TX proof verification. Stay with trusted oracle.
- A web UI for partner registration. CLI-only for MVP.
- Solana-side support for multiple chains. CORG only.
- Anything on the CorgiCoin chain side. Phase 2 is purely Solana.

## Recommendation

Pick one option each on questions 3 and 4 before session 1, since both
affect the Partner account schema. Defer the rest.

Suggested defaults:
- (3) **1-mint per partner for MVP.** Adds the right complexity floor.
- (4) **Permissionless + admin-revocable.** Lowest barrier; admin escape
  hatch covers abuse.

Everything else can move after we have a working `register_partner` +
`dispatch_reward` path.
