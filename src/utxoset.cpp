// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// gettxoutsetinfo: the set of unspent transaction outputs of the active chain, worked out in either of two independent ways, and a
// hash of it. This is the reference any change to how the node stores or looks up coins is checked against: both ways must give
// the same hash, and so must the node before and after the change.

#include "corgicoinrpc.h"
#include "db.h"
#include "main.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <set>

using namespace std;
using namespace json_spirit;

extern Object JSONRPCError(int code, const string& message);
extern Value ValueFromAmount(int64 amount);

namespace {

typedef std::pair<uint256, unsigned int> OutKey;

struct UtxoSummary
{
    std::map<OutKey, CTxOut> mapCoins;
    uint64 nBogusSpends = 0;            // a spend of an output the replay did not know of (blocks mode)
};

// The set read from the transaction index: every output that no later transaction is recorded as spending.
bool FromIndex(UtxoSummary& out, std::string& strError)
{
    CTxDB txdb("r");
    uint64 nUnreadable = 0;
    bool fOk = txdb.ForEachTxIndex([&](const uint256& hash, const CTxIndex& txindex) {
        bool fAnyUnspent = false;
        for (const CDiskTxPos& spent : txindex.vSpent)
            fAnyUnspent |= spent.IsNull();
        if (!fAnyUnspent)
            return true;
        CTransaction tx;
        if (!tx.ReadFromDisk(txindex.pos))
        {
            nUnreadable++;
            return true;
        }
        for (unsigned int n = 0; n < tx.vout.size() && n < txindex.vSpent.size(); n++)
            if (txindex.vSpent[n].IsNull())
                out.mapCoins[OutKey(hash, n)] = tx.vout[n];
        return true;
    });
    if (!fOk)
        strError = "the transaction index could not be read to the end";
    else if (nUnreadable)
        strError = strprintf("%llu transactions named by the index could not be read from the block files", (unsigned long long)nUnreadable);
    return strError.empty();
}

// The set worked out from the blocks alone, applying them from the genesis block in order. It does not look at the index.
bool FromBlocks(UtxoSummary& out, std::string& strError)
{
    std::vector<CBlockIndex*> vChain;
    for (CBlockIndex* p = pindexBest; p; p = p->pprev)
        vChain.push_back(p);
    for (auto it = vChain.rbegin(); it != vChain.rend(); ++it)
    {
        CBlock block;
        if (!block.ReadFromDisk(*it, true))
        {
            strError = strprintf("block %d could not be read", (*it)->nHeight);
            return false;
        }
        for (const CTransaction& tx : block.vtx)
        {
            if (!tx.IsCoinBase())
                for (const CTxIn& txin : tx.vin)
                    if (out.mapCoins.erase(OutKey(txin.prevout.hash, txin.prevout.n)) == 0)
                        out.nBogusSpends++;
            const uint256 hash = tx.GetHash();
            for (unsigned int n = 0; n < tx.vout.size(); n++)
                out.mapCoins[OutKey(hash, n)] = tx.vout[n];
        }
    }
    return true;
}

} // namespace

Value gettxoutsetinfo(const Array& params, bool fHelp)
{
    if (fHelp || params.size() > 1)
        throw runtime_error(
            "gettxoutsetinfo [index|blocks]\n"
            "Returns statistics about the unspent transaction outputs of the active chain, and a hash of the whole set (outputs sorted\n"
            "by txid and index, each as txid, index, amount, script). Reading is slow and holds the node's main lock throughout.\n"
            "  index   (default) the set the transaction index records as unspent\n"
            "  blocks  the set found by applying every block from the genesis block in order, which does not use the index\n"
            "The two must agree. Result: {mode, height, bestblock, txouts, transactions, total_amount, hash_serialized, bogus_spends}");
    RPCTypeCheck(params, {str_type});
    std::string strMode = params.empty() ? "index" : params[0].get_str();
    if (strMode != "index" && strMode != "blocks")
        throw JSONRPCError(-8, "mode must be index or blocks");
    if (!pindexBest)
        throw JSONRPCError(-1, "No chain loaded");

    UtxoSummary utxo;
    std::string strError;
    if (!(strMode == "index" ? FromIndex(utxo, strError) : FromBlocks(utxo, strError)))
        throw JSONRPCError(-1, strError);

    // std::map is sorted by (txid, n) with txid compared as a number; the hash must not depend on that, so sort by the bytes
    std::vector<const std::pair<const OutKey, CTxOut>*> vSorted;
    vSorted.reserve(utxo.mapCoins.size());
    for (const auto& kv : utxo.mapCoins)
        vSorted.push_back(&kv);
    std::sort(vSorted.begin(), vSorted.end(), [](const std::pair<const OutKey, CTxOut>* a, const std::pair<const OutKey, CTxOut>* b) {
        int c = memcmp(&a->first.first, &b->first.first, 32);
        return c != 0 ? c < 0 : a->first.second < b->first.second;
    });

    CDataStream ss(SER_GETHASH, 0);
    int64 nTotal = 0;
    std::set<uint256> setTx;
    for (const auto* kv : vSorted)
    {
        ss << kv->first.first << (uint32_t)kv->first.second << (int64_t)kv->second.nValue << kv->second.scriptPubKey;
        nTotal += kv->second.nValue;
        setTx.insert(kv->first.first);
    }
    const uint256 hashSet = Hash(ss.begin(), ss.end());

    Object result;
    result.emplace_back("mode", strMode);
    result.emplace_back("height", (int)pindexBest->nHeight);
    result.emplace_back("bestblock", pindexBest->GetBlockHash().GetHex());
    result.emplace_back("txouts", (int64_t)utxo.mapCoins.size());
    result.emplace_back("transactions", (int64_t)setTx.size());
    result.emplace_back("total_amount", ValueFromAmount(nTotal));
    result.emplace_back("hash_serialized", hashSet.GetHex());
    result.emplace_back("bogus_spends", (int64_t)utxo.nBogusSpends);
    return result;
}
