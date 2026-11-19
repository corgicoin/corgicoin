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
#include <map>
#include <queue>
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
constexpr int MAX_HEADER_FORK_DEPTH = 2000;         // a header that forks off the best header chain further back than this is refused
constexpr size_t MAX_BRANCH_HEADERS = 50000;        // headers held that are on no branch we follow (the best header chain is not counted)
constexpr int64 HEADERS_RETRY_SECONDS = 60;         // a peer that sent a header that failed a time check is asked again after this
constexpr int64 HEADERS_FALLBACK_SECONDS = 1800;    // after a peer let a headers request go unanswered, peers are synced the old way for this long

// regtest can lower the cap for the test
size_t MaxBranchHeaders()
{
    if (fRegTest && mapArgs.count("-testmaxbranchheaders"))
        return (size_t)std::max<int64>(1, GetArg("-testmaxbranchheaders", MAX_BRANCH_HEADERS));
    return MAX_BRANCH_HEADERS;
}

int MaxForkDepth()
{
    if (fRegTest && mapArgs.count("-testmaxforkdepth"))
        return (int)std::max<int64>(1, GetArg("-testmaxforkdepth", MAX_HEADER_FORK_DEPTH));
    return MAX_HEADER_FORK_DEPTH;
}

size_t nBranchHeaders = 0;                          // header-only entries that were not the best chain when they came in
int64 nHeadersFallbackUntil = 0;

int64 HeaderSyncTimeout()
{
    const int64 n = GetArg("-headersynctimeout", 120);
    return n < 1 ? 120 : n;
}

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

bool OnHeaderChain(const CBlockIndex* p)
{
    return p->nHeight < (int)vHeaderChain.size() && SameBlock(vHeaderChain[p->nHeight], p);
}

// The best header is what a connected peer has told us of, or our own tip: nothing else is worth following. Called when what
// was the best header is no longer one (it descends from a block that failed, or the peer that had it went away or never sent the blocks).
void RepickBestHeader(const CNode* pExclude)
{
    CBlockIndex* pindexCand = (pindexBest && !pindexBest->fFailedChain) ? pindexBest : nullptr;      // (during a rollback the tip may still be the failed block)
    {
        LOCK(cs_vNodes);
        for (CNode* pnode : vNodes)
        {
            CBlockIndex* p = pnode->pindexBestKnown;
            if (pnode == pExclude || pnode->fDisconnect || !p || p->fFailedChain)
                continue;
            if (!pindexCand || p->bnChainWork > pindexCand->bnChainWork)
                pindexCand = p;
        }
    }
    if (pindexCand && pindexCand != pindexBestHeader)
    {
        LogPrintf("headers-first: the best header is now %s at %d (it was %d)\n", pindexCand->phashBlock->ToString().substr(0, 20).c_str(),
                  pindexCand->nHeight, pindexBestHeader ? pindexBestHeader->nHeight : -1);
        SetBestHeader(pindexCand);
        // every peer is asked for headers again from where we are: one that was asked before the best header moved would never be again
        LOCK(cs_vNodes);
        for (CNode* pnode : vNodes)
            pnode->fSyncStarted = false;
    }
}

// The header entries that are on no branch we follow, dropped from the lowest work up (a branch is dropped from its tip back, so no entry
// is left with a parent that is gone) until no more than nTarget are held. What is on the best header chain is never dropped, nor is
// pKeep (the parent of the header being added) nor what it stands on. Counts what is held afresh: the running count is an estimate
// (a reorganisation of the header chain moves entries from one side to the other). No peer is left pointing at a dropped entry.
void EvictBranchHeaders(const CBlockIndex* pKeep, size_t nTarget)
{
    std::map<const CBlockIndex*, unsigned> mapChildren;
    std::vector<CBlockIndex*> vBranch;
    for (const auto& item : mapHeaderIndex)
    {
        CBlockIndex* p = item.second;
        if (p->pprev)
            mapChildren[p->pprev]++;
        if (!OnHeaderChain(p))
            vBranch.push_back(p);
    }
    auto lowerWork = [](const CBlockIndex* a, const CBlockIndex* b) { return a->bnChainWork > b->bnChainWork; };
    std::priority_queue<CBlockIndex*, std::vector<CBlockIndex*>, decltype(lowerWork)> leaves(lowerWork);
    for (CBlockIndex* p : vBranch)
        if (!mapChildren.count(p) && p != pKeep)
            leaves.push(p);
    size_t nHeld = vBranch.size();
    std::set<CBlockIndex*> setGone;
    while (nHeld > nTarget && !leaves.empty())
    {
        CBlockIndex* p = leaves.top();
        leaves.pop();
        setGone.insert(p);
        nHeld--;
        CBlockIndex* pparent = p->pprev;
        if (pparent && --mapChildren[pparent] == 0 && pparent != pKeep && mapHeaderIndex.count(*pparent->phashBlock) && !OnHeaderChain(pparent))
            leaves.push(pparent);
    }
    for (CBlockIndex* p : setGone)
        { const uint256 h = *p->phashBlock; mapHeaderIndex.erase(h); }
    {
        LOCK(cs_vNodes);
        for (CNode* pnode : vNodes)
            if (pnode->pindexBestKnown && setGone.count(pnode->pindexBestKnown))
                pnode->pindexBestKnown = nullptr;
    }
    for (CBlockIndex* p : setGone)
        delete p;
    nBranchHeaders = nHeld;
    if (!setGone.empty())
        LogPrintf("headers-first: %u header(s) on side branches dropped (%u held)\n", (unsigned)setGone.size(), (unsigned)nHeld);
}

// HEADER_REFUSED: a header we will not keep (a deep fork, no room), by no fault of the peer's that we can tell: no score, and not asked again for it
enum HeaderResult { HEADER_OK, HEADER_BAD, HEADER_UNCONNECTED, HEADER_REFUSED };

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
        // one that was dropped as the best header (nobody served its blocks) and is announced again
        if (pindexBestHeader && pindexKnown->bnChainWork > pindexBestHeader->bnChainWork)
            SetBestHeader(pindexKnown);
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
    // A header that forks off the best header chain far back needs the same work as every header after the fork to matter, and a peer
    // that sends a few of them gains nothing but our memory: refuse it, and what is built on it.
    EnsureHeaderChain();
    // The depth is measured from our own validated tip, which a peer cannot move without the work of real blocks. (Measured from the best
    // header, which is not validated, a run of cheap low-work headers moved it, and then every header of the honest chain was refused.)
    // A header whose parent is itself a header entry stands on one that passed this test, or on the best header chain from our tip.
    if (pindexBest && !mapHeaderIndex.count(hdr.hashPrevBlock) && pindexPrev->nHeight + MaxForkDepth() < pindexBest->nHeight)
    {
        LogPrintf("headers-first: header %s forks off at %d, more than %d below our tip (%d): not followed\n", hash.ToString().substr(0, 20).c_str(),
                  pindexPrev->nHeight, MaxForkDepth(), pindexBest->nHeight);
        return HEADER_REFUSED;          // no score: it is a fork nobody should follow, not proof that the peer is at fault
    }
    // Side branches are held up to a cap; past it the lowest-work ones are dropped (not scored: an honest fork is one of them, and the peer
    // that sends the header that fills the space is not the one that filled it). pindexPrev is kept.
    if (nBranchHeaders >= MaxBranchHeaders())
    {
        EvictBranchHeaders(pindexPrev, MaxBranchHeaders() * 9 / 10);
        if (nBranchHeaders >= MaxBranchHeaders())
            return HEADER_REFUSED;
    }
    if (mapHeaderIndex.size() >= MAX_HEADER_INDEX)
    {
        EvictBranchHeaders(pindexPrev, 0);
        if (mapHeaderIndex.size() >= MAX_HEADER_INDEX)
        {
            LogPrintf("headers-first: the header index is full (%u), not keeping %s\n", (unsigned)mapHeaderIndex.size(), hash.ToString().substr(0, 20).c_str());
            return HEADER_REFUSED;
        }
    }

    CBlock copy(hdr);
    CBlockIndex* pindexNew = new CBlockIndex(0, 0, copy);
    auto mi = mapHeaderIndex.insert({hash, pindexNew}).first;
    pindexNew->phashBlock = &mi->first;
    pindexNew->pprev = pindexPrev;
    pindexNew->nHeight = nHeight;
    pindexNew->bnChainWork = pindexPrev->bnChainWork + pindexNew->GetBlockWork();
    pindexNew->fFailedChain = false;
    if (!pindexBestHeader || pindexNew->bnChainWork > pindexBestHeader->bnChainWork)
        SetBestHeader(pindexNew);
    else
        nBranchHeaders++;
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
    return pnode && HeadersFirstEnabled() && pnode->nVersion >= HEADERSFIRST_VERSION && GetTime() >= nHeadersFallbackUntil;
}

void HeadersFirstChainInvalidated()
{
    if (mapHeaderIndex.empty() && !pindexBestHeader)
        return;
    // a header entry built on a block that failed, or was invalidated, fails with it (parents first, so by height)
    std::vector<std::pair<int, CBlockIndex*> > vByHeight;
    vByHeight.reserve(mapHeaderIndex.size());
    for (const auto& item : mapHeaderIndex)
        vByHeight.emplace_back(item.second->nHeight, item.second);
    std::sort(vByHeight.begin(), vByHeight.end());
    for (const auto& item : vByHeight)
    {
        CBlockIndex* p = item.second;
        p->fFailedChain = setInvalidatedBlocks.count(*p->phashBlock) || (p->pprev && p->pprev->fFailedChain);
    }
    // and the best header must not be one of them
    if (pindexBestHeader && pindexBestHeader->fFailedChain)
    {
        LogPrintf("headers-first: the best header descends from a block that failed\n");
        RepickBestHeader(nullptr);
    }
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

bool HaveHeaderFor(const uint256& hash)
{
    return mapHeaderIndex.count(hash) != 0;
}

bool ProcessHeadersMessage(CNode* pfrom, CDataStream& vRecv)
{
    // whatever this message holds, the request it answers is over; it is asked again below only if there may be more. (An empty answer, a
    // bad header or one that does not connect used to leave the flag set, and three such peers kept header sync from every other peer.)
    // This is before the check that headers-first is on for the peer: during the fallback a peer that answers must not be taken for one that did not.
    pfrom->fSyncing = false;
    if (!HeadersFirstWith(pfrom))
        return true;
    vector<CBlock> vHeaders;
    vRecv >> vHeaders;
    if (vHeaders.size() > MAX_HEADERS_RESULTS)
    {
        pfrom->Misbehaving(20);
        return LogError("headers message size = %u", (unsigned)vHeaders.size());
    }
    if (vHeaders.empty())
    {
        // nothing more, although it said at the start that its chain is longer than what we have: if the tip does not move, it is asked for blocks
        if (pfrom->nStartingHeight > (pindexBestHeader ? pindexBestHeader->nHeight : 0))
            pfrom->nShortAnswerTime = GetTime();
        return true;
    }
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
        if (r == HEADER_REFUSED)
            return true;
        if (r == HEADER_BAD)
        {
            if (nDoS)
                pfrom->Misbehaving(nDoS);
            else
            {
                // a time check, say: an honest peer with a wrong clock. It is asked again later rather than never
                pfrom->nHeadersRetryTime = GetTime() + HEADERS_RETRY_SECONDS;
                pfrom->fSyncStarted = false;
            }
            LogPrintf("headers-first: bad header from %s, stopping at %s\n", pfrom->addr.ToString().c_str(), hdr.GetHash().ToString().substr(0, 20).c_str());
            return true;
        }
        pindexLast = pindex;
    }
    pfrom->nUnconnectingHeaders = 0;
    if (pindexLast && vHeaders.size() < MAX_HEADERS_RESULTS && pfrom->nStartingHeight > pindexLast->nHeight)
        pfrom->nShortAnswerTime = GetTime();        // an answer that ends short of the chain it claims
    if (pindexLast &&(!pfrom->pindexBestKnown || pindexLast->bnChainWork > pfrom->pindexBestKnown->bnChainWork))
        pfrom->pindexBestKnown = pindexLast;
    LogPrintf("headers-first: %u headers from %s, best header %d\n", (unsigned)vHeaders.size(), pfrom->addr.ToString().c_str(), pindexBestHeader ? pindexBestHeader->nHeight : -1);

    if (vHeaders.size() == MAX_HEADERS_RESULTS && pindexLast)
    {
        pfrom->fSyncing = true;
        pfrom->nSyncRequestTime = GetTime();
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
    const int64 nNow = GetTime();

    // 0. a getheaders that was not answered: the peer holds one of the few slots, so it is dropped, and the others are synced the old
    //    way (getblocks) for a while, so that peers that answer pings and nothing else cannot stop a node from syncing. (Checked for every
    //    peer that was asked, also once the fallback is on and headers-first is off for the new ones.)
    if (HeadersFirstEnabled() && pto->fSyncing && nNow - pto->nSyncRequestTime > HeaderSyncTimeout())
    {
        LogPrintf("headers-first: %s did not answer getheaders in %d seconds, disconnecting; syncing the old way for %d minutes\n",
                  pto->addr.ToString().c_str(), (int)HeaderSyncTimeout(), (int)(HEADERS_FALLBACK_SECONDS / 60));
        pto->fSyncing = false;
        pto->fDisconnect = true;
        nHeadersFallbackUntil = nNow + HEADERS_FALLBACK_SECONDS;
        LOCK(cs_vNodes);
        int nAsked = 0;
        for (CNode* pnode : vNodes)
        {
            // the others are not waited on any more (they would be dropped in their turn for an answer that is not wanted), and two taller peers are asked
            pnode->fSyncing = false;
            pnode->fSyncStarted = false;        // asked for headers again once the fallback is over (a silent one is then dropped in its turn)
            if (pnode != pto && !pnode->fDisconnect && !pnode->fClient && !pnode->fOneShot && pnode->fSuccessfullyConnected && pnode->nStartingHeight > nBestHeight && nAsked < 2)
            {
                pnode->PushGetBlocks(pindexBest, uint256(0));
                nAsked++;
            }
        }
        return;
    }

    if (!HeadersFirstWith(pto) || !pto->fSuccessfullyConnected || pto->fClient || pto->fOneShot)
        return;
    EnsureHeaderChain();

    // 0-. a peer that has answered for headers with none (or too few) while it claims a longer chain than ours, and the tip has not moved for
    //     the length of a header timeout: it is asked for blocks the old way, now and then, so that it can not hold a node still by answering nothing
    static int nLastBestHeight = -1;
    static int64 nLastBestChange = 0;
    if (nBestHeight != nLastBestHeight)
    {
        nLastBestHeight = nBestHeight;
        nLastBestChange = nNow;
    }
    if (pto->nShortAnswerTime)
    {
        if (nBestHeight >= pto->nStartingHeight)
            pto->nShortAnswerTime = 0;
        else if (nNow - std::max(pto->nShortAnswerTime, nLastBestChange) > HeaderSyncTimeout())
        {
            LogPrintf("headers-first: %s has no headers for us beyond %d and the tip has not moved: asking it for blocks\n", pto->addr.ToString().c_str(), nBestHeight);
            pto->PushGetBlocks(pindexBest, uint256(0));
            pto->nShortAnswerTime = nNow;
        }
    }

    if (!pindexBestHeader)
        return;

    // 0a. the best header descends from a block that failed (the chain has been rolled back since it was marked): not the best any more
    if (pindexBestHeader->fFailedChain)
        RepickBestHeader(nullptr);

    // 0b. the best header is not one that any connected peer has told us of (the peer that had it went, or was dropped for not
    //     sending the blocks): it must not stay the best, or the node waits for blocks nobody has and asks no one else
    static int64 nLastServedCheck = 0;
    if (nNow - nLastServedCheck >= 10)
    {
        nLastServedCheck = nNow;
        if (pindexBestHeader->bnChainWork > pindexBest->bnChainWork)
        {
            bool fServed = false;
            {
                LOCK(cs_vNodes);
                for (CNode* pnode : vNodes)
                    if (!pnode->fDisconnect && pnode->pindexBestKnown && pnode->pindexBestKnown->bnChainWork >= pindexBestHeader->bnChainWork)
                        fServed = true;
            }
            if (!fServed)
                RepickBestHeader(nullptr);
        }
    }

    // 1. ask a peer that has more than we do for its headers
    if ((!pto->fSyncStarted && nNow >= pto->nHeadersRetryTime) && pto->nStartingHeight > pindexBestHeader->nHeight)
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
            pto->nSyncRequestTime = nNow;
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
    const int64 nTimeout = GetArg("-blocktimeout", 120) < 1 ? 120 : GetArg("-blocktimeout", 120);
    for (const auto& kv : pto->mapBlocksInFlight)
        if (nNow - kv.second > nTimeout)
        {
            LogPrintf("headers-first: %s did not send block %s in %d seconds, disconnecting\n", pto->addr.ToString().c_str(), kv.first.ToString().substr(0, 20).c_str(), (int)nTimeout);
            pto->fDisconnect = true;
            return;
        }

    // 3. blocks of the best header chain this peer has, a window ahead of our tip, that nobody is bringing yet
    if (!pto->pindexBestKnown || pto->pindexBestKnown->fFailedChain || pto->pindexBestKnown->bnChainWork <= pindexBest->bnChainWork)
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
