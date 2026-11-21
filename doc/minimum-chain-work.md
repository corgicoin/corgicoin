# Minimum chain work

A node counts itself as synced (and so mines, serves block templates and relays as a full node) only when its best chain has at least
`-minimumchainwork` of total work, as well as recent blocks. On mainnet that now defaults to the total work of block **80000**:

| | |
|---|---|
| block | 80000 |
| hash | `b9d09330ebf52c48015511933586fa4a01e50e401f6c5219bd9cf404f67e6674` |
| total work (`chainwork`) | `29990c451eb92` |
| set on | 2026-11-21, when the tip was block 87,578 (total work `343c348000eaf`), about 5 days after block 80000 |

## Why

A node that has just started knows nothing but the genesis block. A peer that feeds it a chain of cheap, valid blocks (the difficulty of a young
chain is low) could make it believe it has caught up with the network, and it would then mine, relay and serve wallets from that chain. With a
floor that is below what the real chain has, but well above what a made-up chain costs to build, a node on such a chain stays in "still
catching up" until the real chain arrives. The floor is not a checkpoint: it does not name a block and does not reject any chain, so a fork
that is lighter than the floor is still followed, it just does not count as synced.

## Choosing the value

It must be **below** the work of the real chain at all times (a node on the honest chain must never be held back by it) and as high as is safe.
So it is the work of a block a few days behind the tip. Raising it at each release is cheap; too high a value is the only dangerous mistake,
because a node on the real chain would then say "still catching up" for ever and stop mining.

To check or renew it, on a synced node:

    corgicoind getblockhash 80000                       # must equal the hash above on every node you ask
    corgicoind invalidateblock <hash of block 80001>    # a node that can be rolled back (not a wallet node you rely on)
    corgicoind getblockchaininfo                        # "chainwork" is now the work of block 80000
    corgicoind reconsiderblock <hash of block 80001>

Ask more than one independent node (the seeds, a node you run) for the same hash and work before putting a value in a release.

## Turning it off

`-minimumchainwork=0` (or any other value) overrides the default. It is not set on testnet and regtest.
