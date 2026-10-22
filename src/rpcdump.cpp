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

#include <filesystem>
#include <fstream>
#include <sstream>


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
    bool fGood = vchSecret.SetString(strSecret);

    if (!fGood) throw JSONRPCError(-5,"Invalid private key");

    CKey key;
    bool fCompressed;
    CSecret secret = vchSecret.GetSecret(fCompressed);
    key.SetSecret(secret, fCompressed);
    CKeyID vchAddress = key.GetPubKey().GetID();
    {
        LOCK2(cs_main, pwalletMain->cs_wallet);

        pwalletMain->MarkDirty();
        pwalletMain->SetAddressBookName(vchAddress, strLabel);

        if (!pwalletMain->AddKey(key))
            throw JSONRPCError(-4,"Error adding key to wallet");

        pwalletMain->ScanForWalletTransactions(pindexGenesisBlock, true);
        pwalletMain->ReacceptWalletTransactions();
    }

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

// Percent-encode a label so it fits in one space-separated dumpwallet field.
static string EncodeDumpString(const string& str)
{
    string ret;
    for (unsigned char c : str) {
        if (c <= 32 || c >= 128 || c == '%')
            ret += strprintf("%%%02x", c);
        else
            ret += c;
    }
    return ret;
}

static string DecodeDumpString(const string& str)
{
    string ret;
    for (size_t i = 0; i < str.size(); i++) {
        unsigned char c = str[i];
        if (c == '%' && i + 2 < str.size() && IsHex(str.substr(i + 1, 2))) {
            c = (unsigned char)strtol(str.substr(i + 1, 2).c_str(), nullptr, 16);
            i += 2;
        }
        ret += c;
    }
    return ret;
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
    if (std::filesystem::exists(path))
        throw JSONRPCError(-8, path.string() + " already exists. Choose a new filename so an existing file is never overwritten.");

    LOCK2(cs_main, pwalletMain->cs_wallet);

    set<CKeyID> setKeys, setReserve;
    pwalletMain->GetKeys(setKeys);
    pwalletMain->GetAllReserveKeys(setReserve);

    std::ofstream file(path);
    if (!file.is_open())
        throw JSONRPCError(-8, "Cannot open wallet dump file");

    file << strprintf("# Wallet dump created by CorgiCoin %s\n", FormatFullVersion().c_str());
    file << strprintf("# * Created on %s\n", DateTimeStrFormat("%Y-%m-%dT%H:%M:%SZ", GetTime()).c_str());
    file << strprintf("# * Best block at time of backup was %d (%s),\n", nBestHeight, hashBestChain.GetHex().c_str());
    if (pwalletMain->IsHDEnabled())
        file << strprintf("# * HD seed id %s. The recovery phrase is not in this file;\n"
                          "#   keys derived after this dump are only recoverable from the phrase.\n",
                          pwalletMain->GetHDSeedId().GetHex().c_str());
    file << "\n";

    // Key birth times aren't recorded in this wallet format, so every key
    // gets the earliest time and importwallet rescans from genesis.
    const string strTime = "1970-01-01T00:00:01Z";
    for (const CKeyID& keyid : setKeys) {
        CSecret secret;
        bool fCompressed;
        if (!pwalletMain->GetSecret(keyid, secret, fCompressed))
            continue;
        string strAddr = CBitcoinAddress(keyid).ToString();
        string strSecret = CBitcoinSecret(secret, fCompressed).ToString();
        string strKind;
        auto it = pwalletMain->mapAddressBook.find(keyid);
        if (it != pwalletMain->mapAddressBook.end())
            strKind = "label=" + EncodeDumpString(it->second);
        else if (setReserve.count(keyid))
            strKind = "reserve=1";
        else
            strKind = "change=1";
        file << strprintf("%s %s %s # addr=%s\n", strSecret.c_str(), strTime.c_str(), strKind.c_str(), strAddr.c_str());
    }
    file << "\n# End of dump\n";
    file.close();
    if (file.fail())
        throw JSONRPCError(-1, "Error writing wallet dump file");

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

    std::ifstream file(params[0].get_str());
    if (!file.is_open())
        throw JSONRPCError(-8, "Cannot open wallet dump file");

    LOCK2(cs_main, pwalletMain->cs_wallet);

    bool fGood = true;
    int nImported = 0;
    string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#')
            continue;

        vector<string> vstr;
        std::istringstream ss(line);
        for (string tok; ss >> tok; )
            vstr.push_back(tok);
        if (vstr.size() < 2)
            continue;

        CBitcoinSecret vchSecret;
        if (!vchSecret.SetString(vstr[0])) {
            fGood = false;
            continue;
        }
        CKey key;
        bool fCompressed;
        CSecret secret = vchSecret.GetSecret(fCompressed);
        key.SetSecret(secret, fCompressed);
        CKeyID keyid = key.GetPubKey().GetID();
        if (pwalletMain->HaveKey(keyid))
            continue;

        bool fLabel = false;
        string strLabel;
        for (size_t i = 2; i < vstr.size(); i++) {
            if (vstr[i][0] == '#')
                break;
            if (vstr[i].compare(0, 6, "label=") == 0) {
                strLabel = DecodeDumpString(vstr[i].substr(6));
                fLabel = true;
            }
        }
        if (!pwalletMain->AddKey(key)) {
            fGood = false;
            continue;
        }
        if (fLabel)
            pwalletMain->SetAddressBookName(keyid, strLabel);
        nImported++;
    }
    file.close();

    pwalletMain->MarkDirty();
    if (nImported > 0) {
        pwalletMain->ScanForWalletTransactions(pindexGenesisBlock, true);
        pwalletMain->ReacceptWalletTransactions();
    }

    if (!fGood)
        throw JSONRPCError(-4, "Error adding some keys to wallet");

    return Value::null;
}
