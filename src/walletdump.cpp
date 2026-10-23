// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletdump.h"
#include "wallet.h"
#include "base58.h"
#include "util.h"

#include <fstream>
#include <set>
#include <sstream>
#include <vector>

using namespace std;

// Percent-encode a label so it fits in one space-separated dump field.
string EncodeDumpString(const string& str)
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

string DecodeDumpString(const string& str)
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

bool DumpWalletToFile(CWallet* pwallet, const std::filesystem::path& path, bool fOverwrite, string& strError)
{
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }
    if (!fOverwrite && std::filesystem::exists(path)) {
        strError = path.string() + " already exists. Choose a new filename so an existing file is never overwritten.";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);

    set<CKeyID> setKeys, setReserve;
    pwallet->GetKeys(setKeys);
    pwallet->GetAllReserveKeys(setReserve);

    std::ofstream file(path, std::ios::out | std::ios::trunc);
    if (!file.is_open()) {
        strError = "Cannot open wallet dump file";
        return false;
    }

    file << strprintf("# Wallet dump created by CorgiCoin %s\n", FormatFullVersion().c_str());
    file << strprintf("# * Created on %s\n", DateTimeStrFormat("%Y-%m-%dT%H:%M:%SZ", GetTime()).c_str());
    file << strprintf("# * Best block at time of backup was %d (%s),\n", nBestHeight, hashBestChain.GetHex().c_str());
    if (pwallet->IsHDEnabled())
        file << strprintf("# * HD seed id %s. The recovery phrase is not in this file;\n"
                          "#   keys derived after this dump are only recoverable from the phrase.\n",
                          pwallet->GetHDSeedId().GetHex().c_str());
    file << "\n";

    // Key birth times aren't recorded in this wallet format, so every key
    // gets the earliest time and an import rescans from genesis.
    const string strTime = "1970-01-01T00:00:01Z";
    for (const CKeyID& keyid : setKeys) {
        CSecret secret;
        bool fCompressed;
        if (!pwallet->GetSecret(keyid, secret, fCompressed))
            continue;
        string strAddr = CBitcoinAddress(keyid).ToString();
        string strSecret = CBitcoinSecret(secret, fCompressed).ToString();
        string strKind;
        auto it = pwallet->mapAddressBook.find(keyid);
        if (it != pwallet->mapAddressBook.end())
            strKind = "label=" + EncodeDumpString(it->second);
        else if (setReserve.count(keyid))
            strKind = "reserve=1";
        else
            strKind = "change=1";
        file << strprintf("%s %s %s # addr=%s\n", strSecret.c_str(), strTime.c_str(), strKind.c_str(), strAddr.c_str());
    }
    file << "\n# End of dump\n";
    file.close();
    if (file.fail()) {
        strError = "Error writing wallet dump file";
        return false;
    }
    return true;
}

static void RescanWallet(CWallet* pwallet)
{
    pwallet->ScanForWalletTransactions(pindexGenesisBlock, true);
    pwallet->ReacceptWalletTransactions();
}

bool ImportWalletFromFile(CWallet* pwallet, const std::filesystem::path& path, int& nImported, string& strError)
{
    nImported = 0;
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }

    std::ifstream file(path);
    if (!file.is_open()) {
        strError = "Cannot open wallet dump file";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);

    bool fGood = true;
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
        if (pwallet->HaveKey(keyid))
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
        if (!pwallet->AddKey(key)) {
            fGood = false;
            continue;
        }
        if (fLabel)
            pwallet->SetAddressBookName(keyid, strLabel);
        nImported++;
    }
    file.close();

    pwallet->MarkDirty();
    if (nImported > 0)
        RescanWallet(pwallet);

    if (!fGood) {
        strError = "Error adding some keys to wallet";
        return false;
    }
    return true;
}

bool ImportPrivateKey(CWallet* pwallet, const string& strSecret, const string& strLabel, bool& fAlreadyHad, string& strError)
{
    fAlreadyHad = false;
    CBitcoinSecret vchSecret;
    if (!vchSecret.SetString(strSecret)) {
        strError = "Invalid private key";
        return false;
    }
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }

    CKey key;
    bool fCompressed;
    CSecret secret = vchSecret.GetSecret(fCompressed);
    key.SetSecret(secret, fCompressed);
    CKeyID keyid = key.GetPubKey().GetID();

    LOCK2(cs_main, pwallet->cs_wallet);

    pwallet->MarkDirty();
    pwallet->SetAddressBookName(keyid, strLabel);
    if (pwallet->HaveKey(keyid)) {
        fAlreadyHad = true;
        return true;
    }
    if (!pwallet->AddKey(key)) {
        strError = "Error adding key to wallet";
        return false;
    }
    RescanWallet(pwallet);
    return true;
}
