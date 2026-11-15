// A write-back cache over the transaction index (CTxIndex records in blkindex.dat).
//
// Connecting or disconnecting a block reads and changes the index record of every transaction it touches. They go through this
// cache, and reach the database in one pass, in Flush(), at the point the block code used to write them. Nothing about what is
// stored changes; this is the seam that the undo data and the coin database of 8.1 steps 3 to 5 replace.
//
// Reads see the cache first, then the database. An erased record reads as absent even if the database still has it.
#ifndef CORGICOIN_TXINDEXCACHE_H
#define CORGICOIN_TXINDEXCACHE_H

#include "db.h"

#include <map>
#include <set>

class CTxIndexCache
{
public:
    explicit CTxIndexCache(CTxDB& txdbIn) : txdb(txdbIn) {}

    // The record as it is now: changed in the cache, else in the database. False if erased or not there.
    bool Read(const uint256& hash, CTxIndex& txindex)
    {
        auto it = mapDirty.find(hash);
        if (it != mapDirty.end())
        {
            txindex = it->second;
            return true;
        }
        if (setErased.count(hash))
            return false;
        return txdb.ReadTxIndex(hash, txindex);
    }

    // The record in the database only, ignoring what this cache holds (the BIP30 check asks about earlier blocks, not this one).
    bool ReadDb(const uint256& hash, CTxIndex& txindex) { return txdb.ReadTxIndex(hash, txindex); }

    void Write(const uint256& hash, const CTxIndex& txindex)
    {
        setErased.erase(hash);
        mapDirty[hash] = txindex;
    }

    void Erase(const uint256& hash)
    {
        mapDirty.erase(hash);
        setErased.insert(hash);
    }

    // What FetchInputs and ConnectInputs take as the changes proposed so far.
    std::map<uint256, CTxIndex>& Dirty() { return mapDirty; }

    // Write the changes to the database; false if one fails. The cache is empty after.
    bool Flush()
    {
        for (const auto& mi : mapDirty)
            if (!txdb.UpdateTxIndex(mi.first, mi.second))
                return false;
        for (const uint256& hash : setErased)
            txdb.EraseTxIndexByHash(hash);      // as before: an absent record is not an error
        mapDirty.clear();
        setErased.clear();
        return true;
    }

private:
    CTxDB& txdb;
    std::map<uint256, CTxIndex> mapDirty;
    std::set<uint256> setErased;
};

#endif
