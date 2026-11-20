# Replace-by-fee (BIP 125 rules)

A transaction in a node's pool that spends a coin another transaction spends is refused, unless it is a replacement:

- the transaction in the pool signalled that it can be replaced (an input with a sequence number below `0xfffffffe`);
- the newcomer pays more than everything it pushes out (the conflicting transactions and all that is built on them), plus the relay
  fee for its own size, and at a higher fee rate than each conflicting transaction;
- it does not spend an output of what it replaces, and adds no unconfirmed input the replaced transaction did not have;
- it pushes out at most 100 transactions;
- the pool knows the fee of everything pushed out, and the newcomer's inputs are checked (a transaction put back after a
  reorganisation, or resubmitted by the wallet, never replaces anything).

It is **off by default in this release**: `-mempoolreplacement` turns it on. (A later release is expected to turn it on by default,
once wallets and merchants have had a release in which to read `bip125-replaceable`.) `-walletrbf` makes the wallet's own sends signal, so `bumpfee` can raise their fee.

## For merchants

**A zero-confirmation payment that signals is not safe to accept**, nor is one that rests on an unconfirmed transaction that signals:
the sender can replace it with one that pays someone else. `gettransaction` and `listtransactions` report
`bip125-replaceable`: `yes` (it, or an unconfirmed transaction it rests on, signals), `no` (it does not, or it is confirmed), or
`unknown` (unconfirmed, and not in this node's pool). Treat `yes` as unconfirmed until it is in a block. A transaction that does not
signal can still be replaced by a miner that chooses to; this only governs what this node relays.

When a replacement pushes a wallet's transaction out of the pool, the wallet abandons it (its coins are spent again by the
replacement, its change is no longer counted and it is not sent again).
