# Pruning, assume-valid and parallel script checks

## `-prune=<MiB>`

Keeps about this much of the block files and deletes the oldest. The block files are cut at 64 MiB when pruning (about 2 GB otherwise),
and a file goes only when every block in it is more than 2880 blocks (two days) below the tip; the file blocks are being added to is
never deleted. The minimum is 128. `blkpruned.dat` in the data directory lists the files that are gone (it is written before each is
deleted).

A pruned node still validates every block and transaction, from the unspent-output set (`chainstate/`), and it can follow a
reorganisation of up to 2880 blocks. What it cannot do:

* **Offer old blocks.** It does not claim `NODE_NETWORK`, so other nodes do not ask it for them.
* **Look through the deleted blocks.** `getblock` says "pruned"; a wallet scan skips them (and says so in the log and in `getinfo`'s
  errors); `importprivkey`, `importwallet` and the like that need a rescan over them stop with an error after the key is added.
  `-rescan` cannot be used with `-prune`.
* **Rebuild the unspent set.** That needs every block. If `chainstate/` is lost, a pruned node does not start: remove the data directory
  (keep `wallet.dat`) and sync again.
* **Start without `-prune`** once files are gone: it refuses, and says why. Going back to a full node means downloading the blocks again.

`gettxout` answers from the unspent set, so it works for coins in deleted blocks; `getrawtransaction` does not for those.
`getblockchaininfo` shows `pruned`, `pruneheight` (the lowest block whose data is still on disk) and `pruned_files`.

## `-assumevalid=<hash>`

Blocks under the given block, on the best header chain, are connected without checking their scripts (signatures). Everything else is still
checked: proof of work, the merkle root, amounts, and that every input is unspent. It applies only with headers-first, only when the
assumed block's header is on the best header chain and that chain is at least two weeks of blocks past the block in question, and (if
`-minimumchainwork` is set) only when the chain has that work. **Nothing is assumed unless this is given.** Use a hash from a source you
trust: it is a statement that the blocks up to it are valid. `getblockchaininfo` shows `assumevalid` and `blocks_scripts_assumed`.

## `-par=<n>`

Threads for the script checks of a block (default 0: one per core, at most 16; 1: one at a time, as before). The checks are collected
while a block is checked and run together before anything is written. If one fails, the block is connected again the old way (one check at
a time, against the index), so the error, the log line and the penalty for the peer are what they always were. `getblockchaininfo` shows
`script_check_threads` and `blocks_scripts_parallel`.
