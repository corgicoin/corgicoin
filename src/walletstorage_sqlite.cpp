// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletstorage.h"

#ifdef ENABLE_SQLITE

#include "logging.h"
#include "util.h"

#include <sqlite3.h>

#include <cstring>
#include <filesystem>

// A SQLite wallet is one file (wallet.sqlite) with one table of (key, value) records, the same records, as bytes, that a wallet.dat holds. The keys
// are compared as bytes, as Berkeley DB compares them, so the cursor walks them in the same order.
//
// Every CWalletDB has a connection of its own (opened and closed with it), as it had its own Berkeley DB handle; SQLite's locking is what keeps them
// apart. Writes outside a transaction are one transaction each. synchronous=FULL: a commit that returned is on the disk, as the keys it holds must be.
// secure_delete: what is deleted (the unencrypted keys, after the wallet is encrypted) is overwritten with zeros, not just unlinked.

namespace {

const char* const SQL_CREATE = "CREATE TABLE IF NOT EXISTS wallet (key BLOB PRIMARY KEY, value BLOB NOT NULL) WITHOUT ROWID";

/** Write zeros over what a stream held, as the Berkeley DB backend does: a key or a value may be a private key. */
void Wipe(CDataStream& ss)
{
    if (ss.size())
        memset(&ss[0], 0, ss.size());
}

class Statement
{
public:
    Statement(sqlite3* db, const char* sql) : st(nullptr)
    {
        if (sqlite3_prepare_v2(db, sql, -1, &st, nullptr) != SQLITE_OK)
            st = nullptr;
    }
    ~Statement() { if (st) sqlite3_finalize(st); }
    explicit operator bool() const { return st != nullptr; }
    sqlite3_stmt* get() { return st; }
    bool BindBlob(int i, CDataStream& ss)
    {
        // (a zero-length blob is bound as such, not as NULL)
        return sqlite3_bind_blob(st, i, ss.size() ? &ss[0] : "", (int)ss.size(), SQLITE_STATIC) == SQLITE_OK;
    }
private:
    Statement(const Statement&) = delete;
    void operator=(const Statement&) = delete;
    sqlite3_stmt* st;
};

bool Exec(sqlite3* db, const char* sql)
{
    return sqlite3_exec(db, sql, nullptr, nullptr, nullptr) == SQLITE_OK;
}

std::filesystem::path WalletPath(const std::string& strFile)
{
    return GetDataDir() / strFile;
}

/** Open a connection with the settings every one of them has. flags: SQLITE_OPEN_READONLY, or SQLITE_OPEN_READWRITE (| SQLITE_OPEN_CREATE). */
sqlite3* OpenConnection(const std::filesystem::path& path, int flags)
{
    sqlite3* db = nullptr;
    if (sqlite3_open_v2(path.string().c_str(), &db, flags | SQLITE_OPEN_FULLMUTEX, nullptr) != SQLITE_OK)
    {
        LogPrintf("SQLite wallet: cannot open %s: %s\n", path.string().c_str(), db ? sqlite3_errmsg(db) : "out of memory");
        if (db)
            sqlite3_close(db);
        return nullptr;
    }
    sqlite3_busy_timeout(db, 30000);
    if (!(flags & SQLITE_OPEN_READONLY))
    {
        // (WAL: one fsync per commit, readers do not block the writer)
        if (!Exec(db, "PRAGMA journal_mode=WAL") || !Exec(db, "PRAGMA synchronous=FULL") || !Exec(db, "PRAGMA secure_delete=ON"))
        {
            LogPrintf("SQLite wallet: cannot set up %s: %s\n", path.string().c_str(), sqlite3_errmsg(db));
            sqlite3_close(db);
            return nullptr;
        }
    }
    return db;
}

class CSqliteWalletStorage : public CWalletStorage
{
public:
    CSqliteWalletStorage(const std::string& strFile, const char* pszMode) : db(nullptr), fInTxn(false)
    {
        const std::string strMode(pszMode ? pszMode : "r+");
        const bool fCreate = strMode.find('c') != std::string::npos;
        const bool fWrite = fCreate || strMode.find('+') != std::string::npos;
        const std::filesystem::path path = WalletPath(strFile);
        if (!fCreate && !std::filesystem::exists(path))
            return;
        db = OpenConnection(path, fWrite ? (SQLITE_OPEN_READWRITE | (fCreate ? SQLITE_OPEN_CREATE : 0)) : SQLITE_OPEN_READONLY);
        if (db && fWrite && !Exec(db, SQL_CREATE))
        {
            LogPrintf("SQLite wallet: cannot create the table in %s: %s\n", path.string().c_str(), sqlite3_errmsg(db));
            CloseDb();
        }
    }
    ~CSqliteWalletStorage() override { Close(); }

    bool Read(CDataStream& ssKey, CDataStream& ssValue) override
    {
        if (!db)
            return false;
        Statement st(db, "SELECT value FROM wallet WHERE key = ?1");
        bool fFound = false;
        if (st && st.BindBlob(1, ssKey) && sqlite3_step(st.get()) == SQLITE_ROW)
        {
            ssValue.SetType(SER_DISK);
            ssValue.clear();
            ssValue.write(reinterpret_cast<const char*>(sqlite3_column_blob(st.get(), 0)), sqlite3_column_bytes(st.get(), 0));
            fFound = true;
        }
        Wipe(ssKey);
        return fFound;
    }

    bool Write(CDataStream& ssKey, CDataStream& ssValue, bool fOverwrite) override
    {
        if (!db)
            return false;
        Statement st(db, fOverwrite ? "INSERT OR REPLACE INTO wallet (key, value) VALUES (?1, ?2)" : "INSERT INTO wallet (key, value) VALUES (?1, ?2)");
        bool fOk = st && st.BindBlob(1, ssKey) && st.BindBlob(2, ssValue) && sqlite3_step(st.get()) == SQLITE_DONE;
        Wipe(ssKey);
        Wipe(ssValue);
        return fOk;
    }

    bool Erase(CDataStream& ssKey) override
    {
        if (!db)
            return false;
        Statement st(db, "DELETE FROM wallet WHERE key = ?1");
        bool fOk = st && st.BindBlob(1, ssKey) && sqlite3_step(st.get()) == SQLITE_DONE;
        Wipe(ssKey);
        return fOk;
    }

    bool Exists(CDataStream& ssKey) override
    {
        if (!db)
            return false;
        Statement st(db, "SELECT 1 FROM wallet WHERE key = ?1");
        bool fFound = st && st.BindBlob(1, ssKey) && sqlite3_step(st.get()) == SQLITE_ROW;
        Wipe(ssKey);
        return fFound;
    }

    bool TxnBegin() override
    {
        if (!db || fInTxn)
            return false;
        // IMMEDIATE: the write lock is taken now, so a later write in the transaction cannot fail for another connection's lock
        fInTxn = Exec(db, "BEGIN IMMEDIATE");
        return fInTxn;
    }
    bool TxnCommit() override
    {
        if (!db || !fInTxn)
            return false;
        fInTxn = false;
        if (Exec(db, "COMMIT"))
            return true;
        Exec(db, "ROLLBACK");
        return false;
    }
    bool TxnAbort() override
    {
        if (!db || !fInTxn)
            return false;
        fInTxn = false;
        return Exec(db, "ROLLBACK");
    }

    void Close() override
    {
        if (db && fInTxn)
            TxnAbort();
        CloseDb();
    }

    class SqliteCursor : public Cursor
    {
    public:
        explicit SqliteCursor(sqlite3* dbIn) : db(dbIn), st(nullptr) {}
        ~SqliteCursor() override { Reset(); }

        Result Seek(CDataStream& ssKey, CDataStream& ssValue) override
        {
            Reset();
            if (sqlite3_prepare_v2(db, "SELECT key, value FROM wallet WHERE key >= ?1 ORDER BY key", -1, &st, nullptr) != SQLITE_OK)
            {
                st = nullptr;
                return FAILED;
            }
            // (the key is copied: it is the caller's, and it is wiped below)
            sqlite3_bind_blob(st, 1, ssKey.size() ? &ssKey[0] : "", (int)ssKey.size(), SQLITE_TRANSIENT);
            if (ssKey.size())
                memset(&ssKey[0], 0, ssKey.size());
            return Step(ssKey, ssValue);
        }

        Result Next(CDataStream& ssKey, CDataStream& ssValue) override
        {
            if (!st && sqlite3_prepare_v2(db, "SELECT key, value FROM wallet ORDER BY key", -1, &st, nullptr) != SQLITE_OK)
            {
                st = nullptr;
                return FAILED;
            }
            return Step(ssKey, ssValue);
        }

    private:
        void Reset()
        {
            if (st)
                sqlite3_finalize(st);
            st = nullptr;
        }

        Result Step(CDataStream& ssKey, CDataStream& ssValue)
        {
            int ret = sqlite3_step(st);
            if (ret == SQLITE_DONE)
                return END;
            if (ret != SQLITE_ROW)
                return FAILED;
            ssKey.SetType(SER_DISK);
            ssKey.clear();
            ssKey.write(reinterpret_cast<const char*>(sqlite3_column_blob(st, 0)), sqlite3_column_bytes(st, 0));
            ssValue.SetType(SER_DISK);
            ssValue.clear();
            ssValue.write(reinterpret_cast<const char*>(sqlite3_column_blob(st, 1)), sqlite3_column_bytes(st, 1));
            return OK;
        }

        sqlite3* db;
        sqlite3_stmt* st;
    };

    std::unique_ptr<Cursor> OpenCursor() override
    {
        if (!db)
            return nullptr;
        return std::make_unique<SqliteCursor>(db);
    }

private:
    void CloseDb()
    {
        if (db)
        {
            // (a cursor still open would make this fail and leave the connection to be closed when it is finalised)
            sqlite3_close_v2(db);
            db = nullptr;
        }
    }

    sqlite3* db;
    bool fInTxn;
};

} // namespace

bool SqliteWalletAvailable()
{
    return true;
}

std::unique_ptr<CWalletStorage> OpenSqliteWalletStorage(const std::string& strFile, const char* pszMode)
{
    return std::make_unique<CSqliteWalletStorage>(strFile, pszMode);
}

bool RewriteSqliteWallet(const std::string& strFile, const char* pszSkip)
{
    sqlite3* db = OpenConnection(WalletPath(strFile), SQLITE_OPEN_READWRITE);
    if (!db)
        return false;
    bool fOk = true;
    if (pszSkip && *pszSkip)
    {
        // the records whose key begins with pszSkip (as a serialized string: its length byte first)
        Statement st(db, "DELETE FROM wallet WHERE substr(key, 1, ?2) = ?1");
        fOk = st && sqlite3_bind_blob(st.get(), 1, pszSkip, (int)strlen(pszSkip), SQLITE_STATIC) == SQLITE_OK
                 && sqlite3_bind_int(st.get(), 2, (int)strlen(pszSkip)) == SQLITE_OK
                 && sqlite3_step(st.get()) == SQLITE_DONE;
    }
    // VACUUM writes the whole file again (with secure_delete, the freed pages are zeros); the checkpoint moves the log into the file and empties it
    fOk = fOk && Exec(db, "VACUUM") && Exec(db, "PRAGMA wal_checkpoint(TRUNCATE)");
    sqlite3_close(db);
    return fOk;
}

bool BackupSqliteWallet(const std::string& strFile, const std::string& strDest)
{
    if (fShutdown)
        return false;
    std::filesystem::path pathDest(strDest);
    if (std::filesystem::is_directory(pathDest))
        pathDest /= strFile;

    sqlite3* src = OpenConnection(WalletPath(strFile), SQLITE_OPEN_READONLY);
    if (!src)
        return false;
    sqlite3* dest = nullptr;
    bool fOk = sqlite3_open_v2(pathDest.string().c_str(), &dest, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) == SQLITE_OK;
    if (fOk)
    {
        // The backup interface copies a consistent snapshot, whatever else is writing, page by page, in one go
        sqlite3_backup* backup = sqlite3_backup_init(dest, "main", src, "main");
        fOk = backup != nullptr;
        if (backup)
        {
            fOk = sqlite3_backup_step(backup, -1) == SQLITE_DONE;
            sqlite3_backup_finish(backup);
        }
        // one file: no log beside the copy
        fOk = fOk && Exec(dest, "PRAGMA journal_mode=DELETE");
    }
    if (dest)
        sqlite3_close(dest);
    sqlite3_close(src);
    if (fOk)
        LogPrintf("copied %s to %s\n", strFile.c_str(), pathDest.string().c_str());
    else
        LogPrintf("error copying %s to %s\n", strFile.c_str(), pathDest.string().c_str());
    return fOk;
}

#else // no SQLite in this build

bool SqliteWalletAvailable() { return false; }
std::unique_ptr<CWalletStorage> OpenSqliteWalletStorage(const std::string&, const char*) { return nullptr; }
bool RewriteSqliteWallet(const std::string&, const char*) { return false; }
bool BackupSqliteWallet(const std::string&, const std::string&) { return false; }

#endif
