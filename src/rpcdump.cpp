// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "init.h" // for pwalletMain
#include "corgicoinrpc.h"
#include "ui_interface.h"
#include "base58.h"
#include "walletdump.h"

#include <filesystem>


using namespace json_spirit;
using namespace std;

void EnsureWalletIsUnlocked();

class CTxDump
{
public:
    CBlockIndex *pindex;
    int64 nValue;
    bool fSpent;
    CWalletTx* ptx;
    int nOut;
    CTxDump(CWalletTx* ptx = nullptr, int nOut = -1)
    {
        pindex = nullptr;
        nValue = 0;
        fSpent = false;
        this->ptx = ptx;
        this->nOut = nOut;
    }
};

Value importprivkey(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 1 || params.size() > 2)
        throw runtime_error(
            "importprivkey <corgicoinprivkey> [label]\n"
            "Adds a private key (as returned by dumpprivkey) to your wallet.");

    string strSecret = params[0].get_str();
    string strLabel = "";
    if (params.size() > 1)
        strLabel = params[1].get_str();
    CBitcoinSecret vchSecret;
    if (!vchSecret.SetString(strSecret))
        throw JSONRPCError(-5, "Invalid private key");
    EnsureWalletIsUnlocked();

    bool fAlreadyHad;
    string strError;
    if (!ImportPrivateKey(pwalletMain.get(), strSecret, strLabel, fAlreadyHad, strError))
        throw JSONRPCError(-4, strError);

    return Value::null;
}

Value dumpprivkey(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
        "dumpprivkey <corgicoinaddress>\n"
        "Reveals the private key corresponding to <corgicoinaddress>.");

    string strAddress = params[0].get_str();
    CBitcoinAddress address;
    if (!address.SetString(strAddress))
    throw JSONRPCError(-5, "Invalid CorgiCoin address");
    CKeyID keyID;
    if (!address.GetKeyID(keyID))
        throw JSONRPCError(-3, "Address does not refer to a key");
    CSecret vchSecret;
    bool fCompressed;
    if (!pwalletMain->GetSecret(keyID, vchSecret, fCompressed))
        throw JSONRPCError(-4,"Private key for address " + strAddress + " is not known");
    return CBitcoinSecret(vchSecret, fCompressed).ToString();
}

Value dumpwallet(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
            "dumpwallet <filename>\n"
            "Writes every private key in the wallet to <filename> in a\n"
            "human-readable format (one key per line, with its label or whether\n"
            "it is change or an unused keypool key). Restore with importwallet.\n"
            "The file is created on the machine running corgicoind and must not\n"
            "already exist. Anyone who reads it can spend your coins.");

    EnsureWalletIsUnlocked();

    std::filesystem::path path = std::filesystem::absolute(params[0].get_str());
    string strError;
    if (!DumpWalletToFile(pwalletMain.get(), path, false, strError))
        throw JSONRPCError(-8, strError);

    Object result;
    result.emplace_back("filename", path.string());
    return result;
}

Value importwallet(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
            "importwallet <filename>\n"
            "Imports the keys from a dumpwallet file, then rescans the chain\n"
            "for their transactions. Keys already in the wallet are skipped.");

    EnsureWalletIsUnlocked();

    std::filesystem::path path = params[0].get_str();
    if (!std::filesystem::is_regular_file(path))
        throw JSONRPCError(-8, "Cannot open wallet dump file");

    int nImported;
    string strError;
    if (!ImportWalletFromFile(pwalletMain.get(), path, nImported, strError))
        throw JSONRPCError(-4, strError);

    return Value::null;
}
