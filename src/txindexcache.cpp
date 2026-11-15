#include "main.h"

bool CTxIndexCache::Read(const uint256& hash, CTxIndex& txindex)
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

bool CTxIndexCache::ReadDb(const uint256& hash, CTxIndex& txindex)
{
    return txdb.ReadTxIndex(hash, txindex);
}

void CTxIndexCache::Write(const uint256& hash, const CTxIndex& txindex)
{
    setErased.erase(hash);
    mapDirty[hash] = txindex;
}

void CTxIndexCache::Erase(const uint256& hash)
{
    mapDirty.erase(hash);
    setErased.insert(hash);
}

bool CTxIndexCache::Flush()
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
