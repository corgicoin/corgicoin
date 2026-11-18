// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletstorage.h"

#include "db.h"

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
        // The environment throws DbException (DB_CXX_NO_EXCEPTIONS is not set): a throw from a destructor that runs while another
        // exception unwinds would call std::terminate
        ~BerkeleyCursor() override
        {
            if (!pcursor)
                return;
            try { pcursor->close(); }
            catch (...) { LogPrintf("wallet storage: closing a cursor failed\n"); }
        }

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

bool RewriteWalletStorage(const std::string& strFile, const char* pszSkip)
{
    return CDB::Rewrite(strFile, pszSkip);
}

std::unique_ptr<CWalletStorage> OpenWalletStorage(const std::string& strFile, const char* pszMode)
{
    return std::make_unique<CBerkeleyWalletStorage>(strFile, pszMode);
}
