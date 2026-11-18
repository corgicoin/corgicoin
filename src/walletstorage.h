// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef CORGICOIN_WALLETSTORAGE_H
#define CORGICOIN_WALLETSTORAGE_H

#include "serialize.h"

#include <memory>
#include <string>

/** Where the wallet's records are kept: an ordered store of (key, value) records, a key and a value each the serialization of what CWalletDB writes,
 *  with transactions and a cursor that walks the keys in order. CWalletDB knows the records and their meaning; this knows only where they are.
 *
 *  Berkeley DB (wallet.dat) is the one implementation today. The interface is what a second one (SQLite) has to supply, with the records
 *  unchanged, so that a wallet can be read from one and written to the other.
 *
 *  Every call takes its buffers by reference and wipes them when it is done with them: a key or a value may be a private key. */
class CWalletStorage
{
public:
    virtual ~CWalletStorage() {}

    /** The value of a key. False if there is none (or the storage is not open). */
    virtual bool Read(CDataStream& ssKey, CDataStream& ssValue) = 0;
    /** Store a value; without fOverwrite an existing key is left as it is and false is returned. */
    virtual bool Write(CDataStream& ssKey, CDataStream& ssValue, bool fOverwrite) = 0;
    /** Remove a key. True also if there was none. */
    virtual bool Erase(CDataStream& ssKey) = 0;
    virtual bool Exists(CDataStream& ssKey) = 0;

    /** A position among the records, in the order of their keys (as bytes). Closed when it goes away. */
    class Cursor
    {
    public:
        enum Result { OK, END, FAILED };
        virtual ~Cursor() {}
        /** The first record whose key is not before ssKey; on OK ssKey and ssValue hold that record. */
        virtual Result Seek(CDataStream& ssKey, CDataStream& ssValue) = 0;
        /** The record after the one last read, or the first on a new cursor; on OK ssKey and ssValue hold it. */
        virtual Result Next(CDataStream& ssKey, CDataStream& ssValue) = 0;
    };
    /** A new cursor, or null if there is no storage to read. */
    virtual std::unique_ptr<Cursor> OpenCursor() = 0;

    /** One transaction at a time: writes between TxnBegin and TxnCommit take effect together, or not at all after TxnAbort. */
    virtual bool TxnBegin() = 0;
    virtual bool TxnCommit() = 0;
    virtual bool TxnAbort() = 0;

    virtual void Close() = 0;
};

/** Write the wallet's records again into a new file and put it in place of the old one, leaving out the records whose key begins with pszSkip (a
 *  serialized string: "\x04pool" is the key pool). Used after encrypting a wallet: the old file may hold pieces of the unencrypted private keys in
 *  space that is no longer used. Nothing else may have the storage open. False if it failed (the old file is then as it was). */
bool RewriteWalletStorage(const std::string& strFile, const char* pszSkip = nullptr);

/** The wallet's storage in the file strFile of the data directory. pszMode is as CDB takes it: "r" read only, "r+" read and write, "c" may create,
 *  as in "cr+". Throws if the file cannot be opened (as the CDB constructor always has). */
std::unique_ptr<CWalletStorage> OpenWalletStorage(const std::string& strFile, const char* pszMode);

#endif
