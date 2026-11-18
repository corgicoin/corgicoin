// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "coins.h"
#include "util.h"
#include "prune.h"

#include <leveldb/db.h>
#include <leveldb/write_batch.h>

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>

using namespace std;

namespace {

std::mutex mutexCoins;
leveldb::DB* pdb = nullptr;

// the changes of the index transaction that is open
std::map<uint256, std::optional<CCoins>> mapPending;     // nullopt: the transaction has no unspent output left
std::map<uint256, CBlockUndo> mapPendingUndo;
std::set<uint256> setPendingUndoErase;
uint256 hashPendingBest;
bool fHavePendingBest = false;
uint64 nCheckFailures = 0;
uint64 nBlocksFromSet = 0;
bool fStale = false;                // a write failed: the set is behind the index until the next start rebuilds it
bool fTxnBroken = false;            // a change in this transaction could not be applied: the set must be rebuilt once it commits

std::string Key(char chType, const uint256& hash)
{
    std::string strKey(1, chType);
    strKey.append(reinterpret_cast<const char*>(&hash), 32);
    return strKey;
}

template<typename T>
bool Get(char chType, const uint256& hash, T& value)
{
    std::string strValue;
    if (!pdb->Get(leveldb::ReadOptions(), Key(chType, hash), &strValue).ok())
        return false;
    try {
        CDataStream ss(strValue.data(), strValue.data() + strValue.size(), SER_DISK, CLIENT_VERSION);
        ss >> value;
    } catch (const std::exception&) {
        return false;
    }
    return true;
}

template<typename T>
void Put(leveldb::WriteBatch& batch, char chType, const uint256& hash, const T& value)
{
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    ss << value;
    batch.Put(Key(chType, hash), leveldb::Slice(ss.str()));
}

bool GetCoins(const uint256& hash, CCoins& coins)
{
    auto it = mapPending.find(hash);
    if (it != mapPending.end())
    {
        if (!it->second)
            return false;
        coins = *it->second;
        return true;
    }
    return Get('c', hash, coins);
}

void SetCoins(const uint256& hash, const CCoins& coins)
{
    if (coins.IsPruned())
        mapPending[hash] = std::nullopt;
    else
        mapPending[hash] = coins;
}

bool GetUndo(const uint256& hashBlock, CBlockUndo& undo)
{
    auto it = mapPendingUndo.find(hashBlock);
    if (it != mapPendingUndo.end())
    {
        undo = it->second;
        return true;
    }
    return Get('u', hashBlock, undo);
}

void Broken(const char* pszWhat, const uint256& hash)
{
    LogPrintf("COINS: %s %s: the unspent set no longer matches the chain; it will be rebuilt\n", pszWhat, hash.ToString().substr(0, 20).c_str());
    fTxnBroken = true;
}

// the effect of one transaction on the pending set, and the undo data it needs
void ApplyConnectTx(const CTransaction& tx, int nHeight, CBlockUndo& undo)
{
    if (!tx.IsCoinBase())
    {
        for (const CTxIn& txin : tx.vin)
        {
            CCoins coins;
            if (!GetCoins(txin.prevout.hash, coins) || !coins.IsAvailable(txin.prevout.n))
            {
                Broken("spent output not in the set", txin.prevout.hash);
                return;
            }
            CTxInUndo u;
            u.txout = coins.vout[txin.prevout.n];
            u.fCoinBase = coins.fCoinBase;
            u.nHeight = coins.nHeight;
            u.nOutputs = coins.vout.size();
            undo.vprevout.push_back(u);
            coins.vout[txin.prevout.n].SetNull();
            SetCoins(txin.prevout.hash, coins);
        }
    }
    CCoins created;
    created.fCoinBase = tx.IsCoinBase();
    created.nHeight = nHeight;
    created.vout = tx.vout;
    SetCoins(tx.GetHash(), created);
}

void ApplyConnect(const CBlock& block, int nHeight, CBlockUndo& undo)
{
    for (const CTransaction& tx : block.vtx)
    {
        ApplyConnectTx(tx, nHeight, undo);
        if (fTxnBroken)
            return;
    }
}

void ApplyDisconnect(const CBlock& block, const uint256& hashBlock, const CBlockUndo& undo)
{
    size_t nUndo = undo.vprevout.size();
    for (int i = (int)block.vtx.size() - 1; i >= 0; i--)
    {
        const CTransaction& tx = block.vtx[i];
        const uint256 hash = tx.GetHash();
        // later transactions of this block are already taken back, so what is left of this one is exactly what it created
        CCoins created;
        created.vout = tx.vout;
        if (!created.IsPruned())
        {
            CCoins coins;
            if (!GetCoins(hash, coins) || !(coins.vout == tx.vout))
            {
                Broken("outputs of a disconnected transaction differ", hash);
                return;
            }
        }
        mapPending[hash] = std::nullopt;
        if (!tx.IsCoinBase())
        {
            for (int j = (int)tx.vin.size() - 1; j >= 0; j--)
            {
                if (nUndo == 0)
                {
                    Broken("undo data too short for block", hashBlock);
                    return;
                }
                const CTxInUndo& u = undo.vprevout[--nUndo];
                const COutPoint& prevout = tx.vin[j].prevout;
                CCoins prev;
                if (!GetCoins(prevout.hash, prev))
                {
                    prev = CCoins();
                    prev.fCoinBase = u.fCoinBase;
                    prev.nHeight = u.nHeight;
                    prev.vout.assign(u.nOutputs, CTxOut());     // all spent, for now
                }
                if (prevout.n >= prev.vout.size() || prev.IsAvailable(prevout.n))
                {
                    Broken("restoring an output that is not spent", prevout.hash);
                    return;
                }
                prev.vout[prevout.n] = u.txout;
                SetCoins(prevout.hash, prev);
            }
        }
    }
    if (nUndo != 0)
        Broken("undo data too long for block", hashBlock);
}

// write what is pending, and the tip it leaves the set on
bool WritePending(const uint256& hashBest)
{
    leveldb::WriteBatch batch;
    for (const auto& kv : mapPending)
    {
        if (kv.second)
            Put(batch, 'c', kv.first, *kv.second);
        else
            batch.Delete(Key('c', kv.first));
    }
    for (const auto& kv : mapPendingUndo)
        Put(batch, 'u', kv.first, kv.second);
    for (const uint256& hash : setPendingUndoErase)
        batch.Delete(Key('u', hash));
    batch.Put(std::string(1, 'B'), leveldb::Slice(reinterpret_cast<const char*>(&hashBest), 32));
    leveldb::WriteOptions options;
    options.sync = false;           // a lost tail leaves the tip behind the index's: found at the next start, and rebuilt
    const bool fOk = pdb->Write(options, &batch).ok();
    mapPending.clear();
    mapPendingUndo.clear();
    setPendingUndoErase.clear();
    return fOk;
}

void ClearPending()
{
    mapPending.clear();
    mapPendingUndo.clear();
    setPendingUndoErase.clear();
    fHavePendingBest = false;
    fTxnBroken = false;
}

void CloseDb()
{
    delete pdb;
    pdb = nullptr;
}

bool OpenDb(bool fWipe)
{
    CloseDb();
    const std::filesystem::path path = GetDataDir() / "chainstate";
    if (fWipe)
        leveldb::DestroyDB(path.string(), leveldb::Options());
    std::error_code ec;
    std::filesystem::create_directories(path, ec);
    leveldb::Options options;
    options.create_if_missing = true;
    options.compression = leveldb::kNoCompression;
    leveldb::Status status = leveldb::DB::Open(options, path.string(), &pdb);
    if (!status.ok())
    {
        LogPrintf("COINS: cannot open %s: %s\n", path.string().c_str(), status.ToString().c_str());
        pdb = nullptr;
        return false;
    }
    return true;
}

bool ReadBest(uint256& hashBest)
{
    std::string str;
    if (!pdb->Get(leveldb::ReadOptions(), std::string(1, 'B'), &str).ok() || str.size() != 32)
        return false;
    memcpy(&hashBest, str.data(), 32);
    return true;
}

// Build the set and the undo data by applying the blocks of the chain that ends at ptip, from the genesis block, in order
bool Rebuild(const CBlockIndex* ptip)
{
    LogPrintf("COINS: rebuilding the unspent set from the blocks up to height %d\n", ptip ? ptip->nHeight : -1);
    if (!OpenDb(true))
        return false;
    ClearPending();
    std::vector<const CBlockIndex*> vChain;
    for (const CBlockIndex* p = ptip; p; p = p->pprev)
        vChain.push_back(p);
    int nSince = 0;
    for (auto it = vChain.rbegin(); it != vChain.rend(); ++it)
    {
        const CBlockIndex* pindex = *it;
        if (pindex->nHeight > 0)          // the genesis block's output can never be spent and the index never holds it
        {
            CBlock block;
            if (!block.ReadFromDisk(pindex, true))
            {
                LogPrintf("COINS: block %d could not be read while rebuilding\n", pindex->nHeight);
                return false;
            }
            CBlockUndo undo;
            ApplyConnect(block, pindex->nHeight, undo);
            if (fTxnBroken)
            {
                LogPrintf("COINS: the chain does not apply cleanly at height %d\n", pindex->nHeight);
                return false;
            }
            mapPendingUndo[pindex->GetBlockHash()] = undo;
        }
        if (++nSince >= 500 || pindex == ptip)
        {
            if (!WritePending(pindex->GetBlockHash()))
                return false;
            nSince = 0;
        }
    }
    LogPrintf("COINS: rebuilt\n");
    return true;
}

// The set is for a block that is in the block index but is not the chain's tip (a crash between the commit of the index and the commit of the
// set, in either order, perhaps in the middle of a reorganisation): take the blocks of the set's own branch off, newest first, with the undo
// data kept for each, back to the fork point with the chain, then apply the chain's blocks above it: instead of every block since the first.
// False, with the set as it was (or at a consistent earlier tip), if a block cannot be read, its undo data is missing or a block does not
// apply; the caller then rebuilds, which a pruned node cannot (it does not try, and leaves the set alone: see CoinsInit).
bool CatchUp(const CBlockIndex* pMarker, const CBlockIndex* ptip)
{
    // the fork point: the newest block that both are built on
    const CBlockIndex* a = pMarker;
    const CBlockIndex* b = ptip;
    while (a && b && a != b)
    {
        if (a->nHeight > b->nHeight)
            a = a->pprev;
        else if (b->nHeight > a->nHeight)
            b = b->pprev;
        else
        {
            a = a->pprev;
            b = b->pprev;
        }
    }
    if (!a || a != b)
        return false;
    const CBlockIndex* pFork = a;
    std::vector<const CBlockIndex*> vChain;
    for (const CBlockIndex* p = ptip; p && p != pFork; p = p->pprev)
        vChain.push_back(p);
    ClearPending();
    int nBack = 0;
    for (const CBlockIndex* p = pMarker; p != pFork; p = p->pprev)
    {
        CBlock block;
        CBlockUndo undo;
        if (!block.ReadFromDisk(p, true, false) || !GetUndo(p->GetBlockHash(), undo))
        {
            LogPrintf("COINS: block %d of the set's own branch cannot be taken off (no block data or no undo data)\n", p->nHeight);
            ClearPending();
            return false;
        }
        ApplyDisconnect(block, p->GetBlockHash(), undo);
        if (fTxnBroken)
        {
            LogPrintf("COINS: the set's own branch does not come off cleanly at height %d\n", p->nHeight);
            ClearPending();
            return false;
        }
        mapPendingUndo.erase(p->GetBlockHash());
        setPendingUndoErase.insert(p->GetBlockHash());
        nBack++;
    }
    LogPrintf("COINS: the set is %d blocks off the chain's branch and %d behind its tip; fixing\n", nBack, (int)vChain.size());
    if (vChain.empty())
    {
        // only blocks to take off: the set is now for the fork point, which is the tip
        if (!WritePending(ptip->GetBlockHash()))
        {
            ClearPending();
            return false;
        }
        LogPrintf("COINS: caught up\n");
        return true;
    }
    int nSince = 0;
    for (auto it = vChain.rbegin(); it != vChain.rend(); ++it)
    {
        const CBlockIndex* pindex = *it;
        CBlock block;
        if (!block.ReadFromDisk(pindex, true))
        {
            LogPrintf("COINS: block %d could not be read while catching up\n", pindex->nHeight);
            ClearPending();
            return false;
        }
        CBlockUndo undo;
        ApplyConnect(block, pindex->nHeight, undo);
        if (fTxnBroken)
        {
            LogPrintf("COINS: the chain does not apply cleanly at height %d\n", pindex->nHeight);
            ClearPending();
            return false;
        }
        mapPendingUndo[pindex->GetBlockHash()] = undo;
        if (++nSince >= 500 || pindex == ptip)
        {
            if (!WritePending(pindex->GetBlockHash()))
            {
                ClearPending();
                return false;
            }
            nSince = 0;
        }
    }
    LogPrintf("COINS: caught up\n");
    return true;
}

void GiveUp()
{
    LogPrintf("COINS: the unspent set is not available; the node runs on the transaction index alone\n");
    CloseDb();
}

} // namespace

bool CoinsEnabled()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    return pdb != nullptr;
}

void CoinsMarkBroken(const char* pszWhy)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (pdb)
        Broken(pszWhy, uint256(0));
}

bool CoinsUsable()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    return pdb != nullptr && !fStale && !fTxnBroken;
}

CoinsFetchResult CoinsFetchInputs(const CTransaction& tx, std::vector<CCoinInput>& vIn, unsigned int& nBad)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    vIn.clear();
    for (unsigned int i = 0; i < tx.vin.size(); i++)
    {
        const COutPoint& prevout = tx.vin[i].prevout;
        CCoins coins;
        nBad = i;
        if (!GetCoins(prevout.hash, coins))
            return COINS_FETCH_MISSING;             // never there, or every output of it is spent
        if (prevout.n >= coins.vout.size())
            return COINS_FETCH_RANGE;
        if (!coins.IsAvailable(prevout.n))
            return COINS_FETCH_SPENT;
        CCoinInput in;
        in.txout = coins.vout[prevout.n];
        in.fCoinBase = coins.fCoinBase;
        in.nHeight = coins.nHeight;
        vIn.push_back(in);
    }
    return COINS_FETCH_OK;
}

bool CoinsLookup(const uint256& hash, CCoins& coins)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb || fStale || fTxnBroken)
        return false;           // a set that is behind the chain, or out of step in this transaction, is not an answer
    return GetCoins(hash, coins);
}

bool CoinsHaveUnspent(const uint256& hash)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    CCoins coins;
    return GetCoins(hash, coins);
}

bool CoinsInit()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    fStale = false;
    ClearPending();
    if (!OpenDb(false))
        return false;
    uint256 hashBest;
    const bool fHave = ReadBest(hashBest);
    const uint256 hashChain = pindexBest ? pindexBest->GetBlockHash() : uint256(0);
    // a chain that is only the genesis block (or nothing) has no coins to build
    const bool fEmptyChain = !pindexBest || pindexBest->nHeight == 0;
    if (fHave ? hashBest == hashChain : fEmptyChain)
        return true;
    if (fHave)
    {
        auto mi = mapBlockIndex.find(hashBest);
        if (mi != mapBlockIndex.end() && CatchUp(mi->second, pindexBest))
            return true;
    }
    if (fPruneMode)
    {
        // A pruned node cannot rebuild the set (it needs every block), and a rebuild starts by wiping it: leave it as it is, say why, and stop.
        LogPrintf("COINS: the set cannot be brought up to date from the blocks that are left, and a pruned node cannot rebuild it\n");
        GiveUp();
        return false;
    }
    if (!Rebuild(pindexBest))
    {
        GiveUp();
        return false;
    }
    return true;
}

void CoinsShutdown()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    CloseDb();
}

void CoinsTxnBegin()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    ClearPending();
}

void CoinsTxnAbort()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    ClearPending();
}

void CoinsSetBest(const uint256& hashBlock)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    hashPendingBest = hashBlock;
    fHavePendingBest = true;
}

void CoinsTxnCommit()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb)
    {
        ClearPending();
        return;
    }
    const bool fBroken = fTxnBroken;
    const bool fHaveBest = fHavePendingBest;
    const uint256 hashBest = hashPendingBest;
    if (!fHaveBest)
    {
        ClearPending();         // an index transaction that does not move the tip (nothing for the set)
        return;
    }
    if (!fBroken)
    {
        if (fStale)
        {
            // an earlier write failed, so the set lacks that block's changes: do not move its marker on to this block, or the next start
            // would take the set for the chain's. The marker stays where it was, and the next start rebuilds.
            ClearPending();
            return;
        }
        if (!WritePending(hashBest))
        {
            LogPrintf("COINS: writing the unspent set failed; it will be rebuilt at the next start\n");
            fStale = true;
            if (fPruneMode)
                FatalChainstateError("The unspent-output set could not be written. A pruned node cannot go on without it, so it is stopping; the set is brought up to date from the blocks at the next start.");
        }
        ClearPending();
        return;
    }
    ClearPending();
    auto it = mapBlockIndex.find(hashBest);
    if (it == mapBlockIndex.end() || !Rebuild(it->second))
        GiveUp();
}

void CoinsConnectTx(const CTransaction& tx, int nHeight, CBlockUndo& undo)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb || fTxnBroken)
        return;
    ApplyConnectTx(tx, nHeight, undo);
}

void CoinsEndBlock(const CBlockIndex* pindex, const CBlockUndo& undo)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb || fTxnBroken)
        return;
    mapPendingUndo[pindex->GetBlockHash()] = undo;
}

void CoinsNoteBlockFromSet()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    nBlocksFromSet++;
}

uint64 CoinsBlocksFromSet()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    return nBlocksFromSet;
}

uint64 CoinsCheckFailures()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    return nCheckFailures;
}

void CoinsCheckInputs(const CTransaction& tx, const MapPrevTx& mapInputs, const CBlockIndex* pindex)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb || fTxnBroken || tx.IsCoinBase())
        return;
    for (const CTxIn& txin : tx.vin)
    {
        const char* pszWhy = nullptr;
        CCoins coins;
        auto it = mapInputs.find(txin.prevout.hash);
        if (it == mapInputs.end() || txin.prevout.n >= it->second.second.vout.size())
            pszWhy = "the index path has no such input";
        else if (!GetCoins(txin.prevout.hash, coins) || !coins.IsAvailable(txin.prevout.n))
            pszWhy = "the index accepted an input that is not an unspent output of the set";
        else
        {
            const CTxOut& txoutIndex = it->second.second.vout[txin.prevout.n];
            const CTxOut& txoutCoins = coins.vout[txin.prevout.n];
            if (txoutIndex.nValue != txoutCoins.nValue || !(txoutIndex.scriptPubKey == txoutCoins.scriptPubKey))
                pszWhy = "the output differs in value or script";
            else if (coins.fCoinBase != it->second.second.IsCoinBase())
                pszWhy = "the set and the index disagree on whether the output is a coinbase's";
            else if (coins.fCoinBase && pindex->nHeight - coins.nHeight < COINBASE_MATURITY)
                pszWhy = "the index accepted a coinbase the set holds as immature";
        }
        if (pszWhy)
        {
            nCheckFailures++;
            LogPrintf("COINS CHECK: %s (%s:%u, in block %d)\n", pszWhy, txin.prevout.hash.ToString().substr(0, 20).c_str(), txin.prevout.n, pindex->nHeight);
        }
    }
}

void CoinsDisconnectBlock(const CBlock& block, const CBlockIndex* pindex)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb || fTxnBroken)
        return;
    const uint256 hash = pindex->GetBlockHash();
    CBlockUndo undo;
    if (!GetUndo(hash, undo))
    {
        Broken("no undo data for block", hash);
        return;
    }
    ApplyDisconnect(block, hash, undo);
    if (!fTxnBroken)
    {
        mapPendingUndo.erase(hash);
        setPendingUndoErase.insert(hash);
    }
}

bool CoinsForEach(const std::function<bool(const uint256&, const CCoins&)>& fn)
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    if (!pdb)
        return false;
    std::unique_ptr<leveldb::Iterator> it(pdb->NewIterator(leveldb::ReadOptions()));
    for (it->Seek(std::string(1, 'c')); it->Valid() && it->key().size() == 33 && it->key()[0] == 'c'; it->Next())
    {
        uint256 hash;
        memcpy(&hash, it->key().data() + 1, 32);
        CCoins coins;
        try {
            CDataStream ss(it->value().data(), it->value().data() + it->value().size(), SER_DISK, CLIENT_VERSION);
            ss >> coins;
        } catch (const std::exception&) {
            return false;
        }
        if (!fn(hash, coins))
            return false;
    }
    return it->status().ok();
}

uint256 CoinsBestBlock()
{
    std::lock_guard<std::mutex> lock(mutexCoins);
    uint256 hashBest = 0;
    if (pdb)
        ReadBest(hashBest);
    return hashBest;
}
