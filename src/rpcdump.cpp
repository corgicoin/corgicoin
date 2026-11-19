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
    if (fHelp || params.size() < 1 || params.size() > 3)
        throw runtime_error(
            "importprivkey <corgicoinprivkey> [label] [timestamp]\n"
            "Adds a private key (as returned by dumpprivkey) to your wallet.\n"
            "timestamp is when the key was made (seconds since 1970): the block chain is then searched from two hours before\n"
            "it instead of from the first block, which is much quicker. Leave it out, or give 0, when you do not know.");

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
    int64_t nTimestamp = 0;
    if (params.size() > 2)
    {
        nTimestamp = params[2].get_int64();
        if (nTimestamp < 0)
            throw JSONRPCError(-8, "The timestamp cannot be negative");
    }
    if (!ImportPrivateKey(pwalletMain.get(), strSecret, strLabel, fAlreadyHad, strError, nTimestamp))
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
    EnsureWalletIsUnlocked();  // a locked wallet used to report the key as "not known"
    CSecret vchSecret;
    bool fCompressed;
    if (!pwalletMain->GetSecret(keyID, vchSecret, fCompressed))
        throw JSONRPCError(-4,"Private key for address " + strAddress + " is not known");
    return CBitcoinSecret(vchSecret, fCompressed).ToString();
}

Value exportwalletencrypted(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 2)
        throw runtime_error(
            "exportwalletencrypted <filename> <passphrase>\n"
            "Writes the wallet's keys, recovery phrase, labels, key dates and watch-only entries to a new file, encrypted with\n"
            "a key made from <passphrase> (scrypt, AES-256-GCM). Unlike dumpwallet, the file is safe to keep on a USB stick or in\n"
            "the cloud, as long as the passphrase is long and is not kept with it (at least 8 characters). Redeem scripts are\n"
            "included, and a wallet whose recovery phrase cannot be read is refused rather than backed up without it. Restore with\n"
            "importwalletencrypted. The wallet must be unlocked. The passphrase is an argument here, so it shows in a shell's\n"
            "history and in the process list if you type it on a command line: call it from a script or a JSON-RPC client.");
    EnsureWalletIsUnlocked();
    std::filesystem::path path = std::filesystem::absolute(params[0].get_str());
    string strError;
    if (!ExportEncryptedBackup(pwalletMain.get(), path, params[1].get_str(), strError))
        throw JSONRPCError(-8, strError);
    Object result;
    result.emplace_back("filename", path.string());
    return result;
}

Value importwalletencrypted(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 2 || params.size() > 3)
        throw runtime_error(
            "importwalletencrypted <filename> <passphrase> [adoptphrase=false]\n"
            "Adds what an encrypted backup (exportwalletencrypted) holds and this wallet does not: keys, redeem scripts, watch-only\n"
            "entries, and labels for addresses that have none. Refuses a backup of another network, of another recovery phrase,\n"
            "with the wrong passphrase, or that has been changed. Then searches the chain from the oldest key's date. The wallet\n"
            "must be unlocked.\n"
            "A wallet with no recovery phrase takes the backup's only with adoptphrase=true: every new address then comes from\n"
            "that phrase, so say so only for a backup you made yourself. Without it the keys are added and the phrase is left.\n"
            "Returns {keys_added, labels, phrase_adopted}.");
    RPCTypeCheck(params, {str_type, str_type, bool_type});
    EnsureWalletIsUnlocked();
    int nKeys = 0, nLabels = 0;
    bool fAdopted = false;
    string strError;
    if (!ImportEncryptedBackup(pwalletMain.get(), std::filesystem::absolute(params[0].get_str()), params[1].get_str(),
                               params.size() > 2 && params[2].get_bool(), nKeys, nLabels, fAdopted, strError))
        throw JSONRPCError(-8, strError);
    Object result;
    result.emplace_back("keys_added", nKeys);
    result.emplace_back("labels", nLabels);
    result.emplace_back("phrase_adopted", fAdopted);
    return result;
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
