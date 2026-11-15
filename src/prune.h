// Pruning (-prune=<MiB>): old block files are deleted, and the node goes on validating from the unspent set.
//
// What a pruned node can still do: validate and relay new blocks and transactions (the set holds what an input spends), follow a
// reorganisation of up to PRUNE_KEEP_BLOCKS blocks, and mine. What it cannot: serve old blocks (it says so: it does not claim
// NODE_NETWORK), rescan its wallet over the pruned part, answer getrawtransaction or getblock for it, or rebuild the unspent set
// (that needs every block). A block file is deleted whole, oldest first, only when every block in it is more than PRUNE_KEEP_BLOCKS
// below the tip and never the file blocks are being added to. Which files are gone is kept in <datadir>/blkpruned.dat.
#ifndef CORGICOIN_PRUNE_H
#define CORGICOIN_PRUNE_H

#include "main.h"

extern bool fPruneMode;

/** Blocks under the tip that are always kept (2 days at one minute): the deepest reorganisation the node can follow. */
constexpr int PRUNE_KEEP_BLOCKS = 2880;

/** Read -prune and the list of deleted files. False, with the reason in strError, if the options or the data directory do not fit
 *  (pruning with -reindex or -rescan; a data directory that was pruned, started without -prune). */
bool PruneInit(std::string& strError);

/** True if block file number nFile has been deleted. */
bool IsBlockFilePruned(unsigned int nFile);
/** True if the block's data was in a deleted file (a header-only entry has none, and is not pruned). */
bool IsBlockPruned(const CBlockIndex* pindex);
/** How many block files have been deleted. */
unsigned int PrunedFileCount();
/** The height of the lowest block whose data is still on disk (0 if nothing is pruned). */
int PruneHeight();

/** After the tip moved: delete the oldest block files while the rest is over the target. Cheap when there is nothing to do. */
void PruneBlockFiles();

/** True if a scan of the chain from this block on would meet a block whose data was pruned (a wallet rescan cannot be complete). */
bool RescanNeedsPrunedBlocks(const CBlockIndex* pindexStart);

/** The size at which block files are closed and a new one started: about 2 GB, or 64 MiB when pruning (so that files can go one by one). */
uint64 BlockFileThreshold();

#endif
