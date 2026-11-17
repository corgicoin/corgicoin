// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletstorage.h"

#include "db.h"
#include "logging.h"
#include "util.h"

#include <filesystem>
#include <vector>

namespace {

/** wallet.dat: the wallet's records in a Berkeley DB file, in the environment that the block index shares (bitdb). All the work is CDB's. */
class CBerkeleyWalletStorage : public CWalletStorage, private CDB
{
public:
    CBerkeleyWalletStorage(const std::string& strFile, const char* pszMode) : CDB(strFile.c_str(), pszMode) {}

    bool Read(CDataStream& ssKey, CDataStream& ssValue) override { return ReadRaw(ssKey, ssValue); }
    bool Write(CDataStream& ssKey, CDataStream& ssValue, bool fOverwrite) override { return WriteRaw(ssKey, ssValue, fOverwrite); }
    bool Erase(CDataStream& ssKey) override { return EraseRaw(ssKey); }
    bool Exists(CDataStream& ssKey) override { return ExistsRaw(ssKey); }

    bool TxnBegin() override { return CDB::TxnBegin(); }
    bool TxnCommit() override { return CDB::TxnCommit(); }
    bool TxnAbort() override { return CDB::TxnAbort(); }
    void Close() override { CDB::Close(); }

    class BerkeleyCursor : public Cursor
    {
    public:
        BerkeleyCursor(CBerkeleyWalletStorage& dbIn, Dbc* pcursorIn) : db(dbIn), pcursor(pcursorIn) {}
        ~BerkeleyCursor() override { if (pcursor) pcursor->close(); }

        Result Seek(CDataStream& ssKey, CDataStream& ssValue) override { return Get(ssKey, ssValue, DB_SET_RANGE); }
        Result Next(CDataStream& ssKey, CDataStream& ssValue) override { return Get(ssKey, ssValue, DB_NEXT); }

    private:
        Result Get(CDataStream& ssKey, CDataStream& ssValue, unsigned int fFlags)
        {
            int ret = db.ReadAtCursor(pcursor, ssKey, ssValue, fFlags);
            if (ret == 0)
                return OK;
            return ret == DB_NOTFOUND ? END : FAILED;
        }

        CBerkeleyWalletStorage& db;
        Dbc* pcursor;
    };

    std::unique_ptr<Cursor> OpenCursor() override
    {
        Dbc* pcursor = GetCursor();
        if (!pcursor)
            return nullptr;
        return std::make_unique<BerkeleyCursor>(*this, pcursor);
    }
};

} // namespace

namespace {

/** What a wallet that could not be opened is: every call fails (as an unopened CDB always did), so that the caller's error handling is the one it has. */
class CUnavailableWalletStorage : public CWalletStorage
{
public:
    bool Read(CDataStream&, CDataStream&) override { return false; }
    bool Write(CDataStream&, CDataStream&, bool) override { return false; }
    bool Erase(CDataStream&) override { return false; }
    bool Exists(CDataStream&) override { return false; }
    std::unique_ptr<Cursor> OpenCursor() override { return nullptr; }
    bool TxnBegin() override { return false; }
    bool TxnCommit() override { return false; }
    bool TxnAbort() override { return false; }
    void Close() override {}
};

bool BackupBerkeleyWallet(const std::string& strFile, const std::string& strDest)
{
    while (!fShutdown)
    {
        {
            LOCK(bitdb.cs_db);
            if (!bitdb.mapFileUseCount.count(strFile) || bitdb.mapFileUseCount[strFile] == 0)
            {
                // Flush log data to the dat file
                bitdb.CloseDb(strFile);
                bitdb.CheckpointLSN(strFile);
                bitdb.mapFileUseCount.erase(strFile);

                // Copy wallet.dat
                std::filesystem::path pathSrc = GetDataDir() / strFile;
                std::filesystem::path pathDest(strDest);
                if (std::filesystem::is_directory(pathDest))
                    pathDest /= strFile;

                try {
                    std::filesystem::copy_file(pathSrc, pathDest, std::filesystem::copy_options::overwrite_existing);
                    LogPrintf("copied %s to %s\n", strFile.c_str(), pathDest.string().c_str());
                    return true;
                } catch(const std::filesystem::filesystem_error &e) {
                    LogPrintf("error copying %s to %s - %s\n", strFile.c_str(), pathDest.string().c_str(), e.what());
                    return false;
                }
            }
        }
        Sleep(100);
    }
    return false;
}

} // namespace

bool IsSqliteWalletFile(const std::string& strFile)
{
    static const std::string strSuffix = ".sqlite";
    return strFile.size() > strSuffix.size() && strFile.compare(strFile.size() - strSuffix.size(), strSuffix.size(), strSuffix) == 0;
}

bool WalletStorageAvailable(const std::string& strFile)
{
    return !IsSqliteWalletFile(strFile) || SqliteWalletAvailable();
}

bool RewriteWalletStorage(const std::string& strFile, const char* pszSkip)
{
    if (IsSqliteWalletFile(strFile))
        return RewriteSqliteWallet(strFile, pszSkip);
    return CDB::Rewrite(strFile, pszSkip);
}

bool BackupWalletStorage(const std::string& strFile, const std::string& strDest)
{
    if (IsSqliteWalletFile(strFile))
        return BackupSqliteWallet(strFile, strDest);
    return BackupBerkeleyWallet(strFile, strDest);
}

std::unique_ptr<CWalletStorage> OpenWalletStorage(const std::string& strFile, const char* pszMode)
{
    if (IsSqliteWalletFile(strFile))
    {
        std::unique_ptr<CWalletStorage> storage = OpenSqliteWalletStorage(strFile, pszMode);
        if (!storage)
            storage = std::make_unique<CUnavailableWalletStorage>();
        return storage;
    }
    return std::make_unique<CBerkeleyWalletStorage>(strFile, pszMode);
}

namespace {

void RemoveSqliteFiles(const std::filesystem::path& path)
{
    std::error_code ec;
    for (const char* suffix : {"", "-wal", "-shm", "-journal"})
        std::filesystem::remove(path.string() + suffix, ec);
}

/** The records of a wallet in key order, whole: [(key, value)], bytes as stored. */
bool ReadAllRecords(CWalletStorage& storage, std::vector<std::pair<std::vector<char>, std::vector<char>>>& vRecords)
{
    std::unique_ptr<CWalletStorage::Cursor> pcursor = storage.OpenCursor();
    if (!pcursor)
        return false;
    while (true)
    {
        CDataStream ssKey(SER_DISK, CLIENT_VERSION);
        CDataStream ssValue(SER_DISK, CLIENT_VERSION);
        CWalletStorage::Cursor::Result ret = pcursor->Next(ssKey, ssValue);
        if (ret == CWalletStorage::Cursor::END)
            return true;
        if (ret != CWalletStorage::Cursor::OK)
            return false;
        vRecords.emplace_back(std::vector<char>(ssKey.begin(), ssKey.end()), std::vector<char>(ssValue.begin(), ssValue.end()));
    }
}

void Wipe(std::vector<std::pair<std::vector<char>, std::vector<char>>>& vRecords)
{
    for (auto& r : vRecords)
    {
        memset(r.first.data(), 0, r.first.size());
        memset(r.second.data(), 0, r.second.size());
    }
}

} // namespace

bool MigrateWalletStorage(const std::string& strFrom, const std::string& strTo, std::string& strError)
{
    if (IsSqliteWalletFile(strFrom) || !IsSqliteWalletFile(strTo))
    {
        strError = "the wallet to read must be a Berkeley DB file (wallet.dat) and the new one a name that ends in .sqlite";
        return false;
    }
    if (!SqliteWalletAvailable())
    {
        strError = "this build has no SQLite support (build with -DUSE_SQLITE=ON)";
        return false;
    }
    const std::filesystem::path pathTo = GetDataDir() / strTo;
    if (std::filesystem::exists(pathTo))
    {
        strError = pathTo.string() + " exists already; it is never overwritten";
        return false;
    }

    typedef std::vector<std::pair<std::vector<char>, std::vector<char>>> Records;
    Records vFrom, vBack;
    bool fOk = false;
    {
        std::unique_ptr<CWalletStorage> from = OpenWalletStorage(strFrom, "r+");
        if (!ReadAllRecords(*from, vFrom))
            strError = "could not read " + strFrom;
        else if (vFrom.empty())
            strError = strFrom + " has no records";
        else
        {
            std::unique_ptr<CWalletStorage> to = OpenWalletStorage(strTo, "cr+");
            // everything in one transaction: the new file has all the records or it is removed
            if (!to->TxnBegin())
                strError = "could not start a transaction in " + strTo;
            else
            {
                fOk = true;
                for (auto& r : vFrom)
                {
                    CDataStream ssKey(r.first.data(), r.first.data() + r.first.size(), SER_DISK, CLIENT_VERSION);
                    CDataStream ssValue(r.second.data(), r.second.data() + r.second.size(), SER_DISK, CLIENT_VERSION);
                    if (!to->Write(ssKey, ssValue, false))
                    {
                        strError = "could not write a record to " + strTo;
                        fOk = false;
                        break;
                    }
                }
                if (fOk && !to->TxnCommit())
                {
                    strError = "could not commit " + strTo;
                    fOk = false;
                }
                if (!fOk)
                    to->TxnAbort();
            }
            to->Close();
        }
    }
    if (fOk)
    {
        // Read the new file back, as a node would, and compare it with what was read from the old one
        std::unique_ptr<CWalletStorage> back = OpenWalletStorage(strTo, "r");
        fOk = ReadAllRecords(*back, vBack) && vBack == vFrom;
        if (!fOk)
            strError = "the new wallet read back is not the old one";
    }
    Wipe(vFrom);
    Wipe(vBack);
    if (!fOk)
        RemoveSqliteFiles(pathTo);
    return fOk;
}
