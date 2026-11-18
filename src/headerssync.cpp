// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// Headers-first sync (-headersfirst).
//
// Without it a node learns the chain by asking one peer for "what comes after this" (getblocks), 500 blocks at a time, and takes
// each block from the peer that announced it. With it the node first downloads only the headers, checks each one (its proof of
// work, which for a merged-mined block is the parent chain's work and is carried in the header; its difficulty; its time; the
// checkpoints), and so knows which chain has the most work before it has a single block. Then it fetches the blocks of that
// chain from several peers at once, a window ahead of its tip, and drops a peer that does not deliver.
//
// A header costs the sender real work (it must meet the difficulty the chain requires at that point), so what a peer can make us
// hold is bounded by the work it does. Headers live in mapHeaderIndex, apart from mapBlockIndex: nothing that reads the block
// index (the wallet, the RPC, the miner, a reorganisation) ever sees one. A block, when it arrives, goes through the usual
// ProcessBlock, which checks everything again.
//
// Everything here runs with cs_main held.

#include "main.h"
#include "net.h"
#include "checkpoints.h"
#include "util.h"

#include <algorithm>
#include <set>

using namespace std;

std::map<uint256, CBlockIndex*> mapHeaderIndex;
CBlockIndex* pindexBestHeader = nullptr;

namespace {

// the best header chain by height, genesis first. An entry may be a block index or a header index entry; what matters is its hash.
std::vector<CBlockIndex*> vHeaderChain;

constexpr unsigned int MAX_HEADERS_RESULTS = 2000;
constexpr size_t MAX_HEADER_INDEX = 4000000;        // headers held that are not blocks: far above any real chain's length
constexpr int BLOCK_DOWNLOAD_WINDOW = 512;          // below MAX_ORPHAN_BLOCKS, so blocks that arrive early do not push each other out
constexpr size_t MAX_BLOCKS_IN_FLIGHT_PER_PEER = 64;      // the message loop ticks every 100 ms, so 16 made an initial download slower than getblocks
constexpr int MAX_HEADER_SYNC_PEERS = 3;            // peers asked for the same headers at once

bool SameBlock(const CBlockIndex* a, const CBlockIndex* b)
{
    return a && b && *a->phashBlock == *b->phashBlock;
}

CBlockIndex* LookupAnyIndex(const uint256& hash)
{
    auto mi = mapBlockIndex.find(hash);
    if (mi != mapBlockIndex.end())
        return mi->second;
    auto mh = mapHeaderIndex.find(hash);
    return mh != mapHeaderIndex.end() ? mh->second : nullptr;
}

void SetBestHeader(CBlockIndex* pindex)
{
    pindexBestHeader = pindex;
    vHeaderChain.resize(pindex->nHeight + 1, nullptr);
    for (CBlockIndex* p = pindex; p; p = p->pprev)
    {
        if (SameBlock(vHeaderChain[p->nHeight], p))
            break;                      // from here down the vector is already this chain
        vHeaderChain[p->nHeight] = p;
    }
}

// the header chain starts from the block chain the node already has
void EnsureHeaderChain()
{
    if (pindexBest && (!pindexBestHeader || pindexBest->bnChainWork > pindexBestHeader->bnChainWork))
        SetBestHeader(pindexBest);
}

enum HeaderResult { HEADER_OK, HEADER_BAD, HEADER_UNCONNECTED };

HeaderResult AcceptHeader(const CBlock& hdr, CBlockIndex** ppindex, int& nDoS)
{
    nDoS = 0;
    const uint256 hash = hdr.GetHash();
    if (CBlockIndex* pindexKnown = LookupAnyIndex(hash))
    {
        *ppindex = pindexKnown;
        if (pindexKnown->fFailedChain)
        {
            nDoS = 10;
            return HEADER_BAD;
        }
        return HEADER_OK;
    }

    CBlockIndex* pindexPrev = LookupAnyIndex(hdr.hashPrevBlock);
    if (!pindexPrev)
        return HEADER_UNCONNECTED;
    if (pindexPrev->fFailedChain)
    {
        nDoS = 100;
        return HEADER_BAD;
    }
    const int nHeight = pindexPrev->nHeight + 1;

    // the proof of work, which for a merged-mined block is the parent chain's (the proof travels in the header)
    if (!CheckAuxProofOfWork(hdr, hdr.nBits))
    {
        nDoS = 50;
        return HEADER_BAD;
    }
    if (hdr.nBits != GetNextWorkRequiredForHeader(pindexPrev, &hdr))
    {
        nDoS = 100;
        LogPrintf("headers-first: header %s has the wrong difficulty at %d\n", hash.ToString().substr(0, 20).c_str(), nHeight);
        return HEADER_BAD;
    }
    if (nHeight >= GetAuxPowForkHeight())
    {
        if (hdr.GetChainId() != AUXPOW_CHAIN_ID)
        {
            nDoS = 100;
            return HEADER_BAD;
        }
    }
    else if (hdr.IsAuxPow())
    {
        nDoS = 100;
        return HEADER_BAD;
    }
    // times: no score, an honest peer with a wrong clock gets here
    if (hdr.GetBlockTime() <= pindexPrev->GetMedianTimePast() || hdr.GetBlockTime() > GetAdjustedTime() + 2 * 60 * 60 ||
        (nHeight >= GetLwmaForkHeight() && hdr.GetBlockTime() > GetAdjustedTime() + LWMA_FUTURE_TIME_LIMIT))
        return HEADER_BAD;
    if (!Checkpoints::CheckBlock(nHeight, hash))
    {
        nDoS = 100;
        return HEADER_BAD;
    }
    if (mapHeaderIndex.size() >= MAX_HEADER_INDEX)
    {
        LogPrintf("headers-first: the header index is full (%u), not keeping %s\n", (unsigned)mapHeaderIndex.size(), hash.ToString().substr(0, 20).c_str());
        return HEADER_BAD;
    }

    CBlock copy(hdr);
    CBlockIndex* pindexNew = new CBlockIndex(0, 0, copy);
    auto mi = mapHeaderIndex.insert({hash, pindexNew}).first;
    pindexNew->phashBlock = &mi->first;
    pindexNew->pprev = pindexPrev;
    pindexNew->nHeight = nHeight;
    pindexNew->bnChainWork = pindexPrev->bnChainWork + pindexNew->GetBlockWork();
    pindexNew->fFailedChain = false;
    EnsureHeaderChain();
    if (!pindexBestHeader || pindexNew->bnChainWork > pindexBestHeader->bnChainWork)
        SetBestHeader(pindexNew);
    *ppindex = pindexNew;
    return HEADER_OK;
}

void PushGetHeaders(CNode* pto, CBlockIndex* pindexFrom)
{
    pto->PushMessage("getheaders", CBlockLocator(pindexFrom), uint256(0));
}

// every block asked of any peer and not yet received
std::set<uint256> BlocksInFlight()
{
    std::set<uint256> setInFlight;
    LOCK(cs_vNodes);
    for (CNode* pnode : vNodes)
        for (const auto& kv : pnode->mapBlocksInFlight)
            setInFlight.insert(kv.first);
    return setInFlight;
}

} // namespace

bool HeadersFirstEnabled()
{
    return GetBoolArg("-headersfirst", false);
}

bool HeadersFirstWith(const CNode* pnode)
{
    return pnode && HeadersFirstEnabled() && pnode->nVersion >= HEADERSFIRST_VERSION;
}

size_t HeaderOnlyCount()
{
    return mapHeaderIndex.size();
}

CBlockIndex* HeadersTakeIndexFor(const uint256& hash)
{
    auto mh = mapHeaderIndex.find(hash);
    if (mh == mapHeaderIndex.end())
        return nullptr;
    CBlockIndex* pindex = mh->second;
    mapHeaderIndex.erase(mh);
    return pindex;
}

bool HeadersAssumeValid(const CBlockIndex* pindex)
{
    if (hashAssumeValid == 0 || !pindex || !HeadersFirstEnabled() || !pindexBestHeader)
        return false;
    const CBlockIndex* pAssumed = LookupAnyIndex(hashAssumeValid);
    if (!pAssumed)
        return false;                   // its header has not come yet: nothing is assumed
    auto OnHeaderChain = [](const CBlockIndex* p) {
        return p->nHeight >= 0 && p->nHeight < (int)vHeaderChain.size() && SameBlock(vHeaderChain[p->nHeight], p);
    };
    // the assumed block is on the best header chain, and the block asked about is on it and not above it
    if (!OnHeaderChain(pAssumed) || pindex->nHeight > pAssumed->nHeight || !OnHeaderChain(pindex))
        return false;
    // the best header chain has the work it is supposed to (a chain with less is not believed whatever it assumes)
    if (bnMinimumChainWork > 0 && pindexBestHeader->bnChainWork < bnMinimumChainWork)
        return false;
    // and is well past the block: what is assumed is old (2 weeks, as Bitcoin Core does; regtest can shorten it for the test)
    int64 nGap = 14 * 24 * 60 * 60;
    if (fRegTest && mapArgs.count("-testassumevalidgap"))
        nGap = GetArg("-testassumevalidgap", nGap);
    return (int64)pindexBestHeader->nTime - (int64)pindex->nTime >= nGap;
}

bool HaveHeaderFor(const uint256& hash)
{
    return mapHeaderIndex.count(hash) != 0;
}

bool ProcessHeadersMessage(CNode* pfrom, CDataStream& vRecv)
{
    if (!HeadersFirstWith(pfrom))
        return true;
    // whatever this message holds, the request it answers is over; it is asked again below only if there may be more. (An empty answer, a
    // bad header or one that does not connect used to leave the flag set, and three such peers kept header sync from every other peer.)
    pfrom->fSyncing = false;
    vector<CBlock> vHeaders;
    vRecv >> vHeaders;
    if (vHeaders.size() > MAX_HEADERS_RESULTS)
    {
        pfrom->Misbehaving(20);
        return LogError("headers message size = %u", (unsigned)vHeaders.size());
    }
    if (vHeaders.empty())
        return true;
    EnsureHeaderChain();

    // each header must carry no transactions and follow the one before it
    for (size_t i = 0; i < vHeaders.size(); i++)
    {
        if (!vHeaders[i].vtx.empty() || (i > 0 && vHeaders[i].hashPrevBlock != vHeaders[i - 1].GetHash()))
        {
            pfrom->Misbehaving(20);
            return LogError("headers message: header %u is not a header or does not follow the one before", (unsigned)i);
        }
    }

    CBlockIndex* pindexLast = nullptr;
    for (const CBlock& hdr : vHeaders)
    {
        CBlockIndex* pindex = nullptr;
        int nDoS = 0;
        const HeaderResult r = AcceptHeader(hdr, &pindex, nDoS);
        if (r == HEADER_UNCONNECTED)
        {
            // what we were sent starts somewhere we do not know: answer with where we are, and count it
            if (++pfrom->nUnconnectingHeaders % 10 == 0)
                pfrom->Misbehaving(20);
            if (pindexBestHeader)
                PushGetHeaders(pfrom, pindexBestHeader);
            LogPrintf("headers-first: headers from %s do not connect (%d)\n", pfrom->addr.ToString().c_str(), pfrom->nUnconnectingHeaders);
            return true;
        }
        if (r == HEADER_BAD)
        {
            if (nDoS)
                pfrom->Misbehaving(nDoS);
            LogPrintf("headers-first: bad header from %s, stopping at %s\n", pfrom->addr.ToString().c_str(), hdr.GetHash().ToString().substr(0, 20).c_str());
            return true;
        }
        pindexLast = pindex;
    }
    pfrom->nUnconnectingHeaders = 0;
    if (pindexLast && (!pfrom->pindexBestKnown || pindexLast->bnChainWork > pfrom->pindexBestKnown->bnChainWork))
        pfrom->pindexBestKnown = pindexLast;
    LogPrintf("headers-first: %u headers from %s, best header %d\n", (unsigned)vHeaders.size(), pfrom->addr.ToString().c_str(), pindexBestHeader ? pindexBestHeader->nHeight : -1);

    if (vHeaders.size() == MAX_HEADERS_RESULTS && pindexLast)
    {
        pfrom->fSyncing = true;
        PushGetHeaders(pfrom, pindexLast);          // there may be more
    }
    return true;
}

// A block has been received or has become known: it is no longer being waited for from anyone.
void HeadersFirstBlockArrived(const uint256& hash)
{
    LOCK(cs_vNodes);
    for (CNode* pnode : vNodes)
        pnode->mapBlocksInFlight.erase(hash);
}

void HeadersFirstSendMessages(CNode* pto)
{
    if (!HeadersFirstWith(pto) || !pto->fSuccessfullyConnected || pto->fClient || pto->fOneShot)
        return;
    EnsureHeaderChain();
    if (!pindexBestHeader)
        return;

    // 1. ask a peer that has more than we do for its headers
    if (!pto->fSyncStarted && pto->nStartingHeight > pindexBestHeader->nHeight)
    {
        int nSyncing = 0;
        {
            LOCK(cs_vNodes);
            for (CNode* pnode : vNodes)
                nSyncing += pnode->fSyncing;
        }
        if (nSyncing < MAX_HEADER_SYNC_PEERS)
        {
            pto->fSyncStarted = true;
            pto->fSyncing = true;
            LogPrintf("headers-first: asking %s for headers from %d (its height %d)\n", pto->addr.ToString().c_str(), pindexBestHeader->nHeight, pto->nStartingHeight);
            PushGetHeaders(pto, pindexBestHeader);
        }
    }

    // 1b. a peer whose tip we do not know and that has no more than our best header (it joined after the headers were in, or is level with
    //     us): without its tip it would never be asked for blocks, and sits idle while another peer does all the work (and cannot take over
    //     if that one stalls). Ask once, from the header before our best, so that the answer holds the peer's tip if it is on our chain.
    if (!pto->fSyncStarted && !pto->pindexBestKnown && pto->nStartingHeight >= pindexBestHeader->nHeight && pindexBestHeader->pprev &&
        pindexBestHeader->nHeight > pindexBest->nHeight)
    {
        pto->fSyncStarted = true;
        LogPrintf("headers-first: asking %s for its tip (its height %d)\n", pto->addr.ToString().c_str(), pto->nStartingHeight);
        PushGetHeaders(pto, pindexBestHeader->pprev);
    }

    // 2. a block asked for and not delivered in time: this peer is not doing its part
    const int64 nTimeout = GetArg("-blocktimeout", 120);
    const int64 nNow = GetTime();
    for (const auto& kv : pto->mapBlocksInFlight)
        if (nNow - kv.second > nTimeout)
        {
            LogPrintf("headers-first: %s did not send block %s in %d seconds, disconnecting\n", pto->addr.ToString().c_str(), kv.first.ToString().substr(0, 20).c_str(), (int)nTimeout);
            pto->fDisconnect = true;
            return;
        }

    // 3. blocks of the best header chain this peer has, a window ahead of our tip, that nobody is bringing yet
    if (!pto->pindexBestKnown || pto->pindexBestKnown->bnChainWork <= pindexBest->bnChainWork)
        return;
    const int nPeerHeight = pto->pindexBestKnown->nHeight;
    if (nPeerHeight >= (int)vHeaderChain.size() || !SameBlock(vHeaderChain[nPeerHeight], pto->pindexBestKnown))
        return;                         // it is on another branch than the one we are following; the old getblocks path serves that
    // where our block chain leaves the header chain
    CBlockIndex* pindexFork = pindexBest;
    while (pindexFork && !(pindexFork->nHeight < (int)vHeaderChain.size() && SameBlock(vHeaderChain[pindexFork->nHeight], pindexFork)))
        pindexFork = pindexFork->pprev;
    if (!pindexFork)
        return;
    const int nFirst = pindexFork->nHeight + 1;
    const int nEnd = std::min(nFirst + BLOCK_DOWNLOAD_WINDOW, nPeerHeight + 1);
    if (pto->mapBlocksInFlight.size() >= MAX_BLOCKS_IN_FLIGHT_PER_PEER || nFirst >= nEnd)
        return;

    const std::set<uint256> setInFlight = BlocksInFlight();
    std::vector<CInv> vGetData;
    for (int h = nFirst; h < nEnd && pto->mapBlocksInFlight.size() + vGetData.size() < MAX_BLOCKS_IN_FLIGHT_PER_PEER; h++)
    {
        const uint256 hash = *vHeaderChain[h]->phashBlock;
        if (mapBlockIndex.count(hash) || IsOrphanBlock(hash) || setInFlight.count(hash))
            continue;
        vGetData.push_back(CInv(static_cast<int>(MsgType::Block), hash));
        pto->mapBlocksInFlight[hash] = nNow;
    }
    if (!vGetData.empty())
    {
        LogPrintf("headers-first: asking %s for %u blocks from height %d\n", pto->addr.ToString().c_str(), (unsigned)vGetData.size(),
                  LookupAnyIndex(vGetData.front().hash)->nHeight);
        pto->PushMessage("getdata", vGetData);
    }
}
