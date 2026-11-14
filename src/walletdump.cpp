// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletdump.h"
#include "wallet.h"
#include "base58.h"
#include "util.h"

#include <fstream>
#ifndef WIN32
#include <fcntl.h>
#include <unistd.h>
#endif
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

    // Write to a temporary file next to the target and move it into place only when it is complete, so a failure
    // part way leaves no half-written backup that looks like a real one. Owner-only permissions where the platform
    // has them: the file holds every private key.
    // A fresh name, so a file of the user's called <path>.tmp is never truncated, and (not on Windows) created owner-only
    // and exclusively: never written first and chmod-ed after, and never through a symlink someone left there.
    const std::filesystem::path pathTmp = path.string() + strprintf(".tmp%08x", (unsigned int)GetRand(0xffffffff));
#ifndef WIN32
    {
        int fd = open(pathTmp.string().c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) {
            strError = "Cannot create the wallet dump file";
            return false;
        }
        close(fd);
    }
#endif
    std::ofstream file(pathTmp, std::ios::out | std::ios::trunc);
    if (!file.is_open()) {
        std::error_code ec;
        std::filesystem::remove(pathTmp, ec);
        strError = "Cannot open wallet dump file";
        return false;
    }
    auto Abort = [&](const std::string& strWhy) {
        file.close();
        std::error_code ec;
        std::filesystem::remove(pathTmp, ec);
        strError = strWhy;
        return false;
    };

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
            return Abort("Could not read the private key of " + CBitcoinAddress(keyid).ToString() +
                         " (the wallet may have been locked while it was being dumped). Nothing was written.");
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
    if (file.fail())
        return Abort("Error writing wallet dump file");
    {
        std::error_code ec;
        if (!fOverwrite && std::filesystem::exists(path))
            return Abort(path.string() + " appeared while the dump was being written. Choose a new filename.");
        std::filesystem::rename(pathTmp, path, ec);
        if (ec)
            return Abort("Cannot move the wallet dump into place: " + ec.message());
    }
    return true;
}

// nStartTime: the time the oldest key being looked for was made (0: unknown, so from the first block). The scan begins two
// hours before it, as block times are only roughly in order, and a key made later than the newest block has nothing to find.
static void RescanWallet(CWallet* pwallet, int64 nStartTime = 0)
{
    CBlockIndex* pindexStart = pindexGenesisBlock;
    if (nStartTime > 0)
    {
        pindexStart = pindexBest;
        while (pindexStart && pindexStart->pprev && pindexStart->GetBlockTime() >= nStartTime - 2 * 60 * 60)
            pindexStart = pindexStart->pprev;
    }
    pwallet->ScanForWalletTransactions(pindexStart, true);
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

bool ImportPrivateKey(CWallet* pwallet, const string& strSecret, const string& strLabel, bool& fAlreadyHad, string& strError, int64 nTimestamp)
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
    try {
        key.SetSecret(secret, fCompressed);
    } catch (const key_error&) {
        strError = "Invalid private key: the value is not a valid secret (zero or at least the curve order)";
        return false;
    }
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
    if (nTimestamp > 0)
        pwallet->SetKeyMetadata(key.GetPubKey(), CKeyMetadata(nTimestamp));      // the key's own date, not the day it was imported
    RescanWallet(pwallet, nTimestamp);
    return true;
}
