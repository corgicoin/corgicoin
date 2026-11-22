# Headers-first sync (`-headersfirst`)

Off by default. `-headersfirst=1` turns it on; a node started without it behaves as before and logs nothing about it.

## What it does

Without it a node asks one peer "what comes after this" (`getblocks`), 500 blocks at a time, and takes each block from the peer that announced it.
With it the node first downloads only the **headers** (2000 per message), checks each, and so knows which chain has the most work before it
holds a single block. Then it fetches the blocks of that chain from several peers at once, in a window of 512 ahead of its tip.

Each header is checked for its proof of work (for a merged-mined block, the parent chain's work carried in the header, and its chain ID), its
difficulty, its time and the checkpoints. A header costs its sender real work, so what a peer can make a node hold is bounded by the work
it does. Headers are kept apart from the block index: the wallet, the RPC, the miner and reorganisations never see one. A block that arrives
goes through the usual checks again.

## Limits

| Limit | Value | When it applies |
|---|---|---|
| Headers per message | 2000 | more is refused and scored |
| Peers asked for the same headers at once | 3 | |
| Side-branch headers held | 50000 | past it the lowest-work branches are dropped, leaf by leaf; nobody is scored |
| Headers held that are not blocks | 1,000,000 | about ten times this chain's length, a few hundred MB at most; past it the same eviction, and a header that still finds no room is refused |
| Fork depth | 2000 blocks from the validated tip | a header forking off further back is not followed and not scored |
| Blocks in flight per peer | 64 | |
| `-headersynctimeout` | 120 s | a peer that does not answer `getheaders` in this time is dropped |
| `-blocktimeout` | 120 s | a peer that holds a requested block this long is dropped |

A header that fails a check is scored like any bad input (a bad proof of work, a wrong difficulty, a header that does not connect). A header
the node will not keep for a reason that is not the peer's fault (too deep a fork, no room) is refused without a score. A peer that answers a
request with headers the node already has, over and over, is scored and not asked again.

## When a peer is silent

A peer that does not answer a `getheaders` is dropped, and **two other peers** that claim a taller chain are asked for blocks the old way
(`getblocks`) and synced that way for 30 minutes; the rest carry on with headers-first. Peers that have not been in the fallback are chosen first.
A peer that answered with too few headers while it claims a longer chain than ours, with the tip unmoved for a timeout, is asked for blocks
the old way now and then. So a node is never held still by peers that answer pings and nothing else.

## Interaction with other options

- `-testmaxbranchheaders` and `-testmaxforkdepth` lower the two caps in regtest only (for the tests).
- Headers-first is used only with peers that speak protocol version 70014 or later; older peers are synced the old way, as before.

## Tests

`p2p_headers_first.py` (sync from two peers, bad headers refused, replay, a peer that never sends the blocks), `p2p_headers_first_limits.py`
(AuxPoW headers, the side-branch cap, the fork depth, a low-work chain that must not shut out the honest one), `p2p_headers_first_stalls.py`,
`p2p_headers_first_reorg.py`, `_latepeer.py` and `_oldpeer.py`.
