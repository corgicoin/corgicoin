# Limiting reorganisation depth (`-maxreorgdepth`)

Off by default (`-maxreorgdepth=0`). With `-maxreorgdepth=<n>` a node never takes a chain with more work if doing so would remove more than
`n` blocks from its own chain. Without it the node follows the chain with the most work, however far back it forks.

## Why

A chain with more total work wins, so someone who briefly rents more hash power than the honest network can mine a hidden chain from a
point `k` blocks back and publish it: the blocks of the last `k` are replaced, and a payment that was confirmed `k - 1` times is undone
(a double spend). On a small chain that is the main attack. A merged-mined chain is harder to attack than a stand-alone one, but not
immune. A node that refuses reorganisations deeper than `n` stays on the chain it had, so a payment with more than `n` confirmations is
final for it.

## The trade-off

This is a decision each node makes for itself, and it can split nodes. If an honest chain forks more than `n` blocks back (the network was
partitioned for a long time, say), a node with the limit stays on the shorter side and does not rejoin by itself. Nodes without the limit
follow the heavier chain. So:

- **Set it on nodes that care about finality** (an exchange, a payment processor), to the number of confirmations they wait for or more.
  The chain's block time is one minute, so `-maxreorgdepth=100` is about an hour and a half.
- **Do not set it everywhere with a small value**: a network where every node refuses a reorganisation deeper than `n` cannot recover from
  a fork deeper than `n` without people restarting nodes. A larger value is safer.
- Nothing about this is part of consensus: blocks are valid or invalid as before.

## What the node does

When a block arrives that makes a branch heavier than the best chain, and the branch forks more than `n` blocks back, the node:
- keeps the block in its block index (it is a valid block),
- does not switch to the branch, and logs `not reorganising to <hash> ... forks more than -maxreorgdepth=<n> blocks back`,
- sets the warning shown in `getinfo`'s `errors` (and in the GUI's status bar) until the next restart,
- goes on as before: it mines and relays on its own chain.

A depth equal to the limit is allowed (a limit of 5 allows a reorganisation that removes 5 blocks and refuses one that removes 6).

To follow the heavier chain after all, restart the node without the option: the next block of that chain makes it switch.
`reconsiderblock` and `invalidateblock` are not affected by the limit.

## Test

`feature_maxreorgdepth.py`: a fork of 4 is taken with a limit of 5, one of exactly 5 is taken, one of 7 is refused (and a control node
without the limit follows it), the refusal shows in the log and in `getinfo`, the node keeps mining, and a restart without the option
takes the heavier chain.
