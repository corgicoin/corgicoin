# AuxPoW (Merged Mining) — Hard Fork Spec

Status: **implemented** — chain ID `0x00C6` and heights 50,000 mainnet /
200 testnet confirmed. Consensus core landed in PR #38; mining RPCs
(`createauxblock`/`submitauxblock`) and the fork-activation testnet
rehearsal in the follow-up. Activation is at mainnet height 50,000, so no
mainnet behavior changes until then.

> **Note on merged mining in practice:** the code is necessary but not
> sufficient. Merged mining only improves security once a real high-hashrate
> Scrypt pool (Litecoin/Dogecoin) configures CorgiCoin as an aux chain and
> commits our block hashes in its coinbase. The RPCs below are the interface
> such a pool drives; until one adopts the chain, solo CPU mining continues
> unchanged.

## Motivation

CorgiCoin is a low-hashrate Scrypt chain (networkhashps near one CPU; see
`project_mainnet_idle` history). That makes it cheap to 51%-attack: a single
rented Scrypt ASIC — the kind that secures Litecoin/Dogecoin — dwarfs the
entire network. The LWMA retarget (v4.3) fixed difficulty *oscillation*, but
it cannot manufacture hashrate.

**AuxPoW (merged mining, BIP untracked but standardized by Namecoin 2011 and
adopted by Dogecoin 2014) is the proven fix.** It lets a miner who is already
mining a high-hashrate parent chain (Litecoin, Dogecoin — any Scrypt chain)
*simultaneously* submit that same work as proof-of-work for CorgiCoin, at
near-zero marginal cost. The security argument: Dogecoin went from
attackable to effectively un-51%-able the moment it enabled merged mining
with Litecoin, because an attacker now needs a majority of *Litecoin's*
hashrate, not Dogecoin's. CorgiCoin can inherit the same umbrella.

This is the capstone of the modernization effort: the single change that
takes the chain from "works, but anyone could reorg it" to "defended by an
established Scrypt pool's hashrate."

## How merged mining works (overview)

A merged-mining pool mines a **parent** block (e.g. Litecoin). Into the
parent's coinbase transaction it embeds a commitment to one or more **aux**
chains' block hashes (CorgiCoin among them), arranged in a small merkle tree.
When the parent block's header hashes below an aux chain's target, that
parent block *is* a valid proof-of-work for the aux chain — the aux chain
accepts a block whose PoW lives in the parent chain, accompanied by a proof
(the "AuxPoW") that the aux block's hash was committed in the parent coinbase
and that the coinbase is in the parent block.

The aux chain never changes its own block contents or hashing — it changes
only *where it looks for the proof of work*.

## Block version: chain ID + AuxPoW flag

The 32-bit `nVersion` is partitioned (Namecoin/Dogecoin convention):

```
  bits  0– 7 : base block version (currently 1)
  bit   8    : AuxPoW flag — set when this block carries an AuxPoW proof
  bits 16–31 : chain ID (identifies CorgiCoin in a merged-mining merkle tree)
```

- `GetBaseVersion(v)   = v & 0xff`
- `GetChainId(v)       = v >> 16`
- `IsAuxPow(v)         = (v & 0x100) != 0`

**Proposed CorgiCoin chain ID: `0x00C6`** (mnemonic "C6" ≈ Corgi). It only
needs to be stable and distinct from other aux chains a pool merges
simultaneously; the value is otherwise free. **Confirm before implementing** —
it is baked into consensus forever.

Pre-fork blocks have `nVersion == 1` (chain ID 0, AuxPoW bit clear). After
the fork, legacy (non-merged) blocks set the chain ID but leave the AuxPoW
bit clear and hash their own header exactly as today; merged blocks set the
AuxPoW bit and carry the proof. Both remain valid — the chain is not
merged-mining-*only*, so solo CPU mining keeps working.

## New types

### CPureBlockHeader

The existing `CBlock` header fields (`nVersion … nNonce`, 80 bytes) factored
into a standalone serializable type with its own `GetHash()` and
`GetPoWHash()` (scrypt). Needed so the parent block header can be carried and
hashed **without** recursively pulling in an AuxPoW (the parent must never
itself carry an aux proof — guarded in Check).

### CAuxPow

Serialized (in this order), mirroring the Dogecoin/Namecoin layout so
existing merged-mining pool software works unmodified:

1. `CMerkleTx coinbaseTx` — the parent block's coinbase transaction plus its
   merkle branch (`vMerkleBranch` + `nIndex`) proving it under
   `parentBlock.hashMerkleRoot`.
2. `uint256 hashBlock` — legacy/unused (kept for wire compatibility).
3. `std::vector<uint256> vChainMerkleBranch` + `int nChainIndex` — the branch
   proving *this* aux block's hash under the aux merkle root.
4. `CPureBlockHeader parentBlock` — the parent chain's header; the object that
   actually carries the proof-of-work.

### CBlock changes

- Add `std::shared_ptr<CAuxPow> auxpow` (memory + wire).
- Serialization: after the 80-byte header, **if** `IsAuxPow(nVersion)`, read/
  write the `CAuxPow`. Non-AuxPoW blocks serialize byte-identically to today —
  no disk migration, old blocks parse unchanged.

## Verification — CheckAuxPowProofOfWork

Replaces the direct `CheckProofOfWork(GetPoWHash(), nBits)` for post-fork
blocks. Given a block header and its `nBits`:

```
if height < AUXPOW_FORK_HEIGHT:
    # unchanged legacy rule
    return CheckProofOfWork(header.GetPoWHash(), nBits)

if not IsAuxPow(header.nVersion):
    # legacy/solo block after the fork: still hash our own header,
    # but the chain ID must be correct and there must be no stray auxpow
    require GetChainId(header.nVersion) == CHAIN_ID
    require header.auxpow == null
    return CheckProofOfWork(header.GetPoWHash(), nBits)

# merged-mined block
aux = header.auxpow
require GetChainId(header.nVersion) == CHAIN_ID
require GetChainId(aux.parentBlock.nVersion) != CHAIN_ID   # no self-merge
require not IsAuxPow(aux.parentBlock.nVersion)             # parent isn't itself aux

# 1. the aux block hash is committed in the aux merkle tree
rootHash = CheckMerkleBranch(header.GetHash(), aux.vChainMerkleBranch, aux.nChainIndex)

# 2. the coinbase is in the parent block
require CheckMerkleBranch(aux.coinbaseTx.GetHash(),
                          aux.coinbaseTx.vMerkleBranch,
                          aux.coinbaseTx.nIndex) == aux.parentBlock.hashMerkleRoot

# 3. the parent coinbase scriptSig contains the commitment:
#    magic bytes 0xfa 0xbe 'm' 'm', then rootHash (reversed), then
#    merkle_size (1<<branch.size) and merkle_nonce. Enforce the standard
#    anti-spoofing rules: magic must appear once; rootHash must be at a
#    position consistent with merkle_size/nonce (slot = expected index).
require commitment in aux.coinbaseTx scriptSig is well-formed and matches rootHash/nChainIndex

# 4. the PARENT header carries the proof of work, against OUR target
return CheckProofOfWork(aux.parentBlock.GetPoWHash(), nBits)
```

`CheckMerkleBranch(leaf, branch, index)` folds the leaf up through the branch
(standard Bitcoin merkle path) and returns the computed root.

Difficulty (`nBits`) is still produced by the LWMA retarget — merged mining
changes only *who* supplies the work, not the target. The parent's own
difficulty is irrelevant to us; we only require the parent header to meet
*our* `nBits`.

## Activation

Height-gated, no versionbits (consistent with the LWMA fork).

| Network | Fork height | Rationale |
|---------|-------------|-----------|
| mainnet | **50,000** | well past the LWMA fork (34,000) and the current tip (~31,400); leaves generous runway to implement, release, and get the ecosystem/pool ready |
| testnet | **200** | fresh testnet rehearses the transition quickly |

Rules by height:

- `< AUXPOW_FORK_HEIGHT`: today's rules exactly. `nVersion` stays 1; the
  chain-ID/AuxPoW bits are not yet interpreted.
- `>= AUXPOW_FORK_HEIGHT`: blocks must carry chain ID `CHAIN_ID`. Blocks may
  be solo (AuxPoW bit clear, own-header PoW) or merged (AuxPoW bit set, proof
  verified as above). This keeps CPU solo mining alive alongside merged
  mining.

All nodes must upgrade before the fork height; a pre-fork node rejects the
new version/auxpow blocks and forks off. With the current node population
(two seeds + a handful of wallets) this is a controlled event, same as LWMA.

## Mining interface

Add the modern pool RPC pair (Dogecoin/Namecoin `createauxblock` /
`submitauxblock`), which pools already speak:

- `createauxblock <paytoaddress>` → returns the current aux block target:
  `{hash, chainid, bits, height, _target, coinbasevalue, previousblockhash}`.
  The pool inserts `hash` into its merged-mining merkle tree and commits the
  root in the parent coinbase.
- `submitauxblock <hash> <auxpow_hex>` → the pool submits the serialized
  AuxPoW once the parent block is found; the node assembles the full CBlock,
  runs `CheckAuxPowProofOfWork`, and accepts it if valid.

The legacy `getblocktemplate`/`getwork` paths continue to serve solo CPU
miners unchanged (they produce AuxPoW-bit-clear blocks).

## Serialization / back-compat notes

- Non-AuxPoW blocks (all historical blocks and post-fork solo blocks)
  serialize identically to today — no reindex, no `.dat` migration.
- The AuxPoW payload is appended only when the version bit is set, so block
  storage and the P2P `block` message are backward-compatible for every
  block that does not use merged mining.
- `GetHash()` continues to hash only the 80-byte header — the aux proof is
  never part of the block's identity, only of its PoW validation. This is
  essential: the committed aux hash in the parent coinbase is this
  `GetHash()`, computed before any AuxPoW exists.

## Implementation checklist (for the follow-up change)

1. `CPureBlockHeader` extracted; `CBlock` built on it; `auxpow` member +
   conditional serialization.
2. `CAuxPow` type: serialization, `CheckMerkleBranch`, commitment parsing,
   `Check(auxBlockHash, chainId)`.
3. Version helpers (`GetBaseVersion/GetChainId/IsAuxPow`) + constants
   (`CHAIN_ID`, `AUXPOW_FORK_HEIGHT_{MAINNET,TESTNET}`).
4. `CheckAuxPowProofOfWork` wired into `CheckBlock` / `AcceptBlock` /
   `CBlock::ReadFromDisk` in place of the raw PoW check, height-gated.
5. Block creation sets chain ID post-fork; `createauxblock`/`submitauxblock`
   RPCs.
6. Tests (`src/test/auxpow_tests.cpp`): merkle-branch fold vectors; a hand-
   constructed valid AuxPoW accepted; tampered commitment / wrong chain ID /
   self-merge / parent-is-aux / wrong-index all rejected; non-AuxPoW block
   still validates via the legacy path; pre-fork height ignores the version
   bits.
7. Testnet rehearsal: mine solo through the fork height, then submit a
   synthetic merged block, verify both nodes accept and stay in consensus.

## References

- Namecoin merged mining (original AuxPoW design, 2011)
- Dogecoin AuxPoW deployment (Scrypt merged mining with Litecoin, 2014) —
  the closest precedent; CorgiCoin shares its Scrypt PoW and family lineage
- `doc/lwma-retarget-spec.md` — difficulty algorithm the AuxPoW blocks obey
- `doc/seed-node-upgrade.md` — operator procedure for the rollout
