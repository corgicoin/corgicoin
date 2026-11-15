// The unspent-output set (the "chainstate") and the undo data of each block, in LevelDB (8.1 steps 3 and 4).
//
// The node still decides what is valid from the transaction index in blkindex.dat. This set is kept in step with the chain beside it
// ("shadow mode"): it is built from the same blocks, at the same commits, and gettxoutsetinfo coins must give the same hash as the
// index and the blocks. When they have agreed for a release it can take over the index's reads.
//
// Layout of the database (<datadir>/chainstate):
//   'c' + txid          CCoins of a transaction that still has an unspent output
//   'u' + block hash    CBlockUndo: what the block's inputs spent, so it can be disconnected
//   'B'                 the block hash the set is for (the tip of the chain it was last committed at)
#ifndef CORGICOIN_COINS_H
#define CORGICOIN_COINS_H

#include "main.h"

#include <functional>

/** The outputs of one transaction that are still unspent. A spent output is a null CTxOut (value -1). */
struct CCoins
{
    bool fCoinBase;
    int nHeight;                    // the block that holds the transaction
    std::vector<CTxOut> vout;

    CCoins() : fCoinBase(false), nHeight(0) {}

    IMPLEMENT_SERIALIZE
    (
        READWRITE(fCoinBase);
        READWRITE(nHeight);
        READWRITE(vout);
    )

    static bool IsSpentOut(const CTxOut& txout) { return txout.nValue == -1; }
    bool IsAvailable(unsigned int n) const { return n < vout.size() && !IsSpentOut(vout[n]); }
    bool IsPruned() const
    {
        for (const CTxOut& txout : vout)
            if (!IsSpentOut(txout))
                return false;
        return true;
    }
};

/** One spent input: the output it took, and what is needed to put the whole CCoins back if it was the last one left. */
struct CTxInUndo
{
    CTxOut txout;
    bool fCoinBase;
    int nHeight;
    unsigned int nOutputs;          // how many outputs the spent transaction has

    CTxInUndo() : fCoinBase(false), nHeight(0), nOutputs(0) {}

    IMPLEMENT_SERIALIZE
    (
        READWRITE(txout);
        READWRITE(fCoinBase);
        READWRITE(nHeight);
        READWRITE(nOutputs);
    )
};

/** What a block spent, input by input, in the order of the block (coinbase excluded). */
struct CBlockUndo
{
    std::vector<CTxInUndo> vprevout;

    IMPLEMENT_SERIALIZE
    (
        READWRITE(vprevout);
    )
};

// All of these run under cs_main, from the places the block code commits to the index.

/** Open the database. If the set is not the one for the chain the index ends on (first run, a crash, a copy of an old data directory),
 *  rebuild it by replaying the chain's blocks. False if the database cannot be opened (the node carries on without it). */
bool CoinsInit();
void CoinsShutdown();
bool CoinsEnabled();

/** The index transaction begins, commits or is rolled back: the changes made between are applied, or dropped, with it. */
void CoinsTxnBegin();
void CoinsTxnCommit();
void CoinsTxnAbort();
/** The tip the index transaction leaves the chain on. */
void CoinsSetBest(const uint256& hashBlock);

/** A block is connected one transaction at a time, so a later one sees the outputs of an earlier one in the same block.
 *  CoinsCheckInputs compares what the index path has just accepted for a transaction with what the set holds: every input must be an
 *  unspent output of the set with the same value and script, and a coinbase must be as mature by the set's height as by the index's. A
 *  difference is counted (and logged): it means the set cannot yet be trusted to decide validity. */
void CoinsCheckInputs(const CTransaction& tx, const MapPrevTx& mapInputs, const CBlockIndex* pindex);
void CoinsConnectTx(const CTransaction& tx, int nHeight, CBlockUndo& undo);
void CoinsEndBlock(const CBlockIndex* pindex, const CBlockUndo& undo);
/** How many differences CoinsCheckInputs has found since the node started. */
uint64 CoinsCheckFailures();
void CoinsDisconnectBlock(const CBlock& block, const CBlockIndex* pindex);

/** Calls fn for every transaction that has unspent outputs, in key order. */
bool CoinsForEach(const std::function<bool(const uint256&, const CCoins&)>& fn);
/** The tip the set is for (null if there is none). */
uint256 CoinsBestBlock();

#endif
