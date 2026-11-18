// Pruning: see prune.h.
#include "prune.h"

#include "init.h"
#include "ui_interface.h"
#include "util.h"

#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>

bool fPruneMode = false;

namespace {
uint64 nPruneTargetBytes = 0;
std::set<unsigned int> setPrunedFiles;      // numbers of the block files that were deleted
int nLastPruneCheckHeight = 0;
int nPruneHeightCache = -1;                // -1: not worked out since the last file went
std::map<unsigned int, int> mapFileMaxHeight;   // file -> its highest block
bool fFileMapBuilt = false;
unsigned int nLastPruneCheckFile = 0;

std::filesystem::path PrunedListPath() { return GetDataDir() / "blkpruned.dat"; }
std::filesystem::path BlockFilePath(unsigned int nFile) { return GetDataDir() / strprintf("blk%04d.dat", nFile); }

// the list is written whole to a new file and renamed over the old one, before a file is deleted: a crash leaves a list that is
// a superset of what is gone, never a file gone that the list does not say
bool WritePrunedList()
{
    const std::filesystem::path tmp = GetDataDir() / "blkpruned.dat.new";
    {
        std::ofstream out(tmp, std::ios::trunc);
        for (unsigned int n : setPrunedFiles)
            out << n << "\n";
        out.flush();
        if (!out)
            return false;
    }
    std::error_code ec;
    std::filesystem::rename(tmp, PrunedListPath(), ec);
    return !ec;
}

uint64 PruneKeepBlocks()
{
    if (fRegTest && mapArgs.count("-testpruneblocks"))
        return (uint64)std::max<int64>(1, GetArg("-testpruneblocks", PRUNE_KEEP_BLOCKS));       // test hook, regtest only
    return PRUNE_KEEP_BLOCKS;
}
}

bool PruneInit(std::string& strError)
{
    // the list of deleted files, whether or not pruning is asked for now
    setPrunedFiles.clear();
    {
        std::ifstream in(PrunedListPath());
        unsigned int n;
        while (in >> n)
            setPrunedFiles.insert(n);
    }
    // a file the list says is gone but is back (a restored backup) is deleted again, and one gone but not listed is not our business
    for (unsigned int n : setPrunedFiles)
    {
        std::error_code ec;
        std::filesystem::remove(BlockFilePath(n), ec);
    }

    const int64 nMiB = GetArg("-prune", 0);
    if (nMiB < 0)
    {
        strError = _("-prune cannot be negative");
        return false;
    }
    if (nMiB == 0 && !(fRegTest && mapArgs.count("-testprunebytes")))
    {
        if (!setPrunedFiles.empty())
        {
            strError = strprintf(_("This data directory was pruned (%u block files are gone). Start with -prune=<MiB> again; to go back to a full node, the blocks have to be downloaded again (remove the data directory except wallet.dat)."),
                                 (unsigned)setPrunedFiles.size());
            return false;
        }
        fPruneMode = false;
        return true;
    }
    if (nMiB != 0 && nMiB < 128 && !fRegTest)
    {
        strError = _("-prune must be at least 128 (MiB), or 0 for no pruning");
        return false;
    }
    if (GetBoolArg("-reindex", false) || GetBoolArg("-rescan", false))
    {
        strError = _("-prune cannot be used with -reindex or -rescan: they need every block");
        return false;
    }
    if (!GetBoolArg("-coinsvalidate", true))
    {
        strError = _("-prune needs the unspent set to validate (-nocoinsvalidate reads old transactions from the block files)");
        return false;
    }
    fPruneMode = true;
    nPruneTargetBytes = (uint64)nMiB * 1024 * 1024;
    if (fRegTest && mapArgs.count("-testprunebytes"))
        nPruneTargetBytes = (uint64)std::max<int64>(1, GetArg("-testprunebytes", 1));          // test hook, regtest only
    LogPrintf("prune: keeping about %u MiB of block files (and always the last %u blocks); %u files already deleted\n",
              (unsigned)(nPruneTargetBytes / (1024 * 1024)), (unsigned)PruneKeepBlocks(), (unsigned)setPrunedFiles.size());
    return true;
}

bool IsBlockFilePruned(unsigned int nFile)
{
    return !setPrunedFiles.empty() && setPrunedFiles.count(nFile) != 0;
}

bool IsBlockPruned(const CBlockIndex* pindex)
{
    return pindex && pindex->nFile != 0 && IsBlockFilePruned(pindex->nFile);
}

unsigned int PrunedFileCount()
{
    return (unsigned int)setPrunedFiles.size();
}

int PruneHeight()
{
    if (setPrunedFiles.empty())
        return 0;
    if (nPruneHeightCache >= 0)
        return nPruneHeightCache;       // the scan below visits every block: once, and again only after more files go
    int nLowest = -1;
    for (const auto& item : mapBlockIndex)
    {
        const CBlockIndex* pindex = item.second;
        if (pindex->nFile != 0 && !IsBlockFilePruned(pindex->nFile) && (nLowest < 0 || pindex->nHeight < nLowest))
            nLowest = pindex->nHeight;
    }
    nPruneHeightCache = nLowest < 0 ? 0 : nLowest;
    return nPruneHeightCache;
}

uint64 BlockFileThreshold()
{
    if (fRegTest && mapArgs.count("-testblockfilesize"))
        return (uint64)std::max<int64>(1, GetArg("-testblockfilesize", 1));                    // test hook, regtest only
    if (fPruneMode)
        return 64ULL * 1024 * 1024;
    return 0x7F000000ULL - MAX_SIZE;
}

void PruneBlockFiles()
{
    if (!fPruneMode || !pindexBest)
        return;
    const unsigned int nCurrentFile = CurrentBlockFile();
    // not on every block: when a new file has been started, or every 50 blocks
    if (nCurrentFile == nLastPruneCheckFile && nBestHeight - nLastPruneCheckHeight < 50 && nBestHeight >= nLastPruneCheckHeight)
        return;
    nLastPruneCheckFile = nCurrentFile;
    nLastPruneCheckHeight = nBestHeight;

    // per file: the highest block in it (worked out from the block index once, then kept by PruneNoteBlock as blocks are added)
    if (!fFileMapBuilt)
    {
        mapFileMaxHeight.clear();
        for (const auto& item : mapBlockIndex)
        {
            const CBlockIndex* pindex = item.second;
            if (pindex->nFile == 0 || IsBlockFilePruned(pindex->nFile))
                continue;
            int& nMax = mapFileMaxHeight[pindex->nFile];
            nMax = std::max(nMax, pindex->nHeight);
        }
        fFileMapBuilt = true;
    }
    std::map<unsigned int, int>& mapMaxHeight = mapFileMaxHeight;
    uint64 nTotal = 0;
    std::map<unsigned int, uint64> mapSize;
    for (const auto& item : mapMaxHeight)
    {
        std::error_code ec;
        const uint64 nSize = std::filesystem::file_size(BlockFilePath(item.first), ec);
        if (!ec)
        {
            mapSize[item.first] = nSize;
            nTotal += nSize;
        }
    }
    if (nTotal <= nPruneTargetBytes)
        return;

    const int nLimitHeight = nBestHeight - (int)PruneKeepBlocks();
    unsigned int nDeleted = 0;
    for (const auto& item : mapSize)        // the oldest file first
    {
        if (nTotal <= nPruneTargetBytes)
            break;
        const unsigned int nFile = item.first;
        // the file being written to, and any file with a block that is not far enough down, stay (and so do all after it)
        if (nFile >= nCurrentFile || mapMaxHeight[nFile] >= nLimitHeight)
            break;
        setPrunedFiles.insert(nFile);
        nPruneHeightCache = -1;
        if (!WritePrunedList())
        {
            setPrunedFiles.erase(nFile);
            LogPrintf("prune: could not write the list of deleted files; nothing deleted\n");
            return;
        }
        std::error_code ec;
        std::filesystem::remove(BlockFilePath(nFile), ec);
        if (ec)
            LogPrintf("prune: could not delete %s: %s (it is listed as pruned and will be deleted at the next start)\n", BlockFilePath(nFile).string().c_str(), ec.message().c_str());
        const int nHighest = mapMaxHeight[nFile];       // before the entry goes (indexing a missing one would put it back, at 0)
        mapFileMaxHeight.erase(nFile);
        nTotal -= item.second;
        nDeleted++;
        LogPrintf("prune: deleted block file %04u (its highest block is %d, the tip %d)\n", nFile, nHighest, nBestHeight);
    }
    if (nDeleted)
        LogPrintf("prune: %u files deleted, %u MiB of blocks left\n", nDeleted, (unsigned)(nTotal / (1024 * 1024)));
}

bool RescanNeedsPrunedBlocks(const CBlockIndex* pindexStart)
{
    if (!fPruneMode || setPrunedFiles.empty())
        return false;
    for (const CBlockIndex* pindex = pindexStart; pindex; pindex = pindex->pnext)
        if (IsBlockPruned(pindex))
            return true;
    return false;
}

void PruneNoteBlock(unsigned int nFile, int nHeight)
{
    if (nPruneHeightCache >= 0 && nHeight < nPruneHeightCache)
        nPruneHeightCache = nHeight;    // a block came in below the lowest one on disk (a side branch)
    if (!fFileMapBuilt || nFile == 0)
        return;                 // not worked out yet: it will be, from the block index, which holds this block by then
    int& nMax = mapFileMaxHeight[nFile];
    nMax = std::max(nMax, nHeight);
}
